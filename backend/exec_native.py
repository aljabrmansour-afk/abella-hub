"""
يوم التنفيذ — داخل المنصة (/execution) بدون Apps Script
=======================================================
نفس تطبيق «أبيلا — يوم التنفيذ» (التايم لاين D-1 / D-Day / D+1، الحالات، التعليقات، الصور واعتمادها، لوحة المتابعة،
الأرشفة عند انتهاء العقد) — والدخول من حساب المنصة.
الأدوار: الإدارة (مدراء المنصة) · مشرف · مدير تشغيل · موظف (بفريقه). تُستنتج من دور الحساب أو تُحدَّد من exn_team.
المناسبات من العقود (أوامر التشغيل O) — والمشروع يرتبط بأمر إدارة العمليات بنفس رقم التشغيل.
"""
import json, os, re, base64, uuid, datetime
from pathlib import Path

ADMIN, SUP, OPS, STAFF = 'الإدارة', 'مشرف', 'مدير تشغيل', 'موظف'
ALL_TEAMS = 'كل الفِرَق'
HUB_ROLE_MAP = {'supervisor': (SUP, ''), 'field': (OPS, ''), 'project_manager': (SUP, ''),
                'warehouse': (STAFF, 'فريق المستودع'), 'warehouse_decor': (STAFF, 'فريق المستودع'),
                'warehouse_acc': (STAFF, 'فريق التنفيذ 2'), 'factory': (STAFF, 'فريق التصميم'),
                'designer': (STAFF, 'فريق التصميم'), 'hospitality': (STAFF, 'فريق الضيافة')}
NO_PERM = 'ما عندك صلاحية لهذا الإجراء — تواصل مع مدير التشغيل'


def init_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS exn_projects (id TEXT PRIMARY KEY, code TEXT, client TEXT, loc TEXT, time TEXT, ops TEXT, sup TEXT,
        d1 TEXT, d0 TEXT, d2 TEXT, status TEXT, created_by TEXT, updated TEXT);
    CREATE TABLE IF NOT EXISTS exn_tasks (id TEXT PRIMARY KEY, pid TEXT, phase TEXT, ord INTEGER, name TEXT, start TEXT, end_ TEXT,
        team TEXT, chk TEXT, note TEXT, status TEXT, tnote TEXT, updated TEXT, by_name TEXT);
    CREATE INDEX IF NOT EXISTS idx_exn_tasks_p ON exn_tasks(pid);
    CREATE TABLE IF NOT EXISTS exn_photos (id TEXT PRIMARY KEY, at TEXT, pid TEXT, tid TEXT, kind TEXT, by_name TEXT, url TEXT,
        approval TEXT DEFAULT 'بانتظار', rcomment TEXT, rby TEXT);
    CREATE TABLE IF NOT EXISTS exn_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, by_name TEXT, pid TEXT, tid TEXT, kind TEXT, detail TEXT);
    CREATE TABLE IF NOT EXISTS exn_team (username TEXT PRIMARY KEY, role TEXT, team TEXT, all_projects INTEGER DEFAULT 0, active TEXT DEFAULT 'نعم');
    """)
    # منصور 2026-11-20: المشرفات ريّان ورضوى — ميهاف وشريفة خارج فريق يوم التنفيذ
    if not conn.execute("SELECT 1 FROM settings WHERE key='exn_seed_sup_v1'").fetchone():
        for u in ('mihaf', 'shareefa'):
            conn.execute("INSERT OR REPLACE INTO exn_team (username, role, team, all_projects, active) VALUES (?, '', '', 0, 'لا')", (u,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('exn_seed_sup_v1', '1')")
        conn.commit()


def now():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%S')


def t_(v):
    return '' if v is None else str(v).strip()


def _name(u):
    return (u.get('full_name') or u['username']).split(' — ')[0].strip()


def staff(conn):
    import access_control as ac
    out = []
    for u in conn.execute("SELECT username, full_name, role, is_active FROM users ORDER BY full_name").fetchall():
        u = dict(u)
        if not u.get('is_active', 1):
            continue
        r = conn.execute("SELECT role, team, all_projects, active FROM exn_team WHERE username=?", (u['username'],)).fetchone()
        if r and t_(r['active']) == 'لا':
            continue
        if ac.get_perms(conn, u['role']).get('is_super'):
            role, team, allp = ADMIN, '', 0
        elif r and t_(r['role']):
            role, team, allp = t_(r['role']), t_(r['team']), int(r['all_projects'] or 0)
        else:
            role, team = HUB_ROLE_MAP.get(u['role'] or '', ('', ''))
            allp = 0
        if not role:
            continue
        out.append({'name': _name(u), 'username': u['username'], 'role': role, 'team': 'كل المشاريع' if allp else team, 'all': bool(allp)})
    return out


def me_of(conn, user):
    return next((s for s in staff(conn) if s['username'] == user['username']), None)


def log(conn, by, pid, tid, kind, detail=''):
    conn.execute("INSERT INTO exn_log (at, by_name, pid, tid, kind, detail) VALUES (?,?,?,?,?,?)", (now(), by, pid or '', tid or '', kind, detail or ''))


def closed_codes(conn):
    """أوامر التشغيل اللي عقدها منتهي/ملغي → مشاريعها مؤرشفة"""
    s = set()
    for r in conn.execute("SELECT O, closed, contract_state FROM opn_orders"):
        st = t_(r['contract_state'])
        if t_(r['O']) and (t_(r['closed']) == 'نعم' or any(x in st for x in ('منته', 'ملغ', 'مرفوض'))):
            s.add(t_(r['O']))
    for r in conn.execute("SELECT operation_order, status FROM sheet_contracts WHERE operation_order<>''"):
        if 'منته' in t_(r['status']):
            s.add(t_(r['operation_order']))
    return s


def can_see(u, p, tasks):
    if not u:
        return False
    if u['role'] == ADMIN:
        return True
    if u['role'] == SUP:
        return t_(p['sup']) == u['name']
    if u['role'] == OPS:
        return u['all'] or t_(p['ops']) == u['name']
    return bool(u['team']) and any(t_(t['team']) == u['team'] for t in tasks)


def can_manage(u):
    return bool(u) and u['role'] in (ADMIN, SUP)


def can_edit_row(u, p, archived):
    if not u:
        return False
    if u['role'] == ADMIN:
        return True
    if archived:
        return False
    return u['role'] == SUP and t_(p['sup']) == u['name']


def can_update_task(u, team, p):
    if not u:
        return False
    if u['role'] in (ADMIN, SUP):
        return True
    if u['role'] == OPS:
        return t_(p['ops']) == u['name']
    return team == ALL_TEAMS or (u['team'] and team == u['team'])


def _proj(conn, pid):
    r = conn.execute("SELECT * FROM exn_projects WHERE id=?", (pid,)).fetchone()
    return dict(r) if r else None


def _tasks(conn, pid):
    return [dict(r) for r in conn.execute("SELECT * FROM exn_tasks WHERE pid=? ORDER BY ord", (pid,))]


def _photo_out(f, code=''):
    return {'id': f['id'], 'taskId': f['tid'], 'pid': f['pid'], 'projectId': f['pid'], 'code': code, 'kind': f['kind'], 'by': f['by_name'],
            'url': f['url'], 'thumb': f['url'], 'at': f['at'], 'approval': f['approval'] or 'بانتظار',
            'rcomment': f['rcomment'] or '', 'rby': f['rby'] or ''}


def events(conn, used):
    out, seen = [], set()
    rows = conn.execute("""SELECT O code, client, location loc, COALESCE(NULLIF(C,''), E) date FROM opn_orders
                           WHERE COALESCE(O,'')<>'' AND COALESCE(closed,'')<>'نعم' AND COALESCE(is_test,'')<>'1' ORDER BY date""").fetchall()
    rows += conn.execute("""SELECT operation_order code, customer_name client, venue loc, COALESCE(actual_date, expected_date) date
                            FROM sheet_contracts WHERE operation_order LIKE 'O%' AND COALESCE(status,'') NOT LIKE '%منته%'""").fetchall()
    for r in rows:
        c = t_(r['code'])
        if c and c not in used and c not in seen:
            seen.add(c)
            out.append({'code': c, 'client': t_(r['client']), 'loc': t_(r['loc']), 'date': t_(r['date'])[:10], 'time': ''})
    today = now()[:10]
    up = sorted([e for e in out if e['date'] >= today], key=lambda e: e['date'])
    past = sorted([e for e in out if e['date'] < today], key=lambda e: e['date'], reverse=True)
    return up + past


def _save_photo(code, b64, mime):
    base = Path(os.environ['DATA_DIR']) / 'uploads' if os.environ.get('DATA_DIR') else Path(__file__).resolve().parent / 'uploads'
    safe = re.sub(r'[^\w\-]', '_', code or 'misc')
    d = base / 'exec' / safe
    d.mkdir(parents=True, exist_ok=True)
    ext = '.png' if 'png' in (mime or '') else '.jpg'
    name = uuid.uuid4().hex[:16] + ext
    (d / name).write_bytes(base64.b64decode(b64))
    return f'/uploads/exec/{safe}/{name}'


def call(conn, ctx, p):
    u = me_of(conn, ctx['user'])
    act = p.get('action')
    if act == 'bootstrap':
        st = staff(conn)
        projects_all = [dict(r) for r in conn.execute("SELECT * FROM exn_projects ORDER BY d0 DESC")]
        used = {t_(x['code']) for x in projects_all}
        closed = closed_codes(conn)
        n = now()
        projects, vis = [], {}
        for pr in projects_all:
            ts = _tasks(conn, pr['id'])
            if not can_see(u, pr, ts):
                continue
            dates = {'d1': pr['d1'], 'd0': pr['d0'], 'd2': pr['d2']}
            late = sum(1 for t in ts if (t['status'] or 'idle') != 'done' and dates.get(t['phase']) and t['end_']
                       and f"{dates[t['phase']]}T{t['end_']}:00" < n)
            projects.append({'id': pr['id'], 'code': pr['code'], 'client': pr['client'], 'loc': pr['loc'], 'time': pr['time'],
                             'ops': pr['ops'], 'sup': pr['sup'], 'dates': dates, 'approved': pr['status'] == 'معتمد',
                             'archived': t_(pr['code']) in closed, 'total': len(ts), 'done': sum(1 for t in ts if t['status'] == 'done'), 'late': late})
            vis[pr['id']] = pr['code']
        recent = [_photo_out(dict(f), vis.get(f['pid'], '')) for f in conn.execute("SELECT * FROM exn_photos ORDER BY at DESC LIMIT 200") if f['pid'] in vis][:12]
        return {'ok': True, 'me': u['name'] if u else _name(ctx['user']), 'staff': [{k: s[k] for k in ('name', 'role', 'team')} for s in st],
                'events': events(conn, used), 'projects': projects, 'recentPhotos': recent, 'serverTime': n}
    if not u:
        return {'ok': False, 'error': 'حسابك غير مضاف لفريق يوم التنفيذ — راجع الإدارة'}
    if act == 'project':
        pr = _proj(conn, p.get('id'))
        if not pr:
            return {'ok': False, 'error': 'المشروع غير موجود'}
        ts = _tasks(conn, pr['id'])
        if not can_see(u, pr, ts):
            return {'ok': False, 'error': NO_PERM}
        photos = [_photo_out(dict(f), pr['code']) for f in conn.execute("SELECT * FROM exn_photos WHERE pid=? ORDER BY at", (pr['id'],))]
        return {'ok': True, 'project': {
            'id': pr['id'], 'code': pr['code'], 'client': pr['client'], 'loc': pr['loc'], 'time': pr['time'], 'ops': pr['ops'], 'sup': pr['sup'],
            'dates': {'d1': pr['d1'], 'd0': pr['d0'], 'd2': pr['d2']}, 'approved': pr['status'] == 'معتمد',
            'archived': t_(pr['code']) in closed_codes(conn),
            'tasks': [{'id': t['id'], 'phase': t['phase'], 'name': t['name'], 'start': t['start'], 'end': t['end_'], 'team': t['team'],
                       'chk': t['chk'], 'note': t['note'] or '', 'status': t['status'] or 'idle', 'tnote': t['tnote'] or ''} for t in ts]},
            'photos': photos, 'serverTime': now()}
    if act == 'saveProject':
        if not can_manage(u):
            return {'ok': False, 'error': NO_PERM}
        pr = p.get('project') or {}
        old = _proj(conn, pr.get('id'))
        if old and not can_edit_row(u, old, t_(old['code']) in closed_codes(conn)):
            return {'ok': False, 'error': NO_PERM}
        d = pr.get('dates') or {}
        conn.execute("INSERT OR REPLACE INTO exn_projects VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (pr['id'], t_(pr.get('code')), t_(pr.get('client')), t_(pr.get('loc')), t_(pr.get('time')), t_(pr.get('ops')), t_(pr.get('sup')),
                      t_(d.get('d1')), t_(d.get('d0')), t_(d.get('d2')), 'معتمد', (old or {}).get('created_by') or u['name'], now()))
        conn.execute("DELETE FROM exn_tasks WHERE pid=?", (pr['id'],))
        for i, t in enumerate(pr.get('tasks') or []):
            conn.execute("INSERT INTO exn_tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (t['id'], pr['id'], t.get('phase'), i + 1, t.get('name'), t.get('start'), t.get('end'), t.get('team'), t.get('chk'),
                          t.get('note') or '', t.get('status') or 'idle', t.get('tnote') or '', now(), u['name']))
        log(conn, u['name'], pr['id'], '', 'تعديل' if old else 'إنشاء',
            ('تعديل' if old else 'إنشاء') + f" تايم لاين {pr.get('code')} — {pr.get('client')} ({len(pr.get('tasks') or [])} مهمة)")
        conn.commit()
        return {'ok': True, 'id': pr['id']}
    if act == 'deleteProject':
        pr = _proj(conn, p.get('id'))
        if not pr:
            return {'ok': False, 'error': 'المشروع غير موجود'}
        if not can_manage(u) or not can_edit_row(u, pr, t_(pr['code']) in closed_codes(conn)):
            return {'ok': False, 'error': NO_PERM}
        conn.execute("DELETE FROM exn_tasks WHERE pid=?", (pr['id'],))
        conn.execute("DELETE FROM exn_photos WHERE pid=?", (pr['id'],))
        conn.execute("DELETE FROM exn_projects WHERE id=?", (pr['id'],))
        log(conn, u['name'], pr['id'], '', 'حذف', f"حذف المشروع {pr['code']} — {pr['client']}")
        conn.commit()
        return {'ok': True}
    if act in ('setStatus', 'setNote', 'addPhoto'):
        t = conn.execute("SELECT * FROM exn_tasks WHERE id=?", (p.get('taskId'),)).fetchone()
        pr = _proj(conn, p.get('projectId'))
        if not t or not pr:
            return {'ok': False, 'error': 'المهمة غير موجودة'}
        if t_(pr['code']) in closed_codes(conn) and u['role'] != ADMIN:
            return {'ok': False, 'error': 'المشروع مؤرشف — العقد منتهي'}
        if not can_update_task(u, t_(t['team']), pr):
            return {'ok': False, 'error': NO_PERM}
        if act == 'setStatus':
            conn.execute("UPDATE exn_tasks SET status=?, updated=?, by_name=? WHERE id=?", (t_(p.get('status')), now(), u['name'], t['id']))
            log(conn, u['name'], pr['id'], t['id'], 'حالة', f"{t['name']} ← {p.get('status')}")
            conn.commit()
            return {'ok': True}
        if act == 'setNote':
            conn.execute("UPDATE exn_tasks SET tnote=?, updated=?, by_name=? WHERE id=?", (str(p.get('note') or '')[:2000], now(), u['name'], t['id']))
            log(conn, u['name'], pr['id'], t['id'], 'تعليق', f"{t['name']}: {p.get('note')}")
            conn.commit()
            return {'ok': True}
        b64 = str(p.get('base64') or '')
        if not b64 or len(b64) > 12_000_000:
            return {'ok': False, 'error': 'الصورة غير صالحة أو كبيرة جداً'}
        url = _save_photo(pr['code'], b64, p.get('mime'))
        fid = 'f' + uuid.uuid4().hex[:14]
        conn.execute("INSERT INTO exn_photos (id, at, pid, tid, kind, by_name, url) VALUES (?,?,?,?,?,?,?)",
                     (fid, now(), pr['id'], t['id'], p.get('kind') or 'توثيق', u['name'], url))
        log(conn, u['name'], pr['id'], t['id'], 'صورة', f"📸 {p.get('kind') or 'توثيق'} — {t['name']}")
        conn.commit()
        return {'ok': True, 'url': url, 'thumb': url, 'id': fid}
    if act == 'reviewPhoto':
        pr = _proj(conn, p.get('projectId'))
        if not (u['role'] == ADMIN or (pr and u['role'] == SUP and t_(pr['sup']) == u['name'])):
            return {'ok': False, 'error': NO_PERM}
        f = conn.execute("SELECT * FROM exn_photos WHERE id=?", (p.get('photoId'),)).fetchone()
        if not f:
            return {'ok': False, 'error': 'الصورة غير موجودة'}
        conn.execute("UPDATE exn_photos SET approval=?, rcomment=?, rby=? WHERE id=?", (p.get('verdict'), p.get('comment') or '', u['name'], f['id']))
        log(conn, u['name'], f['pid'], f['tid'], 'اعتماد صورة',
            ('✓ اعتماد صورة' if p.get('verdict') == 'معتمد' else '✗ رفض صورة') + (' — ' + p['comment'] if p.get('comment') else ''))
        conn.commit()
        return {'ok': True}
    if act == 'updates':
        since = t_(p.get('since'))
        vis = None
        if u['role'] != ADMIN:
            vis = {pr['id'] for pr in (dict(r) for r in conn.execute("SELECT * FROM exn_projects")) if can_see(u, pr, _tasks(conn, pr['id']))}
        rows = conn.execute("SELECT * FROM exn_log WHERE at>? ORDER BY id DESC LIMIT 200", (since,)).fetchall()
        ups = [{'at': r['at'], 'by': r['by_name'], 'pid': r['pid'], 'tid': r['tid'], 'kind': r['kind'], 'detail': r['detail']}
               for r in rows if vis is None or (r['pid'] and r['pid'] in vis)][:30][::-1]
        return {'ok': True, 'updates': ups, 'serverTime': now()}
    if act == 'team':
        if u['role'] != ADMIN:
            return {'ok': False, 'error': NO_PERM}
        return {'ok': True, 'staff': staff(conn)}
    if act == 'setMember':
        if u['role'] != ADMIN:
            return {'ok': False, 'error': NO_PERM}
        role = t_(p.get('role'))
        if role and role not in (SUP, OPS, STAFF):
            return {'ok': False, 'error': 'دور غير صحيح'}
        conn.execute("INSERT OR REPLACE INTO exn_team VALUES (?,?,?,?,?)",
                     (t_(p.get('username')), role, t_(p.get('team')), 1 if p.get('all') else 0, 'لا' if p.get('inactive') else 'نعم'))
        conn.commit()
        return {'ok': True}
    return {'ok': False, 'error': 'إجراء غير معروف: ' + str(act)}


def ops_summary(conn, code):
    """ملخص يوم التنفيذ لأمر تشغيل (لشاشة إدارة العمليات)"""
    pr = conn.execute("SELECT * FROM exn_projects WHERE code=?", (code,)).fetchone()
    if not pr:
        return None
    ts = _tasks(conn, pr['id'])
    ph = conn.execute("SELECT approval, COUNT(*) FROM exn_photos WHERE pid=? GROUP BY approval", (pr['id'],)).fetchall()
    return {'id': pr['id'], 'total': len(ts), 'done': sum(1 for t in ts if t['status'] == 'done'), 'photos': {r[0]: r[1] for r in ph}}
