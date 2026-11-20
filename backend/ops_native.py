"""
إدارة العمليات — نسخة المنصة الأصلية (بدون Apps Script)
=========================================================
منقولة حرفياً من منطق تطبيق «أبيلا — إدارة العمليات»:
  - الأوامر تُولَّد من العقود (عروض الأسعار اللي لها رقم عقد) — مولّد العقود والمنصة
  - المهام من قالب الشروط والأحكام (TPL) + مهام خطة العمل المعتمدة لكل قسم
  - التاريخ المتوقع E والمؤكد C، نافذة ±7، مستعجل >21 يوم، 9 بوابات، تقويم 60 يوم
  - الأدوار: الإدارة · إدارة العمليات · قسم (بأقسام) — تُستنتج من دور الحساب في المنصة أو تُحدَّد من «الفريق»
  - كل قسم يشوف مهامه وقناته فقط

الواجهة نفسها (operations.html) تنادي /api/ops/call بأسماء الدوال api_* .
"""
import json, re, time, uuid, datetime

DEPTS = ['العمليات', 'المصنع', 'الكماليات', 'الورد', 'الضيافة', 'المشتريات', 'التشغيل']
ROLE_ADMIN, ROLE_OPS, ROLE_DEPT = 'الإدارة', 'إدارة العمليات', 'قسم'
TODO, DOING, DONE, STUCK, CANCEL = 'لم يبدأ', 'جارٍ', 'منجز', 'متعثر', 'ملغاة'
STATUSES = [TODO, DOING, DONE, STUCK]
CLOSED_STATES = ['منتهي', 'ملغي', 'ملغى', 'ملغاة', 'مرفوض']
DAY = 86400000

# دور الحساب في المنصة ← الدور/القسم الافتراضي في إدارة العمليات
HUB_ROLE_MAP = {
    'project_manager': (ROLE_OPS, []), 'planner': (ROLE_DEPT, ['العمليات']), 'designer': (ROLE_DEPT, ['العمليات']),
    'factory': (ROLE_DEPT, ['المصنع']), 'warehouse_acc': (ROLE_DEPT, ['الكماليات']), 'warehouse_decor': (ROLE_DEPT, ['المصنع']),
    'warehouse': (ROLE_DEPT, ['التشغيل']), 'hospitality': (ROLE_DEPT, ['الضيافة']), 'purchasing': (ROLE_DEPT, ['المشتريات']),
    'field': (ROLE_DEPT, ['التشغيل']), 'supervisor': (ROLE_DEPT, ['التشغيل']),
}

TPL = [
    dict(k='plan', d='العمليات', t='مراجعة خطة العمل واعتمادها', a='E', b=-21, w=-28, tm='12:00', ph='pre'),
    dict(k='fac-start', d='المصنع', t='بدء التصنيع', a='E', b=-14, w=-21, tm='09:00', ph='pre'),
    dict(k='buy-dur', d='المشتريات', t='إغلاق المشتريات المعمّرة (الكماليات والديكور والورد الصناعي)', a='E', b=-10, w=-14, tm='17:00', ph='pre'),
    dict(k='fac-done', d='المصنع', t='اكتمال التصنيع والفحص النهائي', a='E', b=-7, w=-10, tm='17:00', ph='pre'),
    dict(k='amen', d='الكماليات', t='تجهيز الكماليات وفحصها', a='E', b=-7, w=-7, tm='17:00', ph='pre'),
    dict(k='art', d='الورد', t='تجهيز الورد الصناعي', a='E', b=-7, w=-7, tm='17:00', ph='pre'),
    dict(k='pay2', d='العمليات', t='تحصيل الدفعة الثانية والتأمين', a='E', b=-7, w=-14, tm='12:00', ph='pre'),
    dict(k='window', d='العمليات', t='بدء نافذة التأكيد (±7 أيام) — التواصل مع العميل', a='E', b=-7, tm='10:00', ph='pre', birthOnly=True),
    dict(k='pay-check', d='العمليات', t='التحقق من السداد الكامل والتأمين قبل التركيب', a='C', b=-1, w=-1, tm='17:00', ph='post'),
    dict(k='staff', d='الضيافة', t='تأكيد طاقم الضيافة والصبابات', a='C', b=-1, w=-2, tm='15:00', ph='post'),
    dict(k='hosp-order', d='الضيافة', t='طلب أصناف الضيافة من الموردين', a='C', b=-1, w=-2, tm='16:00', ph='post'),
    dict(k='nat-order', d='الورد', t='طلب الورد الطبيعي', a='C', b=-1, w=-2, tm='15:00', ph='post'),
    dict(k='buy-fresh', d='المشتريات', t='مشتريات الورد الطبيعي والضيافة', a='C', b=-1, w=-1, tm='18:00', ph='post'),
    dict(k='load', d='التشغيل', t='التحميل من المستودع وفق قائمة التحقق', a='C', b=0, w=0, tm='07:30', ph='post'),
    dict(k='empty', d='التشغيل', t='التأكد من تفريغ الجناح من أثاث المستشفى', a='C', b=0, tm='10:00', ph='post', venue='مستشفى', birthOnly=True),
    dict(k='nat-arr', d='الورد', t='تنسيق الورد الطبيعي في الموقع', a='C', b=0, w=0, tm='15:00', ph='post'),
    dict(k='hosp-setup', d='الضيافة', t='تجهيز ركن الضيافة', a='C', b=0, w=0, tm='16:30', ph='post'),
    dict(k='install', d='التشغيل', t='التركيب والتجهيز (8 ص – 7 م)', a='C', b=0, w=0, tm='18:30', ph='post'),
    dict(k='handover', d='التشغيل', t='التسليم للعميل', a='C', b=0, w=0, tm='19:00', ph='post'),
    dict(k='hosp-run', d='الضيافة', t='تشغيل الضيافة (5 ع – 11 م)', a='C', b=0, w=0, tm='23:00', ph='post'),
    dict(k='dismantle', d='التشغيل', t='فك الديكور', a='C', b=0, w=1, tm='23:30', ph='post', home=dict(b=1, tm='03:00'), fixedTm='03:00'),
    dict(k='return', d='التشغيل', t='الإرجاع للمستودع والجرد', a='C', b=1, w=1, tm='14:00', ph='post'),
    dict(k='refund', d='العمليات', t='رد التأمين للعميل (خلال 14 يوم عمل)', a='C', biz=14, tm='12:00', ph='post', insurance=True),
]
TPL_BY = {x['k']: x for x in TPL}
GATES = [('contract', 'العقد'), ('plan', 'الخطة'), ('buy', 'المشتريات'), ('ready', 'الجاهزية'), ('confirm', 'التأكيد'),
         ('pay', 'السداد'), ('load', 'التحميل'), ('handover', 'التسليم'), ('close', 'الإرجاع')]

ORDER_COLS = ['Q', 'B', 'O', 'client', 'type', 'path', 'venue', 'location', 'E', 'birth', 'C', 'place', 'confirm_at', 'cls',
              'rush_paid', 'owner', 'contract_state', 'deposit', 'final', 'ins', 'no_ins', 'plan_ver', 'closed', 'notes',
              'updated', 'by_name', 'is_test']
TASK_COLS = ['id', 'Q', 'dept', 'phase', 'key', 'title', 'detail', 'anchor', 'days', 'tm', 'custom', 'status', 'owner',
             'note', 'updated', 'by_name', 'src', 'ord']


def init_tables(conn):
    conn.executescript(f"""
    CREATE TABLE IF NOT EXISTS opn_orders ({', '.join(c + (' TEXT PRIMARY KEY' if c == 'Q' else ' TEXT') for c in ORDER_COLS)});
    CREATE TABLE IF NOT EXISTS opn_tasks ({', '.join(c + (' TEXT PRIMARY KEY' if c == 'id' else ' TEXT') for c in TASK_COLS)});
    CREATE INDEX IF NOT EXISTS idx_opn_tasks_q ON opn_tasks(Q);
    CREATE TABLE IF NOT EXISTS opn_comments (id TEXT PRIMARY KEY, Q TEXT, ch TEXT, task TEXT, from_name TEXT, role TEXT, text TEXT, at TEXT);
    CREATE TABLE IF NOT EXISTS opn_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, user TEXT, Q TEXT, action TEXT, details TEXT);
    CREATE TABLE IF NOT EXISTS opn_seen (user TEXT, k TEXT, at TEXT, PRIMARY KEY(user, k));
    CREATE TABLE IF NOT EXISTS opn_team (username TEXT PRIMARY KEY, role TEXT, depts TEXT, active TEXT DEFAULT 'نعم');
    CREATE TABLE IF NOT EXISTS opn_blocked (d TEXT PRIMARY KEY, reason TEXT);
    """)
    # طلب منصور 2026-11-20: إخراج ميهاف وشريفة من فريق إدارة العمليات (مرة واحدة — يُرجَعون من «الفريق»)
    if not conn.execute("SELECT 1 FROM settings WHERE key='opn_seed_removed_v1'").fetchone():
        for u in ('mihaf', 'shareefa'):
            conn.execute("INSERT OR REPLACE INTO opn_team (username, role, depts, active) VALUES (?, '', '', 'لا')", (u,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('opn_seed_removed_v1', '1')")
        conn.commit()


# ───────────────────────── أدوات التاريخ (ساعة الرياض كقيمة UTC — نفس التطبيق) ─────────────────────────
def t_(v):
    return '' if v is None else str(v).strip()


def yes_(v):
    if v is True:
        return True
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v > 0
    return t_(v) in ('نعم', 'TRUE', 'true', 'مدفوع', 'تم', '✓', '1')


def now_r():
    return int(time.time() * 1000) + 3 * 3600000


def fmt_d(ms):
    return datetime.datetime.utcfromtimestamp(ms / 1000).strftime('%Y-%m-%d')


def today_s():
    return fmt_d(now_r())


def stamp():
    return datetime.datetime.utcfromtimestamp(now_r() / 1000).strftime('%Y-%m-%d %H:%M')


def D(s):
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', t_(s))
    if not m:
        return None
    return int(datetime.datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=datetime.timezone.utc).timestamp() * 1000)


def add_d(s, n):
    return fmt_d(D(s) + n * DAY)


def diff_d(a, b):
    return round((D(a) - D(b)) / DAY)


def dow(s):  # 0 = الأحد … 5 الجمعة · 6 السبت (مثل JS)
    return (datetime.datetime.utcfromtimestamp(D(s) / 1000).weekday() + 1) % 7


def is_biz(s):
    return dow(s) not in (5, 6)


def add_biz(s, n):
    d, c = s, 0
    while c < n:
        d = add_d(d, 1)
        if is_biz(d):
            c += 1
    return d


def biz_between(a, b):
    c, d = 0, a
    while d < b:
        d = add_d(d, 1)
        if is_biz(d):
            c += 1
    return c


def at_(s, tm):
    p = t_(tm or '00:00').split(':')
    return D(s) + int(p[0] or 0) * 3600000 + int((p[1] if len(p) > 1 else 0) or 0) * 60000


def parse_date(v):
    s = t_(v)
    if not s:
        return ''
    m = re.search(r'(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})', s)
    if m:
        return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.search(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})', s)
    if m:
        return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    return ''


def uid(p):
    return p + uuid.uuid4().hex[:12]


# ───────────────────────── تخزين ─────────────────────────
def _orders(conn, where='', p=()):
    return [dict(r) for r in conn.execute("SELECT * FROM opn_orders " + where, p).fetchall()]


def _tasks(conn, where='', p=()):
    return [dict(r) for r in conn.execute("SELECT * FROM opn_tasks " + where, p).fetchall()]


def _ins(conn, table, cols, obj):
    conn.execute(f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                 [None if obj.get(c) is None else str(obj.get(c)) for c in cols])


def _upd_order(conn, o):
    _ins(conn, 'opn_orders', ORDER_COLS, o)


def _upd_task(conn, t):
    _ins(conn, 'opn_tasks', TASK_COLS, t)


def log_(conn, user, Q, action, details=''):
    conn.execute("INSERT INTO opn_log (at, user, Q, action, details) VALUES (?,?,?,?,?)", (stamp(), user, Q, action, details or ''))


def _setting(conn, k, d=None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    return r[0] if r and r[0] is not None else d


def settings_(conn):
    try:
        cap = int(_setting(conn, 'ops_capacity', '2') or 2)
    except Exception:
        cap = 2
    try:
        warn = int(_setting(conn, 'ops_warn_hours', '48') or 48)
    except Exception:
        warn = 48
    return {'cap': cap, 'warnH': warn}


def blocked_(conn):
    return {r[0]: r[1] or '' for r in conn.execute("SELECT d, reason FROM opn_blocked")}


# ───────────────────────── الهوية والصلاحيات ─────────────────────────
def _name(user):
    return (user.get('full_name') or user['username']).split(' — ')[0].strip()


def member(conn, user, is_super):
    r = conn.execute("SELECT role, depts, active FROM opn_team WHERE username=?", (user['username'],)).fetchone()
    if r and t_(r['active']) == 'لا':
        raise PermissionError('حسابك موقوف في إدارة العمليات — راجع الإدارة')
    if is_super:
        role, depts = ROLE_ADMIN, []
    elif r and t_(r['role']):
        role, depts = t_(r['role']), [d for d in re.split(r'[،,]', t_(r['depts'])) if t_(d) in DEPTS]
        depts = [t_(d) for d in depts]
    else:
        role, depts = HUB_ROLE_MAP.get(user.get('role') or '', ('', []))
    if role not in (ROLE_ADMIN, ROLE_OPS) and not (role == ROLE_DEPT and depts):
        raise PermissionError('لم يُحدَّد دورك أو قسمك في إدارة العمليات بعد — راجع الإدارة')
    return {'name': _name(user), 'username': user['username'], 'role': role, 'depts': depts,
            'isAdmin': role == ROLE_ADMIN, 'isOps': role in (ROLE_ADMIN, ROLE_OPS)}


def pub(me):
    return {k: me[k] for k in ('name', 'role', 'depts', 'isAdmin', 'isOps')}


def need_ops(me):
    if not me['isOps']:
        raise PermissionError('هذا الإجراء لإدارة العمليات فقط')


def can_task(me, t):
    return me['isOps'] or t_(t['dept']) in me['depts']


def can_channel(me, ch):
    return me['isOps'] or ch in me['depts']


# ───────────────────────── الأوامر من العقود ─────────────────────────
def _type_label(etype, vkind):
    if etype == 'newborn':
        return 'استقبال مولود — ' + ('منزل' if vkind == 'home' else 'مستشفى')
    if etype == 'exhibition':
        return 'معرض'
    if etype == 'wedding':
        return 'زواج'
    return 'مناسبة خاصة'


def tpl_applies(tp, o):
    birth = t_(o['path']) == 'ولادة'
    if tp.get('birthOnly') and not birth:
        return False
    if not birth and tp.get('w') is None and tp.get('biz') is None:
        return False
    if tp.get('venue') and t_(o['venue']) != tp['venue']:
        return False
    if tp.get('insurance') and t_(o['no_ins']) == 'نعم':
        return False
    return True


def tpl_task(tp, Q, n):
    return dict(id=uid('T'), Q=Q, dept=tp['d'], phase=tp['ph'], key='T:' + tp['k'], title=tp['t'], detail='', anchor=tp['a'],
                days='', tm='', custom='', status=TODO, owner='', note='', updated=stamp(), by_name='النظام', src='قالب', ord=n)


def sync_orders(conn, log=print):
    """يحدّث الأوامر من العقود (عروض لها رقم عقد) ويولّد مهام القالب للأوامر الجديدة"""
    rows = conn.execute("""
        SELECT q.quote_code Q, q.contract_code B, COALESCE(NULLIF(q.gen_operation_order,''), e.operation_order) O, q.client_name client,
               q.event_type, q.venue_kind, q.venue_name loc, q.expected_date E, q.confirmed_date conf, q.gen_status, q.status,
               q.source, q.gen_paid_flags flags, q.gen_remaining rem, q.insurance ins_amt, COALESCE(q.is_test,0) is_test,
               e.total_price ev_total, e.paid_amount ev_paid, e.insurance_amount ev_ins
        FROM quotes q LEFT JOIN events e ON e.id = q.event_id
        WHERE COALESCE(q.contract_code,'') <> ''""").fetchall()
    existing = {o['Q']: o for o in _orders(conn)}
    added = changed_n = 0
    for r in rows:
        r = dict(r)
        Q = t_(r['Q'])
        st = t_(r['gen_status']) or ('ملغي' if r['status'] in ('cancelled', 'rejected') else 'عقد')
        closed = st in CLOSED_STATES or any(x in st for x in ('منته', 'ملغ', 'مرفوض'))
        typ = _type_label(r['event_type'], r['venue_kind'])
        birth = r['event_type'] == 'newborn'
        try:
            flags = json.loads(r['flags'] or '{}')
        except Exception:
            flags = {}
        if r['source'] == 'generator':
            final = yes_(flags.get('final')) or (r['rem'] is not None and t_(r['rem']) != '' and float(r['rem'] or 0) <= 0 and bool(r['flags']))
            ins = yes_(flags.get('insurance'))
        else:
            final = bool(r['ev_total']) and float(r['ev_paid'] or 0) >= float(r['ev_total'] or 0) - 0.01
            ins = final and float(r['ins_amt'] or 0) > 0
        fields = dict(Q=Q, B=t_(r['B']), O=t_(r['O']), client=t_(r['client']), type=typ, path='ولادة' if birth else 'ثابت',
                      venue='مستشفى' if (birth and r['venue_kind'] != 'home') or 'مستشفى' in t_(r['loc']) else ('منزل' if birth else 'قاعة/موقع'),
                      location=t_(r['loc']), E=parse_date(r['E']), contract_state=st, deposit='نعم',
                      final='نعم' if final else '', ins='نعم' if ins else '',
                      no_ins='نعم' if (r['event_type'] in ('special', 'wedding') and not float(r['ins_amt'] or 0)) or (r['ins_amt'] is not None and float(r['ins_amt'] or 0) == 0) else '',
                      is_test='1' if r['is_test'] else '')
        conf = parse_date(r['conf'])
        ex = existing.get(Q)
        if ex:
            ch = False
            for k, v in fields.items():
                if t_(ex.get(k)) != t_(v):
                    ex[k] = v; ch = True
            if closed and t_(ex.get('closed')) != 'نعم':
                ex['closed'] = 'نعم'; ch = True
            if conf and not t_(ex.get('C')):
                ex['C'] = conf; ex['cls'] = ex.get('cls') or 'عادي'; ch = True
            if ch:
                _upd_order(conn, ex); changed_n += 1
        else:
            if closed:
                continue
            o = dict(fields, closed='', updated=stamp(), by_name='مزامنة')
            if conf and birth:
                o['C'], o['cls'] = conf, 'عادي'
            _upd_order(conn, o)
            for n, tp in enumerate(TPL):
                if tpl_applies(tp, o):
                    _upd_task(conn, tpl_task(tp, Q, n))
            added += 1
    # الخطط المعتمدة اللي ما استُوردت بعد → توزيعها على الأقسام
    for p in conn.execute("SELECT quote_code, approved_version FROM wpg_plans WHERE COALESCE(approved_version,0)>0").fetchall():
        o = conn.execute("SELECT plan_ver FROM opn_orders WHERE Q=?", (p[0],)).fetchone()
        if o is not None and not t_(o[0]).startswith(f"{p[1]} (معتمدة)"):
            try:
                import_plan(conn, p[0], 'النظام')
            except Exception as e:
                log(f'⚠ توزيع خطة {p[0]}: {e}')
    conn.commit()
    log(f'✓ إدارة العمليات (المنصة): {added} أمر جديد، {changed_n} محدّث')
    return {'added': added, 'updated': changed_n}


# ───────────────────────── المواعيد والحالة ─────────────────────────
def due_(task, o):
    birth = t_(o['path']) == 'ولادة'
    E, Cf = t_(o.get('E')), t_(o.get('C'))
    custom = t_(task.get('custom'))
    if custom:
        p = custom.split(' ')
        d = parse_date(p[0])
        if d:
            tm = p[1] if len(p) > 1 else '17:00'
            return {'ms': at_(d, tm), 'date': d, 'time': tm, 'tentative': False}
    anchor = t_(task.get('anchor')) or 'E'
    tentative = False
    if anchor == 'C':
        base = Cf or E
        tentative = birth and not Cf
    else:
        base = E
    if not base:
        return {'ms': None, 'date': '', 'time': '', 'tentative': True}
    key = t_(task.get('key'))
    if key.startswith('T:') and key[2:] in TPL_BY:
        tp = TPL_BY[key[2:]]
        if tp.get('biz'):
            d = add_biz(base, tp['biz'])
            return {'ms': at_(d, tp['tm']), 'date': d, 'time': tp['tm'], 'tentative': tentative}
        days = tp['b'] if birth else (tp['w'] if tp.get('w') is not None else tp['b'])
        tm = tp['tm']
        if birth and tp.get('home') and t_(o.get('venue')) != 'مستشفى':
            days, tm = tp['home']['b'], tp['home']['tm']
        if not birth and tp.get('fixedTm'):
            tm = tp['fixedTm']
    else:
        try:
            days = int(float(task.get('days') or 0))
        except Exception:
            days = 0
        tm = t_(task.get('tm')) or '17:00'
    d = add_d(base, days)
    return {'ms': at_(d, tm), 'date': d, 'time': tm, 'tentative': tentative}


def classify(E, birth, exec_):
    r = {'cls': 'عادي', 'dev': 0, 'rushEligible': False, 'window': True, 'notes': []}
    if not E or not birth:
        return r
    r['dev'] = diff_d(birth, E)
    if abs(r['dev']) <= 7:
        return r
    r['window'] = False
    if r['dev'] < -21:
        r['rushEligible'] = True
        r['notes'].append('الولادة قبل المتوقع بأكثر من 3 أسابيع: إما تنفيذ مستعجل برسوم 10% + الضريبة، أو إعادة جدولة')
    else:
        r['notes'].append('الولادة خارج نافذة ±7 أيام: للشركة إعادة الجدولة خلال 2–4 أيام عمل من التاريخ الفعلي')
    r['cls'] = 'إعادة جدولة'
    if exec_:
        b = biz_between(birth, exec_)
        if exec_ < birth:
            r['notes'].append('تاريخ التنفيذ قبل تاريخ الولادة!')
        elif b < 2 or b > 4:
            r['notes'].append(f'تنبيه: موعد التنفيذ بعد {b} يوم عمل من الولادة (الشرط 2–4 أيام عمل)')
    return r


def compute_order(conn, o, tasks, now, st=None, blk=None):
    st = st or settings_(conn)
    blk = blk if blk is not None else blocked_(conn)
    birth = t_(o['path']) == 'ولادة'
    E, Cf = t_(o.get('E')), t_(o.get('C'))
    today = fmt_d(now)
    rush = t_(o.get('cls')) == 'مستعجل'
    rush_paid = t_(o.get('rush_paid')) == 'نعم'
    live = [t for t in tasks if t_(t['status']) != CANCEL]
    late = soon = 0
    T = []
    for t in live:
        du = due_(t, o)
        done = t_(t['status']) == DONE
        locked = t_(t['phase']) == 'post' and rush and not rush_paid
        is_late = not done and not du['tentative'] and not locked and du['ms'] is not None and du['ms'] < now
        is_soon = not done and not is_late and not du['tentative'] and du['ms'] is not None and du['ms'] - now < st['warnH'] * 3600000
        late += is_late
        soon += is_soon
        T.append({'t': t, 'due': du, 'done': done, 'late': is_late, 'soon': is_soon, 'locked': locked})
    by = lambda k: next((x for x in T if t_(x['t']['key']) == 'T:' + k), None)
    all_done = lambda arr: len(arr) > 0 and all(x['done'] for x in arr)
    pre = [x for x in T if t_(x['t']['phase']) == 'pre']
    ready = all(x['done'] for x in pre) if pre else False
    ret = by('return')
    closed = t_(o.get('closed')) == 'نعم' or bool(ret and ret['done'])
    pay_ok = t_(o.get('final')) == 'نعم' and (t_(o.get('ins')) == 'نعم' or t_(o.get('no_ins')) == 'نعم')
    buy_pre = [x for x in T if t_(x['t']['dept']) == 'المشتريات' and t_(x['t']['phase']) == 'pre']
    bd = lambda k: (by(k) or {}).get('due')
    g = {
        'contract': {'done': t_(o.get('deposit')) == 'نعم'},
        'plan': {'done': bool(by('plan') and by('plan')['done']), 'due': bd('plan')},
        'buy': {'done': all_done(buy_pre), 'due': bd('buy-dur')},
        'ready': {'done': ready, 'due': {'ms': at_(add_d(E, -7), '17:00'), 'date': add_d(E, -7)} if E else None},
        'confirm': {'done': (not birth) or bool(Cf), 'due': {'ms': at_(add_d(E, 7), '13:00'), 'date': add_d(E, 7)} if birth and E else None},
        'pay': {'done': pay_ok, 'due': bd('pay2')},
        'load': {'done': bool(by('load') and by('load')['done']), 'due': bd('load')},
        'handover': {'done': bool(by('handover') and by('handover')['done']), 'due': bd('handover')},
        'close': {'done': closed, 'due': bd('return')},
    }
    current = None
    gates = []
    for k, title in GATES:
        x = g[k]
        state = 'done' if x['done'] else 'open'
        du = x.get('due')
        if not x['done'] and du and not du.get('tentative') and du.get('ms') is not None and du['ms'] < now:
            state = 'late'
        if not x['done'] and not current:
            current = k
        gates.append({'k': k, 't': title, 'state': state, 'due': du['date'] if du else ''})
    if closed:
        stage = 'مغلق'
    elif Cf and today > Cf:
        stage = 'بعد التنفيذ'
    elif Cf and today == Cf:
        stage = 'يوم التنفيذ'
    elif Cf:
        stage = 'مؤكد'
    elif ready:
        stage = 'جاهز – بانتظار التأكيد'
    else:
        stage = 'تحضير'
    alerts = []
    if birth and not Cf and E and not closed:
        if today >= add_d(E, -7) and not ready:
            alerts.append('دخل نافذة التأكيد وهو غير جاهز')
        if today > add_d(E, 7):
            alerts.append('تجاوز نافذة ±7 أيام بدون تأكيد')
    if rush and not rush_paid:
        alerts.append('مستعجل — رسوم التجهيز غير مسددة (مهام ما بعد التأكيد مقفلة)')
    if Cf and not pay_ok and not closed and diff_d(Cf, today) <= 1:
        alerts.append('السداد الكامل/التأمين غير مكتمل قبل التركيب')
    if Cf and blk.get(Cf):
        alerts.append('التاريخ المؤكد يوم محجوب: ' + blk[Cf])
    health = 'green'
    if late or alerts:
        health = 'red'
    elif soon or (birth and not Cf and E and today >= add_d(E, -7)):
        health = 'amber'
    if closed:
        health = 'grey'
    return {
        'Q': t_(o['Q']), 'B': t_(o.get('B')), 'O': t_(o.get('O')), 'client': t_(o.get('client')), 'type': t_(o.get('type')),
        'path': 'ولادة' if birth else 'ثابت', 'venue': t_(o.get('venue')), 'location': t_(o.get('location')), 'E': E, 'C': Cf,
        'birth': t_(o.get('birth')), 'place': t_(o.get('place')), 'cls': t_(o.get('cls')), 'rushPaid': rush_paid,
        'owner': t_(o.get('owner')), 'notes': t_(o.get('notes')), 'contractState': t_(o.get('contract_state')),
        'pay': {'deposit': g['contract']['done'], 'final': t_(o.get('final')) == 'نعم', 'ins': t_(o.get('ins')) == 'نعم', 'noIns': t_(o.get('no_ins')) == 'نعم'},
        'planVer': t_(o.get('plan_ver')), 'closed': closed, 'stage': stage, 'health': health, 'alerts': alerts, 'gates': gates,
        'current': current, 'late': late, 'soon': soon, 'total': len(T), 'doneN': sum(1 for x in T if x['done']),
        'eventDate': Cf or E, 'tentative': birth and not Cf, 'test': t_(o.get('is_test')) == '1', '_T': T}


def task_out(x):
    t = x['t']
    try:
        order = int(float(t.get('ord') or 0))
    except Exception:
        order = 0
    return {'id': t_(t['id']), 'Q': t_(t['Q']), 'dept': t_(t['dept']), 'phase': t_(t['phase']), 'key': t_(t['key']),
            'title': t_(t['title']), 'detail': t_(t['detail']), 'status': t_(t['status']) or TODO, 'owner': t_(t['owner']),
            'note': t_(t['note']), 'updated': t_(t['updated']), 'by': t_(t['by_name']), 'src': t_(t['src']), 'order': order,
            'due': x['due']['date'], 'time': x['due']['time'], 'dueMs': x['due']['ms'], 'tentative': x['due']['tentative'],
            'late': x['late'], 'soon': x['soon'], 'locked': x['locked'], 'done': x['done'], 'custom': t_(t['custom'])}


def strip(c):
    return {k: v for k, v in c.items() if k != '_T'}


def load(conn):
    orders = _orders(conn)
    byQ = {}
    for t in _tasks(conn):
        byQ.setdefault(t_(t['Q']), []).append(t)
    return orders, byQ


def unread(conn, me):
    seen = {r[0]: r[1] for r in conn.execute("SELECT k, at FROM opn_seen WHERE user=?", (me['username'],))}
    out = {}
    for c in conn.execute("SELECT Q, ch, from_name, at FROM opn_comments"):
        if not can_channel(me, c['ch']) or c['from_name'] == me['name']:
            continue
        key = c['Q'] + '|' + c['ch']
        if t_(c['at']) > seen.get(key, ''):
            out[key] = out.get(key, 0) + 1
    return out


def calendar(conn, cards, days):
    st, blk, today = settings_(conn), blocked_(conn), today_s()
    out = []
    for i in range(days):
        d = add_d(today, i)
        conf, win = [], []
        for c in cards:
            if c.get('closed'):
                continue
            if c.get('C'):
                if c['C'] == d:
                    conf.append(c['Q'])
            elif c.get('path') == 'ولادة' and c.get('E') and add_d(c['E'], -7) <= d <= add_d(c['E'], 7):
                win.append(c['Q'])
            elif c.get('path') != 'ولادة' and c.get('E') == d:
                conf.append(c['Q'])
        out.append({'d': d, 'dow': dow(d), 'conf': conf, 'win': win, 'blocked': blk.get(d, ''), 'cap': st['cap']})
    return out


def overview(conn, me):
    orders, byQ = load(conn)
    now, st, blk = now_r(), settings_(conn), blocked_(conn)
    un = unread(conn, me)
    cards = []
    for o in orders:
        Q = t_(o['Q'])
        c = compute_order(conn, o, byQ.get(Q, []), now, st, blk)
        if me['isOps']:
            c['unread'] = sum(v for k, v in un.items() if k.startswith(Q + '|'))
            dl = {}
            for x in c['_T']:
                e = dl.setdefault(t_(x['t']['dept']), {'n': 0, 'done': 0, 'late': 0})
                e['n'] += 1; e['done'] += x['done']; e['late'] += x['late']
            c['deptLoad'] = dl
            cards.append(strip(c))
        else:
            mine = [x for x in c['_T'] if t_(x['t']['dept']) in me['depts']]
            if not mine or c['closed']:
                continue
            cards.append({'Q': c['Q'], 'O': c['O'], 'client': c['client'], 'venue': c['venue'], 'location': c['location'],
                          'E': c['E'], 'C': c['C'], 'eventDate': c['eventDate'], 'tentative': c['tentative'], 'path': c['path'],
                          'stage': c['stage'], 'place': c['place'] if c['C'] else '', 'locked': c['cls'] == 'مستعجل' and not c['rushPaid'],
                          'tasks': [task_out(x) for x in mine], 'unread': sum(un.get(c['Q'] + '|' + d, 0) for d in me['depts'])})
    cards.sort(key=lambda a: (1 if a.get('closed') else 0, str(a.get('eventDate') or '9')))
    res = {'cards': cards}
    if me['isOps']:
        res['calendar'] = calendar(conn, cards, 60)
    return res


# ───────────────────────── خطة العمل → مهام الأقسام ─────────────────────────
def _J(a):
    return '، '.join(str(x) for x in (a or []) if x)


def plan_tasks(P, o):
    birth = t_(o['path']) == 'ولادة'
    out = []

    def add(key, dept, phase, anchor, days, tm, title, detail):
        out.append({'key': 'P:' + key, 'dept': dept, 'phase': phase, 'anchor': anchor, 'days': days, 'tm': tm,
                    'title': re.sub(r'\s+', ' ', t_(title)), 'detail': t_(detail)})

    def jn(*a):
        return ' · '.join(str(x) for x in a if x)

    def q(r):
        try:
            return float(r.get('qty') or 0)
        except Exception:
            return 0
    pre_days, buy_days = (-7, -10) if birth else (-10, -14)
    for r in P.get('decor') or []:
        add('d' + str(r.get('id')), 'المصنع', 'pre', 'E', pre_days, '17:00', 'تصنيع/تجهيز: ' + t_(r.get('item')) + (f" × {r.get('qty')}" if q(r) > 1 else ''),
            jn(r.get('code'), r.get('area') and 'المنطقة: ' + str(r['area']), _J(r.get('finish')) and 'التشطيب: ' + _J(r.get('finish')),
               _J(r.get('paints')) and 'البوية: ' + _J(r.get('paints')), r.get('led') and 'إضاءة ليد', r.get('nameOn') and 'عليه الاسم', r.get('desc')))
    for r in P.get('amen') or []:
        add('m' + str(r.get('id')), 'الكماليات', 'pre', 'E', pre_days, '17:00', 'تجهيز: ' + t_(r.get('nameAr')) + (f" × {r.get('qty')}" if q(r) > 1 else ''),
            jn(r.get('code'), r.get('area') and 'المنطقة: ' + str(r['area']), r.get('color') and 'اللون: ' + str(r['color']), r.get('desc')))
    for r in P.get('artificial') or []:
        add('a' + str(r.get('id')), 'الورد', 'pre', 'E', pre_days, '17:00', 'ورد صناعي: ' + (t_(r.get('area')) or 'تنسيق'),
            jn(_J(r.get('types')), _J(r.get('colors')), r.get('density'), r.get('method'), q(r) > 1 and f"العدد {r.get('qty')}", r.get('desc')))
    for r in P.get('natural') or []:
        add('n' + str(r.get('id')), 'الورد', 'post', 'C', 0, '15:00', 'ورد طبيعي: ' + (t_(r.get('area')) or 'تنسيق'),
            jn(_J(r.get('types')), _J(r.get('colors')), r.get('density'), r.get('method'), q(r) > 1 and f"العدد {r.get('qty')}", r.get('desc')))
    for r in P.get('hosp') or []:
        add('h' + str(r.get('id')), 'الضيافة', 'post', 'C', -1, '16:00',
            ('طاقم: ' if r.get('sec') == 'staff' else 'ضيافة: ') + t_(r.get('item')) + (f" × {r.get('qty')} {t_(r.get('unit'))}" if r.get('qty') else ''),
            jn(r.get('supplier') and 'المورد: ' + str(r['supplier']), r.get('kg') and f"{r['kg']} كجم/وحدة", r.get('desc')))
    skip = P.get('buySkip') or {}

    def buy(key, sec, item, qty, unit, sup, desc, perishable):
        if skip.get(key):
            return
        add('b' + key, 'المشتريات', 'post' if perishable else 'pre', 'C' if perishable else 'E', -1 if perishable else buy_days,
            '14:00' if perishable else '17:00', f"شراء ({sec}): " + t_(item) + (f" × {qty} {t_(unit)}" if qty else ''),
            jn(sup and 'المورد: ' + str(sup), desc))
    for r in P.get('natural') or []:
        if r.get('buy'):
            buy('n' + str(r.get('id')), 'ورد طبيعي', 'ورد طبيعي — ' + (_J(r.get('types')) or 'يحدد'), r.get('qty'), '', '', jn(r.get('area'), _J(r.get('colors'))), True)
    for r in P.get('artificial') or []:
        if r.get('buy'):
            buy('a' + str(r.get('id')), 'ورد صناعي', 'ورد صناعي — ' + (_J(r.get('types')) or 'يحدد'), r.get('qty'), '', '', jn(r.get('area'), _J(r.get('colors'))), False)
    for r in P.get('hosp') or []:
        if r.get('buy'):
            buy('h' + str(r.get('id')), 'الضيافة', r.get('item'), r.get('qty'), r.get('unit'), r.get('supplier'), r.get('desc'), True)
    for r in P.get('amen') or []:
        if r.get('buy'):
            buy('m' + str(r.get('id')), 'الكماليات', r.get('nameAr'), r.get('qty'), '', '', jn(r.get('code'), r.get('color'), r.get('desc')), False)
    for r in P.get('decor') or []:
        if r.get('buy'):
            buy('d' + str(r.get('id')), 'الديكور', r.get('item'), r.get('qty'), '', '', jn(r.get('code'), _J(r.get('paints')), r.get('desc')), False)
    for r in P.get('buyManual') or []:
        if not skip.get('x' + str(r.get('id'))):
            add('bx' + str(r.get('id')), 'المشتريات', 'pre', 'E', buy_days, '17:00',
                'شراء: ' + t_(r.get('item')) + (f" × {r.get('qty')} {t_(r.get('unit'))}" if r.get('qty') else ''),
                jn(r.get('supplier') and 'المورد: ' + str(r['supplier']), r.get('desc')))
    b = P.get('baby') or {}
    if b.get('nameAr') or b.get('nameEn'):
        add('baby', 'المصنع', 'post', 'C', -1, '18:00', 'الاسم والاستيكر: ' + ' / '.join(x for x in (b.get('nameAr'), b.get('nameEn')) if x),
            jn(b.get('font') and 'الخط: ' + str(b['font']), b.get('notes')))
    return out


def read_plan(conn, Q):
    m = conn.execute("SELECT status, version, approved_version FROM wpg_plans WHERE quote_code=?", (Q,)).fetchone()
    if not m:
        return None
    want = int(m['approved_version'] or 0) or int(m['version'] or 0)
    v = conn.execute("SELECT data_json FROM wpg_versions WHERE quote_code=? AND v=?", (Q, want)).fetchone()
    if not v:
        return None
    return {'status': m['status'], 'version': want, 'approved': bool(m['approved_version']) and want == int(m['approved_version']),
            'plan': json.loads(v[0])}


def import_plan(conn, Q, by):
    R = read_plan(conn, Q)
    if not R:
        raise ValueError('لا توجد خطة عمل محفوظة لهذا الأمر')
    o = conn.execute("SELECT * FROM opn_orders WHERE Q=?", (Q,)).fetchone()
    if not o:
        raise ValueError('الأمر غير موجود في إدارة العمليات')
    o = dict(o)
    items = plan_tasks(R['plan'], o)
    tasks = _tasks(conn, "WHERE Q=? AND key LIKE 'P:%'", (Q,))
    by_key = {t['key']: t for t in tasks}
    seen, added, upd, cancelled = set(), 0, 0, 0
    for n, it in enumerate(items):
        seen.add(it['key'])
        ex = by_key.get(it['key'])
        if ex:
            if t_(ex['title']) != it['title'] or t_(ex['detail']) != it['detail'] or t_(ex['status']) == CANCEL:
                ex.update(title=it['title'], detail=it['detail'], updated=stamp(), by_name=f"خطة v{R['version']}")
                if t_(ex['status']) == CANCEL:
                    ex['status'] = TODO
                _upd_task(conn, ex); upd += 1
        else:
            _upd_task(conn, dict(id=uid('T'), Q=Q, dept=it['dept'], phase=it['phase'], key=it['key'], title=it['title'],
                                 detail=it['detail'], anchor=it['anchor'], days=it['days'], tm=it['tm'], custom='', status=TODO,
                                 owner='', note='', updated=stamp(), by_name=f"خطة v{R['version']}", src='خطة العمل', ord=100 + n))
            added += 1
    for t in tasks:
        if t['key'] not in seen and t_(t['status']) != CANCEL:
            t.update(status=CANCEL, note=f"أُلغي البند في نسخة الخطة {R['version']}")
            _upd_task(conn, t); cancelled += 1
    if R['approved']:
        pt = conn.execute("SELECT * FROM opn_tasks WHERE Q=? AND key='T:plan'", (Q,)).fetchone()
        if pt and t_(pt['status']) != DONE:
            pt = dict(pt); pt.update(status=DONE, note=f"معتمدة في مولّد الخطط (نسخة {R['version']})", updated=stamp())
            _upd_task(conn, pt)
    o.update(plan_ver=f"{R['version']} ({'معتمدة' if R['approved'] else 'مسودة'})", updated=stamp(), by_name=by)
    _upd_order(conn, o)
    log_(conn, by, Q, 'استيراد الخطة', f"نسخة {R['version']} · جديد {added} · محدّث {upd} · ملغى {cancelled}")
    return {'version': R['version'], 'approved': R['approved'], 'added': added, 'updated': upd, 'cancelled': cancelled}


# ───────────────────────── API (نفس دوال التطبيق) ─────────────────────────
def _order_or_fail(conn, Q):
    o = conn.execute("SELECT * FROM opn_orders WHERE Q=?", (t_(Q),)).fetchone()
    if not o:
        raise ValueError('الأمر غير موجود')
    return dict(o)


def _team(conn):
    """كل حسابات المنصة النشطة مع دورها في إدارة العمليات"""
    import access_control as ac
    out = []
    for u in conn.execute("SELECT id, username, full_name, role, is_active FROM users ORDER BY full_name").fetchall():
        u = dict(u)
        if not u.get('is_active', 1):
            continue
        sup = bool(ac.get_perms(conn, u['role']).get('is_super'))
        r = conn.execute("SELECT role, depts, active FROM opn_team WHERE username=?", (u['username'],)).fetchone()
        if sup:
            role, depts, src = ROLE_ADMIN, '', 'مدير في المنصة'
        elif r and t_(r['role']):
            role, depts, src = t_(r['role']), t_(r['depts']), 'محدد'
        else:
            role, dl = HUB_ROLE_MAP.get(u['role'] or '', ('', []))
            depts, src = '، '.join(dl), 'من دور الحساب' if role else ''
        out.append({'username': u['username'], 'name': _name(u), 'hubRole': u['role'], 'role': role, 'depts': depts,
                    'active': not (r and t_(r['active']) == 'لا'), 'src': src, 'super': sup})
    return out


def call(conn, ctx, fn, args):
    me = member(conn, ctx['user'], bool(ctx['perms'].get('is_super')))
    a = list(args or [])
    if fn in ('api_boot', 'api_refresh', 'api_sync'):
        if fn == 'api_sync':
            need_ops(me)
            sync_orders(conn, log=lambda m: None)
        res = {'now': now_r(), **overview(conn, me)}
        if fn == 'api_boot':
            res.update(me=pub(me), depts=DEPTS, statuses=STATUSES, settings=settings_(conn), native=True)
        return res
    if fn in ('api_pinState', 'api_setPin', 'api_login', 'api_logout'):
        return {'name': me['name'], 'state': 'معيّن'}
    if fn == 'api_order':
        Q = t_(a[0])
        o = _order_or_fail(conn, Q)
        c = compute_order(conn, o, _tasks(conn, "WHERE Q=?", (Q,)), now_r())
        tasks = [task_out(x) for x in c['_T'] if can_task(me, x['t'])]
        if not me['isOps'] and not tasks:
            raise PermissionError('لا توجد لك مهام في هذا الأمر')
        tasks.sort(key=lambda x: (x['dueMs'] or 0, x['order']))
        comments = [{'id': r['id'], 'ch': r['ch'], 'task': r['task'], 'from': r['from_name'], 'role': r['role'], 'text': r['text'], 'at': r['at']}
                    for r in conn.execute("SELECT * FROM opn_comments WHERE Q=? ORDER BY at", (Q,)) if can_channel(me, r['ch'])]
        card = strip(c)
        if not me['isOps']:
            for f in ('gates', 'alerts', 'pay', 'notes', 'owner', 'birth', 'cls', 'contractState', 'B', 'planVer'):
                card.pop(f, None)
            card['locked'] = c['cls'] == 'مستعجل' and not c['rushPaid']
            if not c['C']:
                card['place'] = ''
        else:
            card['classify'] = classify(c['E'], c['birth'], c['C']) if c['path'] == 'ولادة' and c['birth'] else None
            team = _team(conn)
            card['ops'] = [m['name'] for m in team if m['role'] in (ROLE_OPS, ROLE_ADMIN) and m['active']]
            dp = {}
            for m in team:
                if not m['active']:
                    continue
                for d in re.split(r'[،,]', m['depts'] or ''):
                    if t_(d):
                        dp.setdefault(t_(d), []).append(m['name'])
            card['deptPeople'] = dp
        return {'order': card, 'tasks': tasks, 'comments': comments,
                'channels': ['داخلي'] + [d for d in DEPTS if d != 'العمليات'] if me['isOps'] else me['depts']}
    if fn == 'api_setTask':
        tid, patch = t_(a[0]), (a[1] if len(a) > 1 else {}) or {}
        t = conn.execute("SELECT * FROM opn_tasks WHERE id=?", (tid,)).fetchone()
        if not t:
            raise ValueError('المهمة غير موجودة')
        t = dict(t)
        if not can_task(me, t):
            raise PermissionError('هذه المهمة ليست من قسمك')
        o = conn.execute("SELECT * FROM opn_orders WHERE Q=?", (t['Q'],)).fetchone()
        o = dict(o) if o else None
        locked = t_(t['phase']) == 'post' and o and t_(o['cls']) == 'مستعجل' and t_(o['rush_paid']) != 'نعم'
        changes = []
        if patch.get('status') is not None:
            s = t_(patch['status'])
            if s not in STATUSES and not (me['isOps'] and s == CANCEL):
                raise ValueError('حالة غير صحيحة')
            if locked and s != TODO:
                raise ValueError('مقفلة: التنفيذ المستعجل بانتظار سداد الرسوم')
            if t_(t['phase']) == 'post' and o and t_(o['path']) == 'ولادة' and not t_(o['C']) and s == DONE and not me['isOps']:
                raise ValueError('لا تبدأ تحضيرات ما بعد التأكيد قبل تأكيد الموعد ورقم الجناح/العنوان')
            t['status'] = s; changes.append('الحالة: ' + s)
        if patch.get('note') is not None:
            t['note'] = str(patch['note'])[:1000]; changes.append('ملاحظة')
        if patch.get('owner') is not None:
            t['owner'] = t_(patch['owner'])[:60]; changes.append('المسؤول: ' + t['owner'])
        if me['isOps']:
            if patch.get('due') is not None:
                p = t_(patch['due'])
                if p and not parse_date(p.split(' ')[0]):
                    raise ValueError('صيغة الموعد: YYYY-MM-DD HH:mm')
                t['custom'] = p; changes.append('الموعد: ' + (p or 'تلقائي'))
            if patch.get('title') is not None and t_(patch['title']):
                t['title'] = t_(patch['title'])[:200]
            if patch.get('detail') is not None:
                t['detail'] = str(patch['detail'])[:2000]
            if patch.get('dept') is not None and t_(patch['dept']) in DEPTS:
                t['dept'] = t_(patch['dept']); changes.append('القسم: ' + t['dept'])
        t.update(updated=stamp(), by_name=me['name'])
        _upd_task(conn, t)
        log_(conn, me['name'], t['Q'], 'تحديث مهمة', t_(t['title']) + ' — ' + '، '.join(changes))
        conn.commit()
        return True
    if fn == 'api_addTask':
        need_ops(me)
        Q, x = t_(a[0]), (a[1] if len(a) > 1 else {}) or {}
        if t_(x.get('dept')) not in DEPTS:
            raise ValueError('اختر القسم')
        if not t_(x.get('title')):
            raise ValueError('اكتب عنوان المهمة')
        due = t_(x.get('due'))
        if not parse_date(due.split(' ')[0]):
            raise ValueError('حدد الموعد')
        _upd_task(conn, dict(id=uid('T'), Q=Q, dept=t_(x['dept']), phase='post' if x.get('phase') == 'post' else 'pre',
                             key='M:' + str(int(time.time() * 1000)), title=t_(x['title'])[:200], detail=str(x.get('detail') or '')[:2000],
                             anchor='E', days='', tm='', custom=due, status=TODO, owner=t_(x.get('owner')), note='',
                             updated=stamp(), by_name=me['name'], src='يدوي', ord=999))
        log_(conn, me['name'], Q, 'إضافة مهمة', t_(x['dept']) + ': ' + t_(x['title']))
        conn.commit()
        return True
    if fn == 'api_confirm':
        need_ops(me)
        Q, x = t_(a[0]), (a[1] if len(a) > 1 else {}) or {}
        ex = parse_date(x.get('exec'))
        birth = parse_date(x.get('birth')) or ex
        if not ex:
            raise ValueError('حدد تاريخ التنفيذ')
        if not t_(x.get('place')):
            raise ValueError('اكتب رقم الجناح أو العنوان — لا تبدأ أي تحضيرات بدونه')
        o = _order_or_fail(conn, Q)
        c = classify(t_(o['E']), birth, ex)
        cls = 'مستعجل' if c['rushEligible'] and t_(x.get('mode')) == 'مستعجل' else c['cls']
        warn = list(c['notes'])
        blk = blocked_(conn)
        if blk.get(ex):
            warn.append('التاريخ يوم محجوب: ' + blk[ex])
        now_s = stamp()
        if ex == today_s() or (ex == add_d(today_s(), 1) and now_s[11:] > '13:00'):
            warn.append('تأكيد متأخر عن المهلة (قبل 1:00 م من اليوم السابق)')
        o.update(birth=birth, C=ex, place=t_(x['place'])[:200], confirm_at=now_s, cls=cls, updated=now_s, by_name=me['name'])
        _upd_order(conn, o)
        # التاريخ المؤكد في العرض والمناسبة داخل المنصة
        conn.execute("UPDATE quotes SET confirmed_date=? WHERE quote_code=?", (ex, Q))
        conn.execute("UPDATE events SET actual_date=? WHERE id=(SELECT event_id FROM quotes WHERE quote_code=?)", (ex, Q))
        log_(conn, me['name'], Q, 'تأكيد الموعد', f"الولادة {birth} · التنفيذ {ex} · {cls}" + (' · ' + ' / '.join(warn) if warn else ''))
        conn.commit()
        return {'cls': cls, 'warnings': warn}
    if fn == 'api_unconfirm':
        need_ops(me)
        Q = t_(a[0])
        o = _order_or_fail(conn, Q)
        o.update(birth='', C='', confirm_at='', cls='', rush_paid='', updated=stamp(), by_name=me['name'])
        _upd_order(conn, o)
        log_(conn, me['name'], Q, 'إلغاء التأكيد', '')
        conn.commit()
        return True
    if fn == 'api_setOrder':
        need_ops(me)
        Q, x = t_(a[0]), (a[1] if len(a) > 1 else {}) or {}
        o = _order_or_fail(conn, Q)
        ch = []
        if x.get('rushPaid') is not None:
            o['rush_paid'] = 'نعم' if x['rushPaid'] else ''; ch.append('رسوم مستعجل: ' + ('مسددة' if x['rushPaid'] else 'غير مسددة'))
        if x.get('owner') is not None:
            o['owner'] = t_(x['owner']); ch.append('المسؤول: ' + o['owner'])
        if x.get('notes') is not None:
            o['notes'] = str(x['notes'])[:2000]; ch.append('ملاحظات')
        if x.get('closed') is not None:
            o['closed'] = 'نعم' if x['closed'] else ''; ch.append('إغلاق' if x['closed'] else 'إعادة فتح')
        if x.get('cls') is not None and t_(x['cls']) in ('عادي', 'إعادة جدولة', 'مستعجل'):
            o['cls'] = t_(x['cls']); ch.append('التصنيف: ' + o['cls'])
        o.update(updated=stamp(), by_name=me['name'])
        _upd_order(conn, o)
        log_(conn, me['name'], Q, 'تحديث الأمر', '، '.join(ch))
        conn.commit()
        return True
    if fn == 'api_comment':
        Q, ch, text = t_(a[0]), t_(a[1] if len(a) > 1 else ''), (a[2] if len(a) > 2 else '')
        task_id = t_(a[3] if len(a) > 3 else '')
        if ch != 'داخلي' and ch not in DEPTS:
            raise ValueError('قناة غير صحيحة')
        if not can_channel(me, ch):
            raise PermissionError('هذه القناة ليست لقسمك')
        if not t_(text):
            raise ValueError('اكتب التعليق')
        at = stamp() + ':' + datetime.datetime.utcfromtimestamp(now_r() / 1000).strftime('%S')
        conn.execute("INSERT INTO opn_comments VALUES (?,?,?,?,?,?,?,?)",
                     (uid('C'), Q, ch, task_id, me['name'], 'العمليات' if me['isOps'] else '، '.join(me['depts']), str(text)[:2000], at))
        conn.execute("INSERT OR REPLACE INTO opn_seen VALUES (?,?,?)", (me['username'], Q + '|' + ch, at))
        conn.commit()
        return True
    if fn == 'api_seen':
        Q, chs = t_(a[0]), (a[1] if len(a) > 1 else []) or []
        for ch in chs:
            if can_channel(me, ch):
                conn.execute("INSERT OR REPLACE INTO opn_seen VALUES (?,?,?)", (me['username'], Q + '|' + ch, stamp() + ':59'))
        conn.commit()
        return True
    if fn == 'api_planStatus':
        need_ops(me)
        R = read_plan(conn, t_(a[0]))
        return {'status': R['status'], 'version': R['version'], 'approved': R['approved']} if R else None
    if fn == 'api_importPlan':
        need_ops(me)
        r = import_plan(conn, t_(a[0]), me['name'])
        conn.commit()
        return r
    if fn == 'api_team':
        need_ops(me)
        return {'native': True, 'members': _team(conn), 'depts': DEPTS, 'roles': [ROLE_OPS, ROLE_DEPT], 'links': [], 'bookUrl': ''}
    if fn == 'api_setMember':
        if not me['isAdmin']:
            raise PermissionError('للإدارة فقط')
        uname, role, depts = t_(a[0]), t_(a[1] if len(a) > 1 else ''), (a[2] if len(a) > 2 else []) or []
        active = a[3] if len(a) > 3 else True
        if role and role not in (ROLE_OPS, ROLE_DEPT):
            raise ValueError('دور غير صحيح')
        depts = [d for d in depts if d in DEPTS]
        if role == ROLE_DEPT and not depts:
            raise ValueError('اختر قسماً واحداً على الأقل')
        conn.execute("INSERT OR REPLACE INTO opn_team VALUES (?,?,?,?)", (uname, role, '، '.join(depts), 'نعم' if active else 'لا'))
        log_(conn, me['name'], '', 'الفريق', f"{uname}: {role or 'افتراضي'} {'، '.join(depts)}{'' if active else ' (موقوف)'}")
        conn.commit()
        return True
    if fn == 'api_resetPin':
        return True
    if fn == 'api_log':
        need_ops(me)
        Q = t_(a[0] if a else '')
        rows = conn.execute("SELECT * FROM opn_log" + (" WHERE Q=?" if Q else '') + " ORDER BY id DESC LIMIT 80", (Q,) if Q else ()).fetchall()
        return [{'at': r['at'], 'by': r['user'], 'Q': r['Q'], 'action': r['action'], 'details': r['details']} for r in rows]
    raise ValueError('دالة غير معروفة: ' + fn)


def dept_tasks_for_user(conn, user, is_super, days=14):
    """مهام الشخص حسب قسمه (للوحة المنصة الرئيسية)"""
    try:
        me = member(conn, user, is_super)
    except PermissionError:
        return []
    ov = overview(conn, me)
    out = []
    for c in ov['cards']:
        for t in (c.get('tasks') or []):
            if not t['done']:
                out.append(dict(t, client=c['client'], O=c['O']))
    return sorted(out, key=lambda x: x['dueMs'] or 9e15)
