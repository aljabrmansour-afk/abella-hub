"""
الجرد داخل المنصة (/jard) — بدل «جرد المصنع» v3 و«جرد المستودع الثاني»
=====================================================================
خانات المصنع: الخام · المعدات · الأصول (بالترميز LGT/SEA/TBL…) — كل قطعة: وصف إلزامي + صور
  - الخام: الصنف، الكمية (تقبل كسور)، الوحدة، الموقع، صورة 1–4
  - المعدات: الاسم، الرقم التسلسلي، الكمية، الحالة، الموقع، صورة 1–4 إلزامية
  - الأصول: التصنيف → النوع، اسم القطعة، الكمية موزعة على الحالات (ممتاز/جيد/يحتاج صيانة/تالف)، صورة لكل حالة + حتى 3 إضافية
المستودع الثاني (الكماليات): نفس الأصول بالعربي والإنجليزي (HOS/ACC).
بيانات «جرد المصنع» القديمة تُستورد من seed/jard_snapshot.json أول مرة.
"""
import json, os, re, base64, uuid, datetime
from pathlib import Path
import access_control as ac

STATES = ['ممتاز', 'جيد', 'يحتاج صيانة', 'تالف']
STATES_EN = {'ممتاز': 'Excellent', 'جيد': 'Good', 'يحتاج صيانة': 'Needs repair', 'تالف': 'Damaged'}
UNITS = ['حبة', 'متر', 'متر مربع', 'لوح', 'كيلو', 'لتر', 'كرتون', 'رول', 'طقم']
EQP_STATES = ['تعمل', 'تحتاج صيانة', 'تالفة']
WH = {'factory': 'المصنع', 'w2': 'المستودع الثاني (الكماليات)'}


def now():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime('%Y-%m-%d %H:%M')


def t_(v):
    return '' if v is None else str(v).strip()


def init_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS jrd_categories (code TEXT PRIMARY KEY, wh TEXT, main TEXT, main_en TEXT, sub TEXT, sub_en TEXT,
        type TEXT, type_en TEXT, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS jrd_items (id TEXT PRIMARY KEY, section TEXT, wh TEXT, code TEXT, name TEXT, name_en TEXT, qty REAL, unit TEXT,
        serial TEXT, state TEXT, counts_json TEXT, location TEXT, description TEXT, notes TEXT, by_name TEXT, at TEXT, updated TEXT,
        source TEXT DEFAULT 'hub', deleted INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS jrd_photos (id TEXT PRIMARY KEY, item_id TEXT, state TEXT, url TEXT, by_name TEXT, at TEXT);
    CREATE INDEX IF NOT EXISTS idx_jrd_photos_i ON jrd_photos(item_id);
    """)
    if not conn.execute("SELECT 1 FROM settings WHERE key='jrd_seeded_v1'").fetchone():
        p = Path(__file__).resolve().parent.parent / 'seed' / 'jard_snapshot.json'
        if p.exists():
            d = json.loads(p.read_text('utf-8'))
            for c in d['categories']:
                conn.execute("INSERT OR IGNORE INTO jrd_categories (code, wh, main, main_en, sub, sub_en, type, type_en) VALUES (?,?,?,?,?,?,?,?)",
                             (c['code'], c['wh'], c['main'], c['main_en'], c['sub'], c['sub_en'], c['type'], c['type_en']))
            for it in d['assets']:
                conn.execute("""INSERT OR IGNORE INTO jrd_items (id, section, wh, code, name, qty, counts_json, location, description, notes, by_name, at, updated, source)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (it['id'], 'asset', 'factory', it['code'], it['name'], it['qty'], json.dumps(it['counts'], ensure_ascii=False),
                              it['loc'], it['desc'], it['notes'], it['by'], it['at'], it['at'], 'جرد المصنع (التطبيق القديم)'))
            for i, ph in enumerate(d['photos']):
                conn.execute("INSERT OR IGNORE INTO jrd_photos (id, item_id, state, url, by_name, at) VALUES (?,?,?,?,?,?)",
                             (f"old{i}", ph['item'], ph['state'], f"https://lh3.googleusercontent.com/d/{ph['drive']}=w800", '', ''))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('jrd_seeded_v1', ?)", (now(),))
        conn.commit()


def _me(ctx):
    u = ctx['user']
    return (u.get('full_name') or u['username']).split(' — ')[0].strip()


def _can_write(ctx):
    p = ctx['perms']
    return p.get('is_super') or ac.can(p, 'inventory', 'create') or ac.can(p, 'inventory', 'edit') or ac.can(p, 'raw_materials', 'create')


def _save_img(data_url, prefix):
    m = re.match(r'^data:(image/[\w.+-]+);base64,(.+)$', data_url or '', re.S)
    if not m:
        raise ValueError('صورة غير صالحة')
    base = Path(os.environ['DATA_DIR']) / 'uploads' if os.environ.get('DATA_DIR') else Path(__file__).resolve().parent / 'uploads'
    d = base / 'jard'
    d.mkdir(parents=True, exist_ok=True)
    name = f"{re.sub(r'[^A-Za-z0-9-]', '', prefix) or 'x'}-{uuid.uuid4().hex[:12]}{'.png' if 'png' in m[1] else '.jpg'}"
    (d / name).write_bytes(base64.b64decode(m[2]))
    return '/uploads/jard/' + name


def _item_out(conn, r, photos=None):
    d = dict(r)
    d['counts'] = json.loads(d.pop('counts_json') or '{}')
    c = conn.execute("SELECT * FROM jrd_categories WHERE code=?", (d['code'],)).fetchone() if d.get('code') else None
    if c:
        d.update(main=c['main'], sub=c['sub'], type=c['type'], main_en=c['main_en'], sub_en=c['sub_en'], type_en=c['type_en'])
    d['photos'] = photos if photos is not None else [dict(p) for p in conn.execute("SELECT id, state, url FROM jrd_photos WHERE item_id=?", (d['id'],))]
    return d


def _validate(sec, x):
    if sec not in ('raw', 'eqp', 'asset'):
        raise ValueError('اختر الخانة')
    if not t_(x.get('name')):
        raise ValueError('اكتب اسم الصنف/القطعة')
    if not t_(x.get('description')):
        raise ValueError('الوصف إلزامي')
    try:
        q = float(x.get('qty') or 0)
    except Exception:
        raise ValueError('الكمية غير صحيحة')
    if q <= 0:
        raise ValueError('الكمية لازم تكون أكبر من صفر')
    if sec == 'asset':
        if not t_(x.get('code')):
            raise ValueError('اختر نوع الصنف')
        counts = {s: int(float((x.get('counts') or {}).get(s) or 0)) for s in STATES}
        if sum(counts.values()) != int(q):
            raise ValueError(f'مجموع الحالات ({sum(counts.values())}) لازم يساوي الكمية ({int(q)})')
        return q, counts
    return q, {}


def handle(h, conn, method, path, query, data, ctx, send_json):
    if not path.startswith('/api/jard/'):
        return False
    q1 = lambda k: (query.get(k) or [''])[0] if isinstance(query.get(k), list) else (query.get(k) or '')
    try:
        if path == '/api/jard/boot' and method == 'GET':
            cats = [dict(r) for r in conn.execute("SELECT * FROM jrd_categories WHERE active=1 ORDER BY code")]
            names = {s: [r[0] for r in conn.execute("SELECT DISTINCT name FROM jrd_items WHERE section=? AND deleted=0 ORDER BY name", (s,))]
                     for s in ('raw', 'eqp', 'asset')}
            locs = [r[0] for r in conn.execute("SELECT DISTINCT location FROM jrd_items WHERE location<>'' ORDER BY location")]
            send_json({'cats': cats, 'states': STATES, 'statesEn': STATES_EN, 'units': UNITS, 'eqpStates': EQP_STATES, 'wh': WH,
                       'names': names, 'locations': locs, 'canWrite': bool(_can_write(ctx)), 'isSuper': bool(ctx['perms'].get('is_super')), 'me': _me(ctx)})
            return True
        if path == '/api/jard/list' and method == 'GET':
            sql, p = "SELECT * FROM jrd_items WHERE deleted=0", []
            for f in ('section', 'wh'):
                if q1(f):
                    sql += f" AND {f}=?"; p.append(q1(f))
            if q1('q'):
                sql += " AND (name LIKE ? OR description LIKE ? OR code LIKE ? OR name_en LIKE ?)"; p += ['%' + q1('q') + '%'] * 4
            rows = conn.execute(sql + " ORDER BY at DESC LIMIT 2000", p).fetchall()
            ph = {}
            for r in conn.execute("SELECT id, item_id, state, url FROM jrd_photos"):
                ph.setdefault(r['item_id'], []).append({'id': r['id'], 'state': r['state'], 'url': r['url']})
            send_json([_item_out(conn, r, ph.get(r['id'], [])) for r in rows])
            return True
        if path == '/api/jard/save' and method == 'POST':
            if not _can_write(ctx):
                raise PermissionError('ما عندك صلاحية الجرد')
            sec, x = data.get('section'), data
            q, counts = _validate(sec, x)
            iid = t_(x.get('id'))
            old = conn.execute("SELECT * FROM jrd_items WHERE id=? AND deleted=0", (iid,)).fetchone() if iid else None
            new_photos = x.get('photos') or []
            have = conn.execute("SELECT COUNT(*) FROM jrd_photos WHERE item_id=?", (iid,)).fetchone()[0] if old else 0
            if sec in ('raw', 'eqp') and have + len(new_photos) < 1:
                raise ValueError('صورة واحدة على الأقل')
            if sec in ('raw', 'eqp') and have + len(new_photos) > 4:
                raise ValueError('الحد 4 صور')
            if sec == 'asset' and not old:
                need = [s for s in STATES if counts.get(s)]
                got = {ph.get('state') for ph in new_photos}
                miss = [s for s in need if s not in got]
                if miss:
                    raise ValueError('صورة لكل حالة: ناقص ' + '، '.join(miss))
                if sum(1 for ph in new_photos if ph.get('state') == 'إضافية') > 3:
                    raise ValueError('الحد 3 صور إضافية')
            iid = iid if old else ('J' + datetime.datetime.now().strftime('%y%m%d%H%M%S') + uuid.uuid4().hex[:3])
            vals = dict(section=sec, wh=x.get('wh') if x.get('wh') in WH else 'factory', code=t_(x.get('code')) if sec == 'asset' else '',
                        name=t_(x.get('name'))[:200], name_en=t_(x.get('name_en'))[:200], qty=q, unit=t_(x.get('unit')) if sec == 'raw' else '',
                        serial=t_(x.get('serial')) if sec == 'eqp' else '', state=t_(x.get('state')) if sec == 'eqp' else '',
                        counts_json=json.dumps(counts, ensure_ascii=False), location=t_(x.get('location'))[:120],
                        description=t_(x.get('description'))[:1000], notes=t_(x.get('notes'))[:1000], updated=now())
            if old:
                conn.execute("UPDATE jrd_items SET " + ", ".join(f"{k}=?" for k in vals) + " WHERE id=?", list(vals.values()) + [iid])
            else:
                vals.update(id=iid, by_name=_me(ctx), at=now())
                conn.execute(f"INSERT INTO jrd_items ({','.join(vals)}) VALUES ({','.join('?' * len(vals))})", list(vals.values()))
            for ph in new_photos:
                url = _save_img(ph.get('data'), vals['code'] or sec)
                conn.execute("INSERT INTO jrd_photos (id, item_id, state, url, by_name, at) VALUES (?,?,?,?,?,?)",
                             ('p' + uuid.uuid4().hex[:14], iid, t_(ph.get('state')) or 'إضافية', url, _me(ctx), now()))
            conn.commit()
            send_json({'success': True, 'id': iid})
            return True
        if path == '/api/jard/delete' and method == 'POST':
            if not (ctx['perms'].get('is_super') or ac.can(ctx['perms'], 'inventory', 'delete')):
                raise PermissionError('الحذف للإدارة')
            conn.execute("UPDATE jrd_items SET deleted=1, updated=? WHERE id=?", (now(), data.get('id')))
            conn.commit()
            send_json({'success': True})
            return True
        if path == '/api/jard/photo-delete' and method == 'POST':
            if not _can_write(ctx):
                raise PermissionError('ما عندك صلاحية الجرد')
            conn.execute("DELETE FROM jrd_photos WHERE id=?", (data.get('id'),))
            conn.commit()
            send_json({'success': True})
            return True
        if path == '/api/jard/stats' and method == 'GET':
            if not ctx['perms'].get('is_super'):
                raise PermissionError('اللوحة للإدارة')
            out = {'wh': {}, 'byType': [], 'eqpIssues': [], 'team': []}
            for wh in WH:
                a = conn.execute("SELECT counts_json, qty FROM jrd_items WHERE section='asset' AND wh=? AND deleted=0", (wh,)).fetchall()
                st = {s: 0 for s in STATES}
                for r in a:
                    for s, n in json.loads(r['counts_json'] or '{}').items():
                        st[s] = st.get(s, 0) + n
                out['wh'][wh] = {'entries': len(a), 'pieces': int(sum(r['qty'] or 0 for r in a)), 'states': st}
            out['raw'] = conn.execute("SELECT COUNT(*), COUNT(DISTINCT name) FROM jrd_items WHERE section='raw' AND deleted=0").fetchone()[1]
            out['eqp'] = conn.execute("SELECT COALESCE(SUM(qty),0) FROM jrd_items WHERE section='eqp' AND deleted=0").fetchone()[0]
            out['byType'] = [dict(r) for r in conn.execute("""SELECT c.sub, c.type, i.code, SUM(i.qty) qty, COUNT(*) n FROM jrd_items i
                LEFT JOIN jrd_categories c ON c.code=i.code WHERE i.section='asset' AND i.deleted=0 GROUP BY i.code ORDER BY qty DESC""")]
            out['eqpIssues'] = [dict(r) for r in conn.execute("SELECT name, serial, state, qty, location FROM jrd_items WHERE section='eqp' AND deleted=0 AND state<>'تعمل'")]
            out['team'] = [dict(r) for r in conn.execute("SELECT by_name, COUNT(*) n, MAX(at) last FROM jrd_items WHERE deleted=0 GROUP BY by_name ORDER BY n DESC")]
            send_json(out)
            return True
    except PermissionError as e:
        send_json({'error': str(e)}, 403)
        return True
    except ValueError as e:
        send_json({'error': str(e)}, 400)
        return True
    return False
