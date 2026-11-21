"""
مولّد خطط العمل داخل المنصة (/workplans)
========================================
نفس واجهة التطبيق القديم (index.html) — جسر google.script.run يحوّل كل استدعاء إلى /api/wpgen/call
والبيانات في قاعدة المنصة:
  - العقود وبنودها: من جدول quotes (مرآة مولّد العقود الآن، والمنصة لاحقاً)
  - الخطط ونسخها: wpg_plans + wpg_versions
  - تنبيهات طلبات التغيير: gen_change_requests
  - الكتالوج وصور الأصول (مجلد «الاصول» في الدرايف): عبر جسر Apps Script (الدرايف خاص)
  - الاعتماد: يحفظ كل مستند كصفحة جاهزة للطباعة/الحفظ PDF بهوية أبيلا

الكاتب الوحيد: الإعداد wpg_master = 'generator' (الافتراضي أثناء التشغيل المتوازي) → الحفظ والاعتماد من التطبيق القديم،
والمنصة تستورد الخطط منه. 'hub' → الحفظ والاعتماد من المنصة.
"""
import json, os, re, time, uuid, base64, hmac, hashlib, secrets, datetime, threading, urllib.request
from pathlib import Path

import access_control as ac

HERE = Path(__file__).resolve().parent
DEFAULT_LISTS = json.loads((HERE / 'wpgen' / 'default_lists.json').read_text(encoding='utf-8'))
EN = json.loads((HERE / 'wpgen' / 'en.json').read_text(encoding='utf-8'))
LOGO = (HERE / 'wpgen' / 'logo.txt').read_text().strip()

# رابط تطبيق خطط العمل القديم (Apps Script) — يستخدم كجسر للدرايف
BRIDGE_URL = os.environ.get('WPG_BRIDGE_URL') or \
    'https://script.google.com/macros/s/AKfycbx4LfbNaP3seSz1H94a6V2pgHi7W_K55badLIeTd4EZwvATQgvW-ta666a9nMgnVQApCg/exec'
HUB_PUBLIC = os.environ.get('HUB_PUBLIC_URL') or 'https://hub.theabella.com'

ROLE_AR = {'owner': 'الإدارة', 'general_manager': 'الإدارة', 'admin': 'الإدارة',
           'project_manager': 'مشرف', 'supervisor': 'مشرف', 'field': 'مدير تشغيل'}
APPROVER_ROLES = ('owner', 'general_manager', 'admin', 'project_manager', 'supervisor')
CONTRACT_STATES = ('عقد ساري', 'مكتمل الدفع', 'منتهي', 'قيد التنفيذ')

_NONCES = {}
_NLOCK = threading.Lock()
_CACHE = {}


def _now():
    return datetime.datetime.now().strftime('%Y/%m/%d %H:%M')


def _ts(s):
    m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?', str(s or ''))
    if not m:
        return 0
    return int(datetime.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4] or 0), int(m[5] or 0)).timestamp() * 1000)


def _sl(d):
    """ISO → yyyy/MM/dd (صيغة التطبيق)"""
    return (str(d or '')[:10]).replace('-', '/') if d else ''


def init_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS wpg_plans (
        quote_code TEXT PRIMARY KEY, contract_code TEXT, operation_order TEXT, client TEXT, event_date TEXT,
        status TEXT, version INTEGER DEFAULT 0, updated TEXT, updated_by TEXT, approved_version INTEGER DEFAULT 0,
        approved_by TEXT, approved_at TEXT, folder TEXT, pdfs_json TEXT, source TEXT DEFAULT 'hub');
    CREATE TABLE IF NOT EXISTS wpg_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, quote_code TEXT NOT NULL, v INTEGER NOT NULL, date TEXT, by_name TEXT,
        type TEXT, note TEXT, pdfs_json TEXT, data_json TEXT, source TEXT DEFAULT 'hub', UNIQUE(quote_code, v));
    CREATE TABLE IF NOT EXISTS wpg_docs (
        id TEXT PRIMARY KEY, quote_code TEXT, v INTEGER, doc_key TEXT, title TEXT, html TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS wpg_uploads (
        id TEXT PRIMARY KEY, quote_code TEXT, name TEXT, path TEXT, mime TEXT, by_name TEXT, created_at TEXT);
    """)
    s = ac.get_settings(conn)
    for k, v in (('wpg_master', 'generator'), ('wpg_doc_secret', secrets.token_hex(24)),
                 ('wpg_lists', json.dumps(DEFAULT_LISTS, ensure_ascii=False))):
        if not s.get(k):
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, v))


def _setting(conn, k, d=None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    return r[0] if r and r[0] is not None else d


def _set(conn, k, v):
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, v))


def is_hub_master(conn):
    return (_setting(conn, 'wpg_master') or 'generator') == 'hub'


# ───────────────────────── الجسر (Apps Script) ─────────────────────────
def new_nonce():
    n = secrets.token_urlsafe(24)
    with _NLOCK:
        now = time.time()
        for k in [k for k, t in _NONCES.items() if t < now]:
            _NONCES.pop(k, None)
        _NONCES[n] = now + 180
    return n


def verify_nonce(n):
    with _NLOCK:
        t = _NONCES.get(n or '')
        return bool(t and t > time.time())


def bridge(fn, timeout=90, **kw):
    body = json.dumps({'fn': fn, 'nonce': new_nonce(), **kw}).encode()
    req = urllib.request.Request(BRIDGE_URL, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode('utf-8')
    try:
        j = json.loads(txt)
    except Exception:
        raise RuntimeError('جسر الدرايف غير مفعّل بعد (تطبيق خطط العمل القديم يحتاج تحديث)')
    if not j.get('ok'):
        raise RuntimeError(j.get('error') or 'خطأ في جسر الدرايف')
    return j.get('data')


def _cached(key, ttl, fn):
    c = _CACHE.get(key)
    if c and c[0] > time.time():
        return c[1]
    v = fn()
    _CACHE[key] = (time.time() + ttl, v)
    return v


# ───────────────────────── البيانات ─────────────────────────
def _rows(conn, sql, p=()):
    return [dict(r) for r in conn.execute(sql, p).fetchall()]


def me(conn, ctx):
    u, perms = ctx['user'], ctx['perms']
    sup = bool(perms.get('is_super'))
    can_edit = sup or ac.can(perms, 'work_plans', 'edit') or ac.can(perms, 'work_plans', 'create') \
        or u['role'] in ('supervisor', 'field', 'project_manager')
    return {'name': (u['full_name'] or u['username']).split(' — ')[0], 'role': ROLE_AR.get(u['role'], perms.get('role_name') or u['role']),
            'canEdit': bool(can_edit), 'canApprove': sup or u['role'] in APPROVER_ROLES, 'isSuper': sup}


def team(conn):
    us = _rows(conn, "SELECT full_name, username, role FROM users WHERE is_active=1 ORDER BY full_name")
    allx = [{'name': (x['full_name'] or x['username']).split(' — ')[0], 'role': ROLE_AR.get(x['role'], x['role'])} for x in us]
    return {'ops': [x['name'] for x in allx if x['role'] == 'مدير تشغيل'],
            'pms': [x['name'] for x in allx if x['role'] == 'مشرف'], 'all': allx}


def lists(conn):
    try:
        L = json.loads(_setting(conn, 'wpg_lists') or '{}')
    except Exception:
        L = {}
    for k, v in DEFAULT_LISTS.items():
        L.setdefault(k, v)
    return L


def contracts(conn):
    guests = {}
    for r in conn.execute("SELECT quote_code, revision, data_json FROM gen_quote_revisions ORDER BY quote_code, revision"):
        try:
            g = (json.loads(r[2] or '{}') or {}).get('guests')
            if g:
                guests[r[0]] = str(g)
        except Exception:
            pass
    out = []
    for q in _rows(conn, """SELECT q.*, e.operation_order AS ev_op FROM quotes q LEFT JOIN events e ON e.id=q.event_id
                            ORDER BY q.quote_code"""):
        items = _rows(conn, "SELECT name, qty FROM quote_items WHERE quote_id=? ORDER BY sort_order, id", (q['id'],))
        st = q.get('gen_status') or {'contracted': 'عقد ساري', 'draft': 'مسودة', 'sent': 'عرض سعر',
                                     'accepted': 'عرض سعر', 'rejected': 'ملغي'}.get(q['status'], q['status'])
        vk = q.get('venue_kind')
        typ = {'newborn': 'استقبال ولادة (منزل)' if vk == 'home' else 'استقبال ولادة (مستشفى)',
               'special': 'مناسبة خاصة / زواج', 'exhibition': 'معرض'}.get(q['event_type'], q['event_type'])

        def qty(v):
            if v in (None, '', 0, 0.0):
                return ''
            return str(int(v)) if float(v).is_integer() else str(v)
        out.append({'Q': q['quote_code'], 'status': st, 'B': q.get('contract_code') or '',
                    'O': q.get('gen_operation_order') or q.get('ev_op') or '', 'title': q.get('client_title') or '',
                    'client': q.get('client_name') or '', 'phone': q.get('client_phone') or '', 'type': typ,
                    'location': q.get('venue_name') or '', 'eventDate': _sl(q.get('expected_date')),
                    'confirmed': _sl(q.get('confirmed_date')), 'ver': str(q.get('revision') or ''),
                    'notes': q.get('notes') or '', 'guests': guests.get(q['quote_code'], str(q.get('guests_count') or '')),
                    'services': [{'name': i['name'], 'qty': qty(i['qty'])} for i in items]})
    return out


def plans_index(conn):
    out = {}
    for p in _rows(conn, "SELECT * FROM wpg_plans"):
        try:
            pdfs = json.loads(p.get('pdfs_json') or '{}')
        except Exception:
            pdfs = {}
        out[p['quote_code']] = {'status': p['status'] or '', 'version': p['version'] or 0, 'updated': p['updated'] or '',
                                'by': p['updated_by'] or '', 'approvedVersion': p['approved_version'] or 0,
                                'approvedBy': p['approved_by'] or '', 'approvedAt': p['approved_at'] or '',
                                'folder': p['folder'] or '', 'updatedTs': _ts(p['updated']), 'approvedTs': _ts(p['approved_at']),
                                'pdfs': pdfs}
    return out


def change_alerts(conn, plans):
    out = {}
    for r in _rows(conn, "SELECT * FROM gen_change_requests WHERE status='معتمد'"):
        Q = r.get('quote_code') or ''
        p = plans.get(Q)
        kind = r.get('request_type') or ''
        if not p and kind != 'ملحق':
            continue
        ref = 0 if not p else (p['approvedTs'] if p['approvedVersion'] else p['updatedTs'])
        at = _ts(r.get('approved_at'))
        if not at or at <= ref:
            continue
        try:
            diff = json.loads(r.get('diff_json') or '[]')
        except Exception:
            diff = []
        out.setdefault(Q, []).append({'crNo': r['request_code'], 'B': r.get('contract_code') or '', 'kind': kind,
                                      'summary': r.get('summary') or '', 'approvedBy': r.get('approved_by') or '',
                                      'approvedAt': (r.get('approved_at') or '').replace('-', '/')[:16],
                                      'result': r.get('result') or '', 'diff': diff})
    return out


def versions(conn, Q):
    return _rows(conn, "SELECT id, v, date, by_name AS by, type, note, pdfs_json FROM wpg_versions WHERE quote_code=? ORDER BY v", (Q,))


def write_version(conn, plan, user, typ, note, pdfs=None, source='hub'):
    Q = str(plan.get('Q') or '').strip()
    if not Q:
        raise ValueError('خطة بدون رقم عرض')
    last = conn.execute("SELECT MAX(v) FROM wpg_versions WHERE quote_code=?", (Q,)).fetchone()[0] or 0
    nv = last + 1
    plan['version'] = nv
    plan['savedAt'] = _now()
    plan['savedBy'] = user
    conn.execute("""INSERT INTO wpg_versions (quote_code, v, date, by_name, type, note, pdfs_json, data_json, source)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (Q, nv, _now(), user, typ, note or '', json.dumps(pdfs or {}, ensure_ascii=False),
                  json.dumps(plan, ensure_ascii=False), source))
    prev = conn.execute("SELECT approved_version, approved_by, approved_at, folder, pdfs_json FROM wpg_plans WHERE quote_code=?",
                        (Q,)).fetchone()
    approved = typ == 'اعتماد'
    status = 'معتمدة' if approved else ('معدّلة بعد الاعتماد' if prev and prev[0] else 'مسودة')
    conn.execute("""INSERT INTO wpg_plans (quote_code, contract_code, operation_order, client, event_date, status, version, updated,
                      updated_by, approved_version, approved_by, approved_at, folder, pdfs_json, source)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(quote_code) DO UPDATE SET contract_code=excluded.contract_code, operation_order=excluded.operation_order,
                      client=excluded.client, event_date=excluded.event_date, status=excluded.status, version=excluded.version,
                      updated=excluded.updated, updated_by=excluded.updated_by, approved_version=excluded.approved_version,
                      approved_by=excluded.approved_by, approved_at=excluded.approved_at, pdfs_json=excluded.pdfs_json,
                      source=excluded.source""",
                 (Q, plan.get('B') or '', plan.get('O') or '', plan.get('client') or '', plan.get('eventDate') or '', status, nv,
                  _now(), user, nv if approved else (prev[0] if prev else 0), user if approved else (prev[1] if prev else ''),
                  _now() if approved else (prev[2] if prev else ''), prev[3] if prev else '',
                  json.dumps(pdfs if approved else (json.loads(prev[4] or '{}') if prev else {}), ensure_ascii=False), source))
    return {'version': nv, 'status': status}


def _doc_sig(conn, doc_id):
    key = (_setting(conn, 'wpg_doc_secret') or 'x').encode()
    return hmac.new(key, doc_id.encode(), hashlib.sha256).hexdigest()[:24]


def doc_url(conn, doc_id):
    return f"/wpdoc/{doc_id}?k={_doc_sig(conn, doc_id)}"


def _img_src(conn, img_id, w=700):
    if img_id.startswith('u_'):
        r = conn.execute("SELECT path FROM wpg_uploads WHERE id=?", (img_id,)).fetchone()
        return '/uploads/' + r[0] if r else ''
    return ''


def _upload_dir():
    d = Path(os.environ.get('DATA_DIR') or (HERE / '..' / 'backend')) / 'uploads' / 'wpg' if os.environ.get('DATA_DIR') \
        else HERE / 'uploads' / 'wpg'
    d.mkdir(parents=True, exist_ok=True)
    return d


# ───────────────────────── الاستدعاءات (نفس أسماء Code.gs) ─────────────────────────
def _need_write(conn, ctx, what):
    m = me(conn, ctx)
    if not is_hub_master(conn):
        raise PermissionError('الحفظ والاعتماد حالياً من تطبيق خطط العمل القديم (التشغيل المتوازي) — '
                              'المنصة تعرض الخطط وتطبعها. التحويل من زر «تحويل الكتابة للمنصة».')
    if what == 'edit' and not m['canEdit']:
        raise PermissionError('ليس لديك صلاحية التعديل')
    if what == 'approve' and not m['canApprove']:
        raise PermissionError('الاعتماد للإدارة ومديرة المشروع فقط')
    return m


def call(conn, ctx, fn, args):
    a = list(args or [])
    if fn == 'api_bootstrap':
        plans = plans_index(conn)
        m = me(conn, ctx)
        m['hubMaster'] = is_hub_master(conn)
        return {'me': m, 'team': team(conn), 'lists': lists(conn), 'contracts': contracts(conn), 'plans': plans,
                'alerts': change_alerts(conn, plans), 'bookUrl': '', 'hubMaster': m['hubMaster']}
    if fn == 'api_contracts':
        plans = plans_index(conn)
        return {'contracts': contracts(conn), 'plans': plans, 'alerts': change_alerts(conn, plans)}
    if fn == 'api_catalog':
        fresh = bool(a and a[0])
        if fresh:
            _CACHE.pop('catalog', None)
        return _cached('catalog', 3600, lambda: bridge('catalog', fresh=fresh))
    if fn == 'api_photos':
        fid = str(a[0] if a else '')
        return _cached('fp_' + fid, 600, lambda: bridge('photos', folderId=fid))
    if fn == 'api_thumbs':
        ids = [str(x) for x in (a[0] if a else [])][:16]
        out, need = {}, []
        for i in ids:
            if i.startswith('u_'):
                out[i] = _img_src(conn, i)
            elif ('th_' + i) in _CACHE:
                out[i] = _CACHE['th_' + i][1]
            else:
                need.append(i)
        if need:
            got = bridge('thumbs', ids=need, w=300) or {}
            for k, v in got.items():
                if v:
                    _CACHE['th_' + k] = (time.time() + 21600, v)
            out.update(got)
        return out
    if fn == 'api_getPlan':
        Q = str(a[0] if a else '')
        vs = versions(conn, Q)
        meta = plans_index(conn).get(Q)
        if not vs:
            return {'meta': meta, 'versions': [], 'plan': None}
        last = conn.execute("SELECT data_json FROM wpg_versions WHERE id=?", (vs[-1]['id'],)).fetchone()[0]
        return {'meta': meta, 'versions': [{'v': x['v'], 'date': x['date'], 'by': x['by'], 'type': x['type'], 'note': x['note'],
                                            'pdfs': json.loads(x['pdfs_json'] or '{}')} for x in vs],
                'plan': json.loads(last)}
    if fn == 'api_getVersion':
        r = conn.execute("SELECT data_json FROM wpg_versions WHERE quote_code=? AND v=?", (str(a[0]), int(a[1]))).fetchone()
        if not r:
            raise ValueError('النسخة غير موجودة')
        return json.loads(r[0])
    if fn == 'api_save':
        m = _need_write(conn, ctx, 'edit')
        plan, note, base, force = a[1], (a[2] if len(a) > 2 else ''), (a[3] if len(a) > 3 else 0), (a[4] if len(a) > 4 else False)
        last = conn.execute("SELECT v, by_name, date FROM wpg_versions WHERE quote_code=? ORDER BY v DESC LIMIT 1",
                            (str(plan.get('Q')),)).fetchone()
        if not force and last and int(base or 0) < last[0]:
            return {'conflict': True, 'latest': last[0], 'by': last[1], 'date': last[2]}
        r = write_version(conn, plan, m['name'], 'مسودة', note)
        conn.commit()
        return r
    if fn == 'api_upload':
        m = _need_write(conn, ctx, 'edit')
        Q, data_url, name = str(a[1]), str(a[4]), str(a[5] if len(a) > 5 else '')
        mm = re.match(r'^data:([^;]+);base64,(.+)$', data_url, re.S)
        if not mm:
            raise ValueError('ملف غير صالح')
        ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif'}.get(mm[1], '.bin')
        fid = 'u_' + uuid.uuid4().hex[:20]
        d = _upload_dir()
        (d / (fid + ext)).write_bytes(base64.b64decode(mm[2]))
        conn.execute("INSERT INTO wpg_uploads (id, quote_code, name, path, mime, by_name, created_at) VALUES (?,?,?,?,?,?,?)",
                     (fid, Q, name or fid, 'wpg/' + fid + ext, mm[1], m['name'], _now()))
        conn.commit()
        return {'id': fid, 'name': name or fid}
    if fn == 'api_approve':
        m = _need_write(conn, ctx, 'approve')
        plan, note, docs = a[1], (a[2] if len(a) > 2 else ''), (a[3] if len(a) > 3 else {}) or {}
        base, force = (a[4] if len(a) > 4 else 0), (a[5] if len(a) > 5 else False)
        Q = str(plan.get('Q'))
        # الدليل الإجرائي م4: لا تخطيط ولا اعتماد خطة قبل استلام العربون (الإدارة العليا تقدر تتجاوز بـ depositOverride)
        try:
            import project_native
            dep = project_native.deposit_ok(conn, Q)
            if not dep['ok'] and not (ctx['perms'].get('is_super') and (plan.get('depositOverride') or (a[6] if len(a) > 6 else False))):
                raise PermissionError(f"ما ينفع اعتماد الخطة قبل استلام العربون — المستلم {dep['paid']:,.0f} من {dep['need']:,.0f} ر.س المطلوبة")
        except PermissionError:
            raise
        except Exception:
            pass
        last = conn.execute("SELECT v, by_name, date FROM wpg_versions WHERE quote_code=? ORDER BY v DESC LIMIT 1", (Q,)).fetchone()
        if not force and last and int(base or 0) < last[0]:
            return {'conflict': True, 'latest': last[0], 'by': last[1], 'date': last[2]}
        nv = (last[0] if last else 0) + 1
        ids = set()
        for k, d in docs.items():
            ids.update(re.findall(r'__IMG__([\w-]+)__', str(d.get('html') or '')))
        drive_ids = [i for i in ids if not i.startswith('u_')]
        imgs = {}
        for i in range(0, len(drive_ids), 16):
            try:
                imgs.update(bridge('thumbs', ids=drive_ids[i:i + 16], w=700) or {})
            except Exception:
                pass
        pdfs = {}
        for k, d in docs.items():
            html = re.sub(r'__IMG__([\w-]+)__',
                          lambda mo: _img_src(conn, mo[1]) if mo[1].startswith('u_')
                          else (imgs.get(mo[1]) or f"https://lh3.googleusercontent.com/d/{mo[1]}=w700"), str(d.get('html') or ''))
            did = uuid.uuid4().hex[:16]
            conn.execute("INSERT INTO wpg_docs (id, quote_code, v, doc_key, title, html, created_at) VALUES (?,?,?,?,?,?,?)",
                         (did, Q, nv, k, d.get('title') or k, html, _now()))
            pdfs[k] = {'title': d.get('title') or k, 'url': doc_url(conn, did), 'id': did}
        plan['approvedBy'] = m['name']
        plan['approvedAt'] = _now()
        r = write_version(conn, plan, m['name'], 'اعتماد', note, pdfs)
        r['pdfs'] = pdfs
        conn.commit()
        # توزيع الخطة المعتمدة على الأقسام (كل قسم تجيه مهامه في حسابه)
        try:
            import ops_native
            if conn.execute("SELECT 1 FROM opn_orders WHERE Q=?", (Q,)).fetchone():
                r['distributed'] = ops_native.import_plan(conn, Q, m['name'])
                conn.commit()
        except Exception as e:
            r['distributeError'] = str(e)
        return r
    if fn == 'api_logo':
        return LOGO
    if fn == 'hub_setMaster':
        if not ctx['perms'].get('is_super'):
            raise PermissionError('للإدارة فقط')
        val = 'hub' if a and a[0] == 'hub' else 'generator'
        _set(conn, 'wpg_master', val)
        ac.audit(conn, ctx['user']['id'], 'WPG_MASTER', 'settings', None, new={'wpg_master': val})
        conn.commit()
        return {'master': val}
    if fn == 'hub_import':
        if not ctx['perms'].get('is_super'):
            raise PermissionError('للإدارة فقط')
        return import_from_generator(conn)
    raise ValueError('استدعاء غير معروف: ' + str(fn))


# ───────────────────────── استيراد الخطط من التطبيق القديم ─────────────────────────
def import_from_generator(conn, log=print):
    """يسحب الخطط ونسخها من «أبيلا — خطط العمل» عبر الجسر — للخطط اللي مصدرها المولّد فقط"""
    idx = bridge('export_index') or {}
    n_plans = n_vers = 0
    for Q, meta in idx.items():
        own = conn.execute("SELECT source FROM wpg_plans WHERE quote_code=?", (Q,)).fetchone()
        if own and own[0] == 'hub':
            continue  # خطة عُدّلت في المنصة بعد التحويل — لا نكتب فوقها
        have = conn.execute("SELECT COALESCE(MAX(v),0) FROM wpg_versions WHERE quote_code=?", (Q,)).fetchone()[0]
        if have >= int(meta.get('version') or 0) and own:
            continue
        vs, since = [], have
        while True:
            part = bridge('export_plan', Q=Q, since=since) or []
            vs += part
            if len(part) < 15:
                break
            since = max(int(x['v']) for x in part)
        for x in vs:
            conn.execute("""INSERT OR REPLACE INTO wpg_versions (quote_code, v, date, by_name, type, note, pdfs_json, data_json, source)
                            VALUES (?,?,?,?,?,?,?,?, 'generator')""",
                         (Q, int(x['v']), x.get('date'), x.get('by'), x.get('type'), x.get('note'),
                          json.dumps(x.get('pdfs') or {}, ensure_ascii=False), json.dumps(x.get('plan'), ensure_ascii=False)))
            n_vers += 1
        conn.execute("""INSERT OR REPLACE INTO wpg_plans (quote_code, contract_code, operation_order, client, event_date, status, version,
                          updated, updated_by, approved_version, approved_by, approved_at, folder, pdfs_json, source)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'generator')""",
                     (Q, meta.get('B'), meta.get('O'), meta.get('client'), meta.get('eventDate'), meta.get('status'),
                      int(meta.get('version') or 0), meta.get('updated'), meta.get('by'), int(meta.get('approvedVersion') or 0),
                      meta.get('approvedBy'), meta.get('approvedAt'), meta.get('folder'),
                      json.dumps(meta.get('pdfs') or {}, ensure_ascii=False)))
        n_plans += 1
        conn.commit()
    try:
        L = bridge('lists')
        if L:
            _set(conn, 'wpg_lists', json.dumps(L, ensure_ascii=False))
            conn.commit()
    except Exception:
        pass
    log(f'✓ خطط العمل من المولّد: {n_plans} خطة، {n_vers} نسخة')
    return {'plans': n_plans, 'versions': n_vers}


# ───────────────────────── HTTP ─────────────────────────
def handle(h, conn, method, path, query, data, ctx, send_json):
    if path == '/api/wpgen/call' and method == 'POST':
        try:
            res = call(conn, ctx, data.get('fn'), data.get('args') or [])
            send_json({'ok': True, 'data': res})
        except PermissionError as e:
            send_json({'ok': False, 'error': str(e)})
        except Exception as e:
            send_json({'ok': False, 'error': str(e)})
        return True
    return False


def serve_doc(h, conn, doc_id, k):
    if not doc_id or not hmac.compare_digest(_doc_sig(conn, doc_id), k or ''):
        h.send_response(403); h.end_headers(); return
    r = conn.execute("SELECT html, title FROM wpg_docs WHERE id=?", (doc_id,)).fetchone()
    if not r:
        h.send_response(404); h.end_headers(); return
    html = r[0]
    bar = ('<div class="noprint" style="position:fixed;top:8px;left:8px;z-index:9;font-family:Tahoma">'
           '<button onclick="print()" style="padding:8px 14px;background:#8B6F47;color:#fff;border:0;border-radius:6px;cursor:pointer">'
           '🖨 طباعة / حفظ PDF</button></div><style>@media print{.noprint{display:none}}</style>')
    html = html.replace('<body>', '<body>' + bar, 1) if '<body>' in html else bar + html
    b = html.encode('utf-8')
    h.send_response(200)
    h.send_header('Content-Type', 'text/html; charset=utf-8')
    h.send_header('Content-Length', str(len(b)))
    h.end_headers()
    h.wfile.write(b)
