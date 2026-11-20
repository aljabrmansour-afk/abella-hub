"""
إدارة العمليات داخل المنصة (/operations)
========================================
نفس شاشات تطبيق «أبيلا — إدارة العمليات» (Apps Script)، والدخول من حساب المنصة بدل الرابط + الرمز.
المنطق والبيانات باقية في التطبيق (جدول «أبيلا — إدارة العمليات») حتى ننقلها لاحقاً، والمنصة:
  - تمرّر كل استدعاء للتطبيق عبر الجسر باسم الشخص في فريق العمليات (ربط حساب المنصة ← اسم الفريق)
  - تحدّث الأوامر من العقود كل 15 دقيقة (sync)
  - تاخذ نسخة من الأوامر والمهام (ops_orders / ops_tasks) وتربطها بمناسبات المنصة برقم العرض/العقد/التشغيل
"""
import json, os, re, time, datetime, urllib.request
import wpgen_routes as wpg

OPS_URL = os.environ.get('OPS_BRIDGE_URL') or \
    'https://script.google.com/macros/s/AKfycbzhon7MabzL4HnM_ZM3RMjTwp_58yAvqBklsyklEAnktN9KrxxWqjByLE9zULws80BMtA/exec'

# أسماء الحسابات الأولية في المنصة ← أسماء فريق إدارة العمليات
DEFAULT_MAP = {'mansour': 'منصور الجبر', 'mihaf': 'ميهاف', 'shareefa': 'شريفة', 'moaaz': 'معاذ', 'faris': 'فارس',
               'abdulqayum': 'عبدالقيوم'}


def init_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ops_orders (
        quote_code TEXT PRIMARY KEY, contract_code TEXT, operation_order TEXT, client TEXT, event_type TEXT, path TEXT,
        venue TEXT, location TEXT, expected_date TEXT, confirmed_date TEXT, classification TEXT, ops_owner TEXT,
        contract_status TEXT, closed TEXT, data_json TEXT, synced_at TEXT);
    CREATE TABLE IF NOT EXISTS ops_tasks (
        id TEXT PRIMARY KEY, quote_code TEXT, dept TEXT, stage TEXT, title TEXT, status TEXT, assignee TEXT,
        data_json TEXT, synced_at TEXT);
    CREATE INDEX IF NOT EXISTS idx_ops_tasks_q ON ops_tasks(quote_code);
    """)


def bridge(fn, timeout=120, **kw):
    body = json.dumps({'fn': fn, 'nonce': wpg.new_nonce(), **kw}).encode()
    req = urllib.request.Request(OPS_URL, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode('utf-8')
    try:
        return json.loads(txt)
    except Exception:
        raise RuntimeError('جسر إدارة العمليات غير مفعّل')


def ops_name(conn, user):
    try:
        m = json.loads(wpg._setting(conn, 'ops_name_map') or '{}')
    except Exception:
        m = {}
    if user['username'] in m:
        return m[user['username']]
    if user['username'] in DEFAULT_MAP:
        return DEFAULT_MAP[user['username']]
    team = [r[0] for r in conn.execute("SELECT DISTINCT assignee FROM ops_tasks WHERE assignee<>''")]
    first = (user.get('full_name') or '').split(' — ')[0].split()[0] if user.get('full_name') else ''
    return first or user['username']


def sync(conn, log=print):
    """تحديث الأوامر من العقود داخل التطبيق ثم أخذ نسخة"""
    r = bridge('sync')
    if not r.get('ok'):
        raise RuntimeError(r.get('error'))
    x = bridge('export')
    if not x.get('ok'):
        raise RuntimeError(x.get('error'))
    d = x['data']
    now = datetime.datetime.now().isoformat(timespec='seconds')
    conn.execute("DELETE FROM ops_orders")
    for o in d.get('orders') or []:
        Q = str(o.get('رقم العرض') or '').strip()
        if not Q:
            continue
        conn.execute("""INSERT OR REPLACE INTO ops_orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (Q, o.get('رقم العقد'), o.get('رقم التشغيل'), o.get('العميل'), o.get('نوع المناسبة'), o.get('المسار'),
                      o.get('المكان'), o.get('الموقع'), o.get('التاريخ المتوقع'), o.get('التاريخ المؤكد'), o.get('التصنيف'),
                      o.get('مسؤول العمليات'), o.get('حالة العقد'), o.get('مغلق'), json.dumps(o, ensure_ascii=False), now))
    conn.execute("DELETE FROM ops_tasks")
    for t in d.get('tasks') or []:
        tid = str(t.get('المعرّف') or '').strip()
        if not tid:
            continue
        conn.execute("INSERT OR REPLACE INTO ops_tasks VALUES (?,?,?,?,?,?,?,?,?)",
                     (tid, t.get('رقم العرض'), t.get('القسم'), t.get('المرحلة'), t.get('العنوان'), t.get('الحالة'),
                      t.get('المسؤول'), json.dumps(t, ensure_ascii=False), now))
    wpg._set(conn, 'ops_team_json', json.dumps(d.get('team') or [], ensure_ascii=False))
    conn.execute("INSERT INTO sync_log (source, status, rows_imported) VALUES ('operations','success',?)",
                 (len(d.get('orders') or []),))
    conn.commit()
    log(f"✓ إدارة العمليات: {len(d.get('orders') or [])} أمر، {len(d.get('tasks') or [])} مهمة")
    return {'orders': len(d.get('orders') or []), 'tasks': len(d.get('tasks') or [])}


def handle(h, conn, method, path, query, data, ctx, send_json):
    if path == '/api/ops/call' and method == 'POST':
        fn = str(data.get('fn') or '')
        if not fn.startswith('api_'):
            fn = 'api_' + fn
        if fn == 'api_logo':
            send_json({'ok': True, 'data': wpg.LOGO})
            return True
        name = ops_name(conn, ctx['user'])
        try:
            r = bridge('call', call=fn, args=data.get('args') or [], **{'as': name})
        except Exception as e:
            r = {'ok': False, 'error': 'تعذّر الاتصال بإدارة العمليات: ' + str(e)}
        if r.get('ok') and fn in ('api_setTask', 'api_addTask', 'api_confirm', 'api_unconfirm', 'api_setOrder', 'api_sync'):
            try:
                sync(conn, log=lambda m: None)
            except Exception:
                pass
        send_json(r)
        return True
    if path == '/api/ops/map' and method == 'POST':
        if not ctx['perms'].get('is_super'):
            send_json({'error': 'للإدارة فقط'}, 403)
            return True
        wpg._set(conn, 'ops_name_map', json.dumps(data.get('map') or {}, ensure_ascii=False))
        conn.commit()
        send_json({'success': True})
        return True
    return False
