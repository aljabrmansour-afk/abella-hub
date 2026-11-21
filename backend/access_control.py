import os
"""
نظام الدخول والصلاحيات لأبيلا (الإصدار 4)
==========================================
- الأدوار وصلاحياتها محفوظة في قاعدة البيانات (roles + role_permissions)
  وتُعدّل من شاشة «المستخدمين والصلاحيات» بدون برمجة.
- لكل قسم (module) أربع صلاحيات: عرض / إضافة / تعديل / حذف.
- الجلسات محفوظة في جدول sessions (ما تضيع لو أُعيد تشغيل الخادم).
- كل طلبات /api/ تتطلب تسجيل دخول، ما عدا الدخول والترجمات.
"""
import hashlib, secrets, datetime, re, json, threading, time

# ============================================================
# الأقسام (مصدر الحقيقة الوحيد — الواجهة تقرأها من /api/auth/me)
# ============================================================
MODULES = [
    # key,            label,                      group
    ('dashboard',     'لوحة المعلومات',           'عام'),
    ('calendar',      'التقويم',                  'عام'),
    ('customers',     'العملاء',                  'خدمة العملاء'),
    ('appointments',  'المواعيد',                 'خدمة العملاء'),
    ('confirmations', 'تأكيد المناسبات',          'خدمة العملاء'),
    ('leads',         'العملاء المحتملون',        'المبيعات'),
    ('quotes',        'عروض الأسعار والعقود',     'المبيعات'),
    ('payments',      'الدفعات والمستحقات',       'المالية'),
    ('finance',       'المالية والأرباح',         'المالية'),
    ('reports',       'التقارير',                 'المالية'),
    ('expenses',      'المصروفات والمشتريات',     'المالية'),
    ('events',        'المناسبات',                'العمليات'),
    ('work_plans',    'خطط العمل',                'العمليات'),
    ('sub_plans',     'الخطط الفرعية',            'العمليات'),
    ('inventory',     'المخزون',                  'العمليات'),
    ('raw_materials', 'المواد الخام',             'العمليات'),
    ('teams',         'الفرق',                    'العمليات'),
    ('employees',     'الموظفون',                 'الموارد البشرية'),
    ('leaves',        'الإجازات',                 'الموارد البشرية'),
    ('payroll',       'الرواتب والسلف',           'الموارد البشرية'),
    ('tasks',         'المهام',                   'الموارد البشرية'),
    ('assets',        'الأصول والمعدات والسيارات', 'الأصول'),
    ('users',         'المستخدمين والصلاحيات',    'الإدارة'),
    ('sync',          'المزامنة',                 'الإدارة'),
]
# الأقسام اللي كانت موجودة في أول نشر للإصدار 4 (عشان نعرف الجديدة ونعطي الأدوار صلاحياتها الافتراضية)
V4_BASE_MODULES = ['dashboard', 'calendar', 'customers', 'appointments', 'confirmations', 'leads', 'quotes',
                   'payments', 'finance', 'reports', 'events', 'work_plans', 'sub_plans', 'inventory',
                   'raw_materials', 'teams', 'users', 'sync']
MODULE_KEYS = [m[0] for m in MODULES]
ACTIONS = ('view', 'create', 'edit', 'delete')

# ============================================================
# الأدوار الافتراضية (تُزرع مرة واحدة فقط — بعدها التعديل من الشاشة)
# V=عرض C=إضافة E=تعديل D=حذف
# ============================================================
DEFAULT_ROLES = [
    # key, name, is_super, perms {module: 'VCED'}
    ('owner', 'المالكة', 1, {}),
    ('general_manager', 'المدير العام', 1, {}),
    ('admin', 'مدير النظام', 1, {}),
    ('customer_service', 'خدمة العملاء', 0, {
        'dashboard': 'V', 'calendar': 'V', 'customers': 'VCE', 'appointments': 'VCED',
        'confirmations': 'VCE', 'leads': 'V', 'events': 'V'}),
    ('sales', 'المبيعات', 0, {
        'dashboard': 'V', 'calendar': 'V', 'customers': 'VCE', 'appointments': 'VCED',
        'leads': 'VCED', 'quotes': 'VCED', 'events': 'V'}),
    ('finance', 'المالية', 0, {
        'dashboard': 'V', 'customers': 'V', 'quotes': 'V', 'payments': 'VCE',
        'finance': 'V', 'reports': 'V', 'events': 'V', 'sync': 'VE',
        'employees': 'V', 'payroll': 'VCE', 'assets': 'V', 'expenses': 'VCE'}),
    ('project_manager', 'مدير المشروع', 0, {
        'dashboard': 'V', 'calendar': 'V', 'customers': 'V', 'appointments': 'V',
        'confirmations': 'V', 'events': 'VE', 'work_plans': 'VCE', 'sub_plans': 'VCE',
        'inventory': 'V', 'teams': 'V', 'tasks': 'VCE', 'leaves': 'V', 'assets': 'V'}),
    ('planner', 'مخطط', 0, {
        'dashboard': 'V', 'events': 'V', 'work_plans': 'VCE', 'sub_plans': 'V'}),
    ('designer', 'التصميم', 0, {
        'dashboard': 'V', 'events': 'V', 'work_plans': 'VCE', 'sub_plans': 'V', 'inventory': 'V'}),
    ('inventory_manager', 'مسؤول المخزون', 0, {
        'dashboard': 'V', 'inventory': 'VCE', 'raw_materials': 'VCE', 'assets': 'VCE'}),
    ('supervisor', 'الإشراف', 0, {
        'dashboard': 'V', 'calendar': 'V', 'customers': 'V', 'confirmations': 'V',
        'events': 'V', 'work_plans': 'V', 'sub_plans': 'V', 'expenses': 'VC'}),
    ('field', 'التنفيذ الميداني', 0, {
        'dashboard': 'V', 'events': 'V', 'inventory': 'V'}),
    ('warehouse', 'المستودع', 0, {
        'dashboard': 'V', 'inventory': 'VE', 'sub_plans': 'V'}),
    ('warehouse_decor', 'مستودع الديكورات', 0, {
        'dashboard': 'V', 'inventory': 'VE', 'sub_plans': 'V'}),
    ('warehouse_acc', 'مستودع الإكسسوارات', 0, {
        'dashboard': 'V', 'inventory': 'VE', 'sub_plans': 'V'}),
    ('factory', 'المصنع', 0, {
        'dashboard': 'V', 'raw_materials': 'VCE', 'sub_plans': 'V', 'inventory': 'V'}),
    ('hospitality', 'الضيافة', 0, {
        'dashboard': 'V', 'events': 'V', 'sub_plans': 'V', 'expenses': 'VC'}),
    ('purchasing', 'المشتريات', 0, {
        'dashboard': 'V', 'raw_materials': 'VCE', 'inventory': 'V', 'sync': 'V', 'expenses': 'VC'}),
]

DEFAULT_SETTINGS = {
    'company_name': 'أبيلا للأفراح والمناسبات',
    'company_cr': '1010691676',
    'company_vat': '314666725500003',
    'company_unified': '920008899',
    'vat_rate': '0.15',
    'deposit_rate': '0.5',
    'insurance_rate': '0.2',
    'quote_valid_days': '2',     # الشروط: صلاحية العرض 48 ساعة
    'confirm_window_days': '30',     # متى نبدأ متابعة تأكيد الموعد قبل التاريخ المتوقع
    'confirm_recontact_days': '7',   # كل كم يوم نعيد الاتصال لو ما تأكد
    'rush_fee_weeks': '3',           # ولادة مبكرة بأكثر من 3 أسابيع → رسوم تجهيز مستعجل
    'rush_fee_rate': '0.10',
    # الموارد البشرية — نسب التأمينات (تحقق منها مع التأمينات الاجتماعية)
    'gosi_cap': '45000',
    'gosi_legacy_employee': '0.0975',   # سعودي مسجّل قبل 3-7-2024: معاشات 9% + ساند 0.75%
    'gosi_legacy_employer': '0.1175',   # معاشات 9% + ساند 0.75% + أخطار 2%
    'gosi_new_employee': '0.1075',      # سعودي مسجّل من 3-7-2024 (بعد زيادة 1-7-2026): معاشات 10% + ساند 0.75%
    'gosi_new_employer': '0.1275',      # معاشات 10% + ساند 0.75% + أخطار 2%
    'gosi_nonsaudi_employer': '0.02',   # غير السعودي: أخطار مهنية 2% على صاحب العمل فقط
    'annual_leave_days': '21',          # م109: 21 يوم، و30 يوم بعد 5 سنوات
    'annual_leave_days_5y': '30',
    'expiry_alert_days': '60',
    'terms_newborn_hospital': '',
    'terms_newborn_home': '',
    'terms_special': '',
    'terms_exhibition': '',
}

SESSION_DAYS = 30

# ============================================================
# كلمات المرور
# ============================================================
def hash_password(password):
    salt = secrets.token_hex(16)
    iters = 200_000
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), iters).hex()
    return f"pbkdf2${iters}${salt}${h}"

def verify_password(password, stored):
    """يدعم الصيغة الجديدة + الصيغ القديمة للنظام"""
    if not stored:
        return False
    if stored.startswith('pbkdf2$'):
        try:
            _, iters, salt, h = stored.split('$', 3)
            calc = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iters)).hex()
            return secrets.compare_digest(calc, h)
        except Exception:
            return False
    if stored.startswith('$2'):
        # حسابات قديمة كلمة مرورها الافتراضية admin123 — تُجبر على التغيير بعد الدخول
        # على الخادم العام: كلمة المرور الافتراضية معطّلة — المدير يصدر كلمة مؤقتة
        if os.environ.get('ABELLA_HOSTED'):
            return False
        return password == 'admin123'
    if '$' not in stored:
        return secrets.compare_digest(password, stored)
    salt, h = stored.split('$', 1)
    return secrets.compare_digest(hashlib.sha256((salt + password).encode()).hexdigest(), h)

def is_legacy_hash(stored):
    return not (stored or '').startswith('pbkdf2$')

# ============================================================
# تهيئة الجداول (آمنة — تُشغّل كل مرة يبدأ فيها الخادم)
# ============================================================
def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

def _users_has_role_check(conn):
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    sql = re.sub(r'\s+', '', (row[0] if row else '') or '')
    return 'CHECK(roleIN(' in sql

def _rebuild_users_without_role_check(conn):
    """جدول users القديم يقيّد الأدوار بقائمة ثابتة — نعيد بناءه بدون القيد عشان تقدر تضيف أدوار"""
    cols = _cols(conn, 'users')
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("""CREATE TABLE users__new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        phone TEXT, email TEXT,
        role TEXT NOT NULL,
        language TEXT DEFAULT 'ar',
        team_id INTEGER,
        can_record_expenses TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_login TEXT,
        must_change_password INTEGER DEFAULT 0,
        job_title TEXT,
        notes TEXT
    )""")
    keep = [c for c in ['id','username','password_hash','full_name','phone','email','role','language',
                        'team_id','can_record_expenses','is_active','created_at','last_login',
                        'must_change_password','job_title','notes'] if c in cols]
    cl = ','.join(keep)
    conn.execute(f"INSERT INTO users__new ({cl}) SELECT {cl} FROM users")
    conn.execute("DROP TABLE users")
    conn.execute("ALTER TABLE users__new RENAME TO users")
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")

def init_tables(conn):
    if _users_has_role_check(conn):
        _rebuild_users_without_role_check(conn)
        print("⚙ جدول المستخدمين: أُزيل قيد الأدوار الثابتة (تقدر تضيف أدوار جديدة)")
    ucols = _cols(conn, 'users')
    for col, d in [('must_change_password', 'INTEGER DEFAULT 0'), ('job_title', 'TEXT'), ('notes', 'TEXT')]:
        if col not in ucols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {d}")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS roles (
        key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        is_super INTEGER DEFAULT 0,
        is_system INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS role_permissions (
        role_key TEXT NOT NULL,
        module TEXT NOT NULL,
        can_view INTEGER DEFAULT 0,
        can_create INTEGER DEFAULT 0,
        can_edit INTEGER DEFAULT 0,
        can_delete INTEGER DEFAULT 0,
        PRIMARY KEY (role_key, module)
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT NOT NULL,
        user_agent TEXT
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)

    # زرع الأدوار الافتراضية (لا يلمس أي دور موجود)
    existing = {r[0] for r in conn.execute("SELECT key FROM roles").fetchall()}
    for key, name, is_super, perms in DEFAULT_ROLES:
        if key in existing:
            continue
        conn.execute("INSERT INTO roles (key, name, is_super, is_system) VALUES (?,?,?,1)",
                     (key, name, is_super))
        for mod, flags in perms.items():
            conn.execute("""INSERT OR REPLACE INTO role_permissions
                (role_key, module, can_view, can_create, can_edit, can_delete) VALUES (?,?,?,?,?,?)""",
                (key, mod, int('V' in flags), int('C' in flags), int('E' in flags), int('D' in flags)))
    # أقسام أُضيفت بعد إنشاء الأدوار → نعطي الأدوار الافتراضية صلاحياتها مرة واحدة فقط
    row = conn.execute("SELECT value FROM settings WHERE key='seeded_modules'").fetchone() \
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='settings'").fetchone() else None
    seeded = set(json.loads(row[0])) if row and row[0] else set(V4_BASE_MODULES)
    new_mods = [m for m in MODULE_KEYS if m not in seeded]
    if new_mods:
        for key, name, is_super, perms in DEFAULT_ROLES:
            if not conn.execute("SELECT 1 FROM roles WHERE key=?", (key,)).fetchone():
                continue
            for mod in new_mods:
                flags = perms.get(mod)
                if flags:
                    conn.execute("""INSERT OR IGNORE INTO role_permissions
                        (role_key, module, can_view, can_create, can_edit, can_delete) VALUES (?,?,?,?,?,?)""",
                        (key, mod, int('V' in flags), int('C' in flags), int('E' in flags), int('D' in flags)))
    _seeded_after = sorted(seeded | set(MODULE_KEYS))
    # أي دور مستخدَم في users وغير معرّف → نعرّفه بدون صلاحيات
    for (r,) in conn.execute("SELECT DISTINCT role FROM users").fetchall():
        if r and not conn.execute("SELECT 1 FROM roles WHERE key=?", (r,)).fetchone():
            conn.execute("INSERT INTO roles (key, name) VALUES (?,?)", (r, r))

    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('seeded_modules', ?)",
                 (json.dumps(_seeded_after),))
    # الشروط والأحكام المعتمدة (من نماذج العقود) — تُعبّأ مرة واحدة لو الحقل فاضي
    try:
        import os
        seed = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'contract_terms.json')
        if os.path.exists(seed):
            for k, v in json.load(open(seed, encoding='utf-8')).items():
                conn.execute("UPDATE settings SET value=? WHERE key=? AND COALESCE(value,'')=''", (v, k))
    except Exception as e:
        print('  ⚠ terms seed:', e)

    # الحسابات القديمة بكلمة المرور الافتراضية تُجبر على التغيير
    for r in conn.execute("SELECT id, password_hash FROM users").fetchall():
        if is_legacy_hash(r[1]):
            conn.execute("UPDATE users SET must_change_password=1 WHERE id=?", (r[0],))
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now(),))
    conn.commit()

def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def get_setting(conn, key, default=None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r and r[0] is not None else default

def get_settings(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT key, value FROM settings").fetchall()}

# ============================================================
# الجلسات
# ============================================================
def create_session(conn, user_id, user_agent=''):
    token = secrets.token_urlsafe(32)
    exp = (datetime.datetime.now() + datetime.timedelta(days=SESSION_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("INSERT INTO sessions (token, user_id, expires_at, user_agent) VALUES (?,?,?,?)",
                 (token, user_id, exp, (user_agent or '')[:200]))
    conn.commit()
    return token

def user_id_from_token(conn, token):
    if not token:
        return None
    r = conn.execute("""SELECT s.user_id FROM sessions s JOIN users u ON u.id=s.user_id
                        WHERE s.token=? AND s.expires_at>=? AND u.is_active=1""",
                     (token, _now())).fetchone()
    return r[0] if r else None

def delete_session(conn, token):
    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()

def kill_user_sessions(conn, user_id, except_token=None):
    conn.execute("DELETE FROM sessions WHERE user_id=? AND token IS NOT ?", (user_id, except_token))
    conn.commit()

# ============================================================
# حماية الدخول من التخمين (10 محاولات فاشلة / 15 دقيقة لكل عنوان)
# ============================================================
_fail_lock = threading.Lock()
_fails = {}

def login_blocked(ip):
    with _fail_lock:
        lst = [t for t in _fails.get(ip, []) if time.time() - t < 900]
        _fails[ip] = lst
        return len(lst) >= 10

def record_fail(ip):
    with _fail_lock:
        _fails.setdefault(ip, []).append(time.time())

def clear_fails(ip):
    with _fail_lock:
        _fails.pop(ip, None)

# ============================================================
# الصلاحيات
# ============================================================
def get_user(conn, user_id):
    r = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(r) if r else None

def get_perms(conn, role):
    """يرجع {'is_super': bool, 'modules': {module: {view,create,edit,delete}}}"""
    role_row = conn.execute("SELECT * FROM roles WHERE key=?", (role,)).fetchone()
    is_super = bool(role_row and role_row['is_super'])
    mods = {}
    if is_super:
        for k in MODULE_KEYS:
            mods[k] = {a: True for a in ACTIONS}
    else:
        for r in conn.execute("SELECT * FROM role_permissions WHERE role_key=?", (role,)).fetchall():
            mods[r['module']] = {'view': bool(r['can_view']), 'create': bool(r['can_create']),
                                 'edit': bool(r['can_edit']), 'delete': bool(r['can_delete'])}
    return {'is_super': is_super, 'role_name': role_row['name'] if role_row else role, 'modules': mods}

def user_roles(user):
    """الدور الأساسي + الأدوار الإضافية (الشخص ممكن يمسك أكثر من دور)"""
    out = [user.get('role')] if user.get('role') else []
    for r in (user.get('extra_roles') or '').split(','):
        r = r.strip()
        if r and r not in out:
            out.append(r)
    return out


def get_user_perms(conn, user):
    """اتحاد صلاحيات كل أدوار المستخدم"""
    roles = user_roles(user)
    merged = {'is_super': False, 'role_name': '', 'modules': {}, 'roles': roles}
    names = []
    for r in roles:
        p = get_perms(conn, r)
        names.append(p['role_name'])
        merged['is_super'] = merged['is_super'] or p['is_super']
        for m, acts in p['modules'].items():
            cur = merged['modules'].setdefault(m, {a: False for a in ACTIONS})
            for a, v in acts.items():
                cur[a] = cur[a] or v
    merged['role_name'] = ' + '.join(n for n in names if n)
    return merged


def can(perms, module, action='view'):
    if perms.get('is_super'):
        return True
    m = perms.get('modules', {}).get(module)
    return bool(m and m.get(action))

# ============================================================
# قواعد حماية مسارات الـAPI
# (method regex, path regex, [(module, action), ...] أي واحدة منها تكفي)
# المسارات اللي ما لها قاعدة: تتطلب تسجيل دخول فقط (تطبيق الجوال وغيره)
# ============================================================
PUBLIC_PATHS = [r'^/api/login$', r'^/api/auth/login$', r'^/api/i18n/(ar|en|ur)$', r'^/api/health$']

RULES = [
    # الموارد البشرية
    (r'GET',        r'^/api/hr/alerts',                [('employees', 'view'), ('leaves', 'view'), ('assets', 'view'), ('payroll', 'view')]),
    (r'GET',        r'^/api/hr/employees',             [('employees', 'view'), ('payroll', 'view')]),
    (r'POST',       r'^/api/hr/employees$',            [('employees', 'create')]),
    (r'PUT',        r'^/api/hr/employees/',            [('employees', 'edit')]),
    (r'DELETE',     r'^/api/hr/employees/',            [('employees', 'delete')]),
    (r'GET',        r'^/api/hr/leaves',                [('leaves', 'view')]),
    (r'POST',       r'^/api/hr/leaves/\d+/decision',   [('leaves', 'edit')]),
    (r'POST',       r'^/api/hr/leaves$',               [('leaves', 'create')]),
    (r'DELETE',     r'^/api/hr/leaves/',               [('leaves', 'delete')]),
    (r'GET',        r'^/api/hr/(payroll|advances)',    [('payroll', 'view')]),
    (r'POST',       r'^/api/hr/(payroll|advances)',    [('payroll', 'create'), ('payroll', 'edit')]),
    (r'PUT',        r'^/api/hr/(payroll|advances)',    [('payroll', 'edit')]),
    (r'DELETE',     r'^/api/hr/(payroll|advances)',    [('payroll', 'delete')]),
    (r'GET',        r'^/api/hr/tasks',                 [('tasks', 'view')]),
    (r'POST',       r'^/api/hr/tasks',                 [('tasks', 'create')]),
    (r'PUT',        r'^/api/hr/tasks/',                [('tasks', 'edit')]),
    (r'DELETE',     r'^/api/hr/tasks/',                [('tasks', 'delete')]),
    # الأصول
    (r'GET',        r'^/api/assets',                   [('assets', 'view')]),
    (r'POST',       r'^/api/assets/\d+/',              [('assets', 'edit')]),
    (r'POST',       r'^/api/assets$',                  [('assets', 'create')]),
    (r'PUT',        r'^/api/assets/',                  [('assets', 'edit')]),
    (r'DELETE',     r'^/api/assets/',                  [('assets', 'delete')]),
    # الإدارة
    (r'GET',        r'^/api/admin/',                   [('users', 'view')]),
    (r'POST|PUT',   r'^/api/admin/',                   [('users', 'edit')]),
    (r'DELETE',     r'^/api/admin/',                   [('users', 'delete')]),
    (r'POST',       r'^/api/sync/',                    [('sync', 'edit')]),
    (r'GET',        r'^/api/sync/',                    [('sync', 'view')]),
    # المبيعات
    (r'GET',        r'^/api/leads',                    [('leads', 'view')]),
    (r'POST',       r'^/api/leads/\d+/',               [('leads', 'edit')]),
    (r'POST',       r'^/api/leads$',                   [('leads', 'create')]),
    (r'PUT',        r'^/api/leads',                    [('leads', 'edit')]),
    (r'DELETE',     r'^/api/leads',                    [('leads', 'delete')]),
    (r'GET',        r'^/api/quotes',                   [('quotes', 'view'), ('payments', 'view')]),
    (r'POST',       r'^/api/quotes$',                  [('quotes', 'create')]),
    (r'POST|PUT',   r'^/api/quotes/',                  [('quotes', 'edit')]),
    (r'DELETE',     r'^/api/quotes',                   [('quotes', 'delete')]),
    (r'GET',        r'^/api/services-catalog',         [('quotes', 'view')]),
    # خدمة العملاء
    (r'GET',        r'^/api/confirmations',            [('confirmations', 'view')]),
    (r'POST|PUT',   r'^/api/confirmations',            [('confirmations', 'edit')]),
    (r'GET',        r'^/api/customers',                [('customers', 'view'), ('leads', 'view'),
                                                        ('quotes', 'view'), ('confirmations', 'view'),
                                                        ('payments', 'view'), ('appointments', 'view')]),
    (r'POST',       r'^/api/customers$',               [('customers', 'create')]),
    (r'PUT',        r'^/api/customers/',               [('customers', 'edit')]),
    (r'DELETE',     r'^/api/customers/',               [('customers', 'delete')]),
    (r'POST',       r'^/api/appointments$',            [('appointments', 'create'), ('leads', 'edit')]),
    (r'PUT',        r'^/api/appointments/',            [('appointments', 'edit')]),
    (r'DELETE',     r'^/api/appointments/',            [('appointments', 'delete')]),
    # المالية
    (r'GET',        r'^/api/payments',                 [('payments', 'view')]),
    (r'POST',       r'^/api/payments',                 [('payments', 'create')]),
    (r'DELETE',     r'^/api/payments',                 [('payments', 'delete')]),
    # العمليات (كتابة فقط — القراءة يحتاجها تطبيق الجوال)
    (r'POST',       r'^/api/events$',                  [('events', 'create')]),
    (r'PUT',        r'^/api/events/',                  [('events', 'edit')]),
    (r'DELETE',     r'^/api/events/',                  [('events', 'delete')]),
    (r'GET|POST',   r'^/api/jard/',                    [('inventory', 'view'), ('raw_materials', 'view')]),
    (r'GET',        r'^/api/exp/',                     [('expenses', 'view'), ('finance', 'view')]),
    (r'POST',       r'^/api/exp/',                     [('expenses', 'view'), ('finance', 'view')]),
    (r'POST',       r'^/api/wpgen/',                  [('work_plans', 'view')]),
    (r'POST',       r'^/api/workplans$',               [('work_plans', 'create')]),
    (r'POST',       r'^/api/workplans/approve',        [('work_plans', 'edit')]),
    (r'PUT',        r'^/api/workplans/',               [('work_plans', 'edit')]),
    (r'DELETE',     r'^/api/workplans/',               [('work_plans', 'delete')]),
    (r'POST',       r'^/api/inventory$',               [('inventory', 'create')]),
    (r'PUT',        r'^/api/inventory/',               [('inventory', 'edit')]),
    (r'DELETE',     r'^/api/inventory/',               [('inventory', 'delete')]),
    (r'PUT',        r'^/api/raw-materials/',           [('raw_materials', 'edit')]),
    (r'DELETE',     r'^/api/raw-materials/',           [('raw_materials', 'delete')]),
]
_COMPILED = [(re.compile(m), re.compile(p), req) for m, p, req in RULES]
_PUBLIC = [re.compile(p) for p in PUBLIC_PATHS]

def is_public(path):
    return any(p.match(path) for p in _PUBLIC)

def required_for(method, path):
    for mre, pre, req in _COMPILED:
        if mre.fullmatch(method) and pre.match(path):
            return req
    return None

def check(conn, method, path, user_id):
    """يرجع (ok, status, message, ctx)"""
    if is_public(path):
        return True, 200, '', None
    if not user_id:
        return False, 401, 'سجّل الدخول أولاً', None
    user = get_user(conn, user_id)
    if not user or not user.get('is_active'):
        return False, 401, 'الحساب غير مفعّل', None
    perms = get_user_perms(conn, user)
    ctx = {'user': user, 'perms': perms}
    # تغيير كلمة المرور الإجباري: يُسمح فقط بمسارات الحساب
    if user.get('must_change_password') and not path.startswith('/api/auth/') and path not in ('/api/me', '/api/permissions/me'):
        return False, 403, 'لازم تغيّر كلمة المرور أولاً', ctx
    req = required_for(method, path)
    if req is None:
        return True, 200, '', ctx
    if any(can(perms, m, a) for m, a in req):
        return True, 200, '', ctx
    return False, 403, 'ما عندك صلاحية لهذا الإجراء', ctx

def public_user(user, perms):
    return {
        'id': user['id'], 'username': user['username'], 'full_name': user['full_name'],
        'role': user['role'], 'role_name': perms.get('role_name'),
        'language': user.get('language') or 'ar',
        'must_change_password': bool(user.get('must_change_password')),
        'can_record_expenses': 1 if user.get('can_record_expenses') or perms.get('is_super') else 0,
    }

def audit(conn, user_id, action, entity_type, entity_id=None, old=None, new=None):
    try:
        conn.execute("""INSERT INTO audit_log (user_id, action, entity_type, entity_id, old_value, new_value)
                        VALUES (?,?,?,?,?,?)""",
                     (user_id, action, entity_type, entity_id,
                      json.dumps(old, ensure_ascii=False, default=str) if old is not None else None,
                      json.dumps(new, ensure_ascii=False, default=str) if new is not None else None))
    except Exception:
        pass
