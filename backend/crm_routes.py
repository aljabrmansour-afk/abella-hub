"""
أقسام الإصدار 4 من نظام أبيلا:
- الحساب: دخول / خروج / تغيير كلمة المرور / بياناتي وصلاحياتي
- الإدارة: المستخدمين، الأدوار ومصفوفة الصلاحيات، الإعدادات، سجل العمليات
- المبيعات: العملاء المحتملون، الاجتماعات، عروض الأسعار، التحويل لعقد
- خدمة العملاء: ملف العميل الشامل، متابعة تأكيد مواعيد المناسبات
- المالية: الدفعات والمستحقات (العربون يصرف رقم التشغيل O)
"""
import re, json, datetime, secrets
import access_control as ac

TYPE_LABELS = {'newborn': 'استقبال مولود', 'special': 'مناسبة خاصة', 'exhibition': 'معرض'}
TYPE_PREFIX = {'newborn': 'B', 'special': 'W', 'exhibition': 'E'}
VENUE_KINDS = {'hospital': 'مستشفى', 'home': 'منزل', 'hall': 'قاعة', 'other': 'أخرى'}
LEAD_STAGES = ['new', 'contacted', 'meeting', 'quoted', 'won', 'lost']

DEFAULT_SERVICES = [
    'خلفية رئيسية', 'كوشة / منصة', 'طاولة استقبال', 'طاولة ضيافة', 'كراسي', 'إضاءة',
    'ورد طبيعي', 'ورد صناعي', 'ستاند ترحيبي', 'ستيكر أسماء', 'توزيعات', 'طاقم ضيافة (صبابات)',
    'تصوير', 'سرير المولود', 'ديكور الغرفة', 'ممر / مدخل',
]


def _today():
    return datetime.date.today().isoformat()

def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]

def _row(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None

def _num(v, d=0.0):
    try:
        if v in (None, ''):
            return d
        return float(v)
    except (TypeError, ValueError):
        return d


# ============================================================
# الجداول
# ============================================================
def init_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_code TEXT UNIQUE,
        full_name TEXT NOT NULL,
        phone TEXT,
        source TEXT,
        event_type TEXT,
        venue_kind TEXT,
        expected_date TEXT,
        budget REAL,
        stage TEXT DEFAULT 'new',
        lost_reason TEXT,
        next_followup TEXT,
        assigned_to INTEGER,
        customer_id INTEGER,
        notes TEXT,
        created_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quote_code TEXT UNIQUE,
        lead_id INTEGER,
        customer_id INTEGER,
        client_name TEXT,
        client_phone TEXT,
        client_id_number TEXT,
        event_type TEXT NOT NULL,
        venue_kind TEXT,
        venue_name TEXT,
        expected_date TEXT,
        event_time TEXT,
        guests_count INTEGER,
        package TEXT,
        execution_days INTEGER,
        contract_value REAL DEFAULT 0,
        additional REAL DEFAULT 0,
        discount REAL DEFAULT 0,
        vat_rate REAL DEFAULT 0.15,
        vat_amount REAL DEFAULT 0,
        total_with_vat REAL DEFAULT 0,
        insurance REAL DEFAULT 0,
        deposit REAL DEFAULT 0,
        status TEXT DEFAULT 'draft',
        valid_until TEXT,
        notes TEXT,
        internal_notes TEXT,
        event_id INTEGER,
        contract_code TEXT,
        contracted_at TEXT,
        created_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS quote_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quote_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        qty REAL DEFAULT 1,
        notes TEXT,
        sort_order INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS event_confirmations (
        event_id INTEGER PRIMARY KEY,
        status TEXT DEFAULT 'pending',
        confirmed_date TEXT,
        confirmed_time TEXT,
        next_contact_date TEXT,
        last_contact_at TEXT,
        rush_fee_due INTEGER DEFAULT 0,
        notes TEXT,
        updated_by INTEGER,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS confirmation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        channel TEXT,
        result TEXT,
        note TEXT,
        created_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
    CREATE INDEX IF NOT EXISTS idx_quotes_status ON quotes(status);
    CREATE INDEX IF NOT EXISTS idx_quote_items_q ON quote_items(quote_id);
    CREATE INDEX IF NOT EXISTS idx_conflog_ev ON confirmation_logs(event_id);
    """)
    ecols = {r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    if 'quote_id' not in ecols:
        conn.execute("ALTER TABLE events ADD COLUMN quote_id INTEGER")
    acols = {r[1] for r in conn.execute("PRAGMA table_info(appointments)").fetchall()}
    if 'lead_id' not in acols:
        conn.execute("ALTER TABLE appointments ADD COLUMN lead_id INTEGER")
    conn.commit()


# ============================================================
# الترقيم
# ============================================================
def _next_seq(conn, sql_list, prefix, start):
    mx = start
    for sql in sql_list:
        try:
            for (v,) in conn.execute(sql).fetchall():
                m = re.match(rf'^{prefix}(\d+)$', str(v or '').strip())
                if m:
                    mx = max(mx, int(m.group(1)))
        except Exception:
            pass
    return f"{prefix}{mx + 1}"

def next_contract_code(conn, event_type):
    p = TYPE_PREFIX.get(event_type, 'W')
    return _next_seq(conn, [
        f"SELECT contract_code FROM events WHERE contract_code LIKE '{p}%'",
        f"SELECT contract_code FROM sheet_contracts WHERE contract_code LIKE '{p}%'",
        f"SELECT contract_code FROM quotes WHERE contract_code LIKE '{p}%'",
    ], p, 1000)

def next_operation_order(conn):
    return _next_seq(conn, [
        "SELECT operation_order FROM events WHERE operation_order LIKE 'O%'",
        "SELECT operation_order FROM sheet_contracts WHERE operation_order LIKE 'O%'",
    ], 'O', 1000)

def _next_code(conn, table, col, prefix):
    year = datetime.date.today().year
    pre = f"{prefix}-{year}-"
    mx = 0
    for (v,) in conn.execute(f"SELECT {col} FROM {table} WHERE {col} LIKE ?", (pre + '%',)).fetchall():
        try:
            mx = max(mx, int(str(v).split('-')[-1]))
        except Exception:
            pass
    return f"{pre}{mx + 1:04d}"


# ============================================================
# حساب عرض السعر (نفس معادلات جدول العقود)
# ============================================================
def compute_totals(conn, d):
    s = ac.get_settings(conn)
    vat_rate = _num(s.get('vat_rate'), 0.15)
    cv = _num(d.get('contract_value'))
    add = _num(d.get('additional'))
    disc = _num(d.get('discount'))
    base = max(cv + add - disc, 0)
    vat = round(base * vat_rate, 2)
    total = round(base + vat, 2)
    return {
        'vat_rate': vat_rate,
        'vat_amount': vat,
        'total_with_vat': total,
        'deposit': round(total * _num(s.get('deposit_rate'), 0.5), 2),
        'insurance': round(cv * _num(s.get('insurance_rate'), 0.2), 2),
    }


# ============================================================
# الموجّه الرئيسي
# ============================================================
def handle(h, conn, method, path, query, data, ctx, send_json):
    """يرجع True لو المسار تم التعامل معه"""
    uid = ctx['user']['id'] if ctx else None

    # ---------------- الحساب ----------------
    if path in ('/api/auth/login', '/api/login') and method == 'POST':
        return _login(h, conn, data, send_json)
    if path == '/api/auth/logout' and method == 'POST':
        token = h.headers.get('Authorization', '').replace('Bearer ', '')
        ac.delete_session(conn, token)
        return send_json({'success': True}) or True
    if path in ('/api/auth/me', '/api/me', '/api/permissions/me') and method == 'GET':
        return _me(conn, ctx, send_json, legacy=(path != '/api/auth/me'))
    if path == '/api/auth/change-password' and method == 'POST':
        return _change_password(h, conn, ctx, data, send_json)

    # ---------------- الإدارة ----------------
    if path.startswith('/api/admin/'):
        return _admin(conn, method, path, query, data, ctx, send_json)

    # ---------------- المبيعات ----------------
    if path.startswith('/api/leads'):
        return _leads(conn, method, path, query, data, ctx, send_json)
    if path.startswith('/api/quotes'):
        return _quotes(conn, method, path, query, data, ctx, send_json)
    if path == '/api/services-catalog' and method == 'GET':
        names = [r[0] for r in conn.execute(
            "SELECT name FROM quote_items GROUP BY name ORDER BY COUNT(*) DESC LIMIT 200").fetchall()]
        for n in DEFAULT_SERVICES:
            if n not in names:
                names.append(n)
        return send_json(names) or True

    # ---------------- خدمة العملاء ----------------
    if path.startswith('/api/confirmations'):
        return _confirmations(conn, method, path, query, data, ctx, send_json)
    m = re.match(r'^/api/customers/(\d+)/profile$', path)
    if m and method == 'GET':
        return _customer_profile(conn, int(m.group(1)), ctx, send_json)

    # ---------------- المالية ----------------
    if path.startswith('/api/payments'):
        return _payments(conn, method, path, query, data, ctx, send_json)

    return False


# ============================================================
# الحساب
# ============================================================
def _login(h, conn, data, send_json):
    ip = h.headers.get('X-Forwarded-For', '').split(',')[0].strip() or h.client_address[0]
    if ac.login_blocked(ip):
        send_json({'error': 'محاولات كثيرة خاطئة — حاول بعد 15 دقيقة'}, 429)
        return True
    username = (data.get('username') or '').strip()
    user = conn.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (username,)).fetchone()
    if not user or not ac.verify_password(data.get('password', ''), user['password_hash']):
        ac.record_fail(ip)
        send_json({'error': 'اسم المستخدم أو كلمة المرور غير صحيحة'}, 401)
        return True
    if not user['is_active']:
        send_json({'error': 'الحساب موقوف — راجع الإدارة'}, 403)
        return True
    ac.clear_fails(ip)
    token = ac.create_session(conn, user['id'], h.headers.get('User-Agent', ''))
    conn.execute("UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=?", (user['id'],))
    conn.commit()
    u = dict(user)
    perms = ac.get_perms(conn, u['role'])
    send_json({'token': token, 'user': ac.public_user(u, perms), 'perms': perms})
    return True

def _me(conn, ctx, send_json, legacy=False):
    if not ctx:
        send_json({'error': 'غير مصرح'}, 401)
        return True
    user, perms = ctx['user'], ctx['perms']
    pu = ac.public_user(user, perms)
    menu = [k for k in ac.MODULE_KEYS if ac.can(perms, k, 'view')]
    payload = {
        'user': pu, 'perms': perms, 'menu': menu, 'is_super': perms['is_super'],
        'modules': [{'key': k, 'label': l, 'group': g} for k, l, g in ac.MODULES],
        'role': user['role'],
        'can_approve': perms['is_super'] or ac.can(perms, 'work_plans', 'edit'),
        'employee_id': (conn.execute("SELECT id FROM employees WHERE user_id=?", (user['id'],)).fetchone() or [None])[0]
                       if conn.execute("SELECT 1 FROM sqlite_master WHERE name='employees'").fetchone() else None,
        'settings': {k: ac.get_setting(conn, k) for k in ('vat_rate', 'deposit_rate', 'insurance_rate',
                                                           'company_name')},
        'inventory_filter': {'warehouse_decor': 'decorations', 'warehouse_acc': 'accessories',
                             'factory': 'factory_raw'}.get(user['role']),
    }
    send_json(payload)
    return True

def _change_password(h, conn, ctx, data, send_json):
    if not ctx:
        send_json({'error': 'غير مصرح'}, 401)
        return True
    user = ctx['user']
    new = data.get('new_password') or ''
    if not user.get('must_change_password'):
        if not ac.verify_password(data.get('old_password') or '', user['password_hash']):
            send_json({'error': 'كلمة المرور الحالية غير صحيحة'}, 400)
            return True
    if len(new) < 8:
        send_json({'error': 'كلمة المرور لازم تكون 8 أحرف على الأقل'}, 400)
        return True
    if new == 'admin123':
        send_json({'error': 'اختر كلمة مرور غير الافتراضية'}, 400)
        return True
    conn.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?",
                 (ac.hash_password(new), user['id']))
    token = h.headers.get('Authorization', '').replace('Bearer ', '')
    ac.kill_user_sessions(conn, user['id'], except_token=token)
    ac.audit(conn, user['id'], 'CHANGE_PASSWORD', 'user', user['id'])
    conn.commit()
    send_json({'success': True})
    return True


# ============================================================
# الإدارة: المستخدمين والأدوار والإعدادات
# ============================================================
def _super_users_left(conn, excluding_id=None):
    return conn.execute("""SELECT COUNT(*) FROM users u JOIN roles r ON r.key=u.role
                           WHERE r.is_super=1 AND u.is_active=1 AND u.id IS NOT ?""",
                        (excluding_id,)).fetchone()[0]

def _admin(conn, method, path, query, data, ctx, send_json):
    uid = ctx['user']['id']

    # ----- المستخدمون -----
    if path == '/api/admin/users' and method == 'GET':
        rows = _rows(conn, """SELECT u.id, u.username, u.full_name, u.phone, u.email, u.role, u.job_title,
                                     u.language, u.is_active, u.last_login, u.created_at, u.must_change_password,
                                     u.can_record_expenses, r.name AS role_name, r.is_super
                              FROM users u LEFT JOIN roles r ON r.key=u.role
                              ORDER BY u.is_active DESC, r.is_super DESC, u.full_name""")
        send_json(rows)
        return True

    if path == '/api/admin/users' and method == 'POST':
        username = (data.get('username') or '').strip().lower()
        if not re.match(r'^[a-z0-9_.-]{3,30}$', username):
            send_json({'error': 'اسم المستخدم: حروف إنجليزية صغيرة وأرقام فقط (3 أحرف على الأقل)'}, 400)
            return True
        if conn.execute("SELECT 1 FROM users WHERE lower(username)=?", (username,)).fetchone():
            send_json({'error': 'اسم المستخدم مستخدم من قبل'}, 400)
            return True
        if not (data.get('full_name') or '').strip():
            send_json({'error': 'اكتب الاسم الكامل'}, 400)
            return True
        role = data.get('role')
        if not conn.execute("SELECT 1 FROM roles WHERE key=?", (role,)).fetchone():
            send_json({'error': 'اختر دوراً صحيحاً'}, 400)
            return True
        pw = data.get('password') or ''
        temp = False
        if not pw:
            pw = 'Ab-' + secrets.token_hex(3)
            temp = True
        if len(pw) < 8 and not temp:
            send_json({'error': 'كلمة المرور 8 أحرف على الأقل'}, 400)
            return True
        cur = conn.execute("""INSERT INTO users (username, password_hash, full_name, phone, email, role,
                                                 job_title, language, is_active, must_change_password,
                                                 can_record_expenses)
                              VALUES (?,?,?,?,?,?,?,?,?,1,?)""",
                           (username, ac.hash_password(pw), data['full_name'].strip(), data.get('phone'),
                            data.get('email'), role, data.get('job_title'), data.get('language') or 'ar',
                            1 if data.get('is_active', 1) else 0, data.get('can_record_expenses') or None))
        ac.audit(conn, uid, 'CREATE', 'user', cur.lastrowid, new={'username': username, 'role': role})
        if data.get('employee_id'):
            try:
                conn.execute("UPDATE employees SET user_id=? WHERE id=? AND user_id IS NULL", (cur.lastrowid, data['employee_id']))
            except Exception:
                pass
        conn.commit()
        send_json({'success': True, 'id': cur.lastrowid, 'temp_password': pw})
        return True

    m = re.match(r'^/api/admin/users/(\d+)$', path)
    if m and method == 'PUT':
        tid = int(m.group(1))
        target = _row(conn, "SELECT * FROM users WHERE id=?", (tid,))
        if not target:
            send_json({'error': 'المستخدم غير موجود'}, 404)
            return True
        fields, params = [], []
        for k in ('full_name', 'phone', 'email', 'job_title', 'language', 'can_record_expenses'):
            if k in data:
                fields.append(f"{k}=?"); params.append(data[k] or None if k != 'full_name' else data[k])
        if 'role' in data and data['role'] != target['role']:
            if not conn.execute("SELECT 1 FROM roles WHERE key=?", (data['role'],)).fetchone():
                send_json({'error': 'دور غير صحيح'}, 400)
                return True
            new_is_super = conn.execute("SELECT is_super FROM roles WHERE key=?", (data['role'],)).fetchone()[0]
            if not new_is_super and _super_users_left(conn, excluding_id=tid) == 0:
                send_json({'error': 'لازم يبقى مستخدم واحد على الأقل بصلاحية كاملة'}, 400)
                return True
            fields.append("role=?"); params.append(data['role'])
        if 'is_active' in data:
            active = 1 if data['is_active'] else 0
            if not active and tid == uid:
                send_json({'error': 'ما تقدر توقف حسابك أنت'}, 400)
                return True
            if not active and _super_users_left(conn, excluding_id=tid) == 0:
                send_json({'error': 'لازم يبقى مستخدم واحد على الأقل بصلاحية كاملة'}, 400)
                return True
            fields.append("is_active=?"); params.append(active)
        reset_pw = None
        if data.get('reset_password'):
            reset_pw = data.get('new_password') or ('Ab-' + secrets.token_hex(3))
            fields.append("password_hash=?"); params.append(ac.hash_password(reset_pw))
            fields.append("must_change_password=1")
        if 'username' in data and (data['username'] or '').strip().lower() != target['username']:
            un = (data['username'] or '').strip().lower()
            if not re.match(r'^[a-z0-9_.-]{3,30}$', un):
                send_json({'error': 'اسم المستخدم غير صالح'}, 400)
                return True
            if conn.execute("SELECT 1 FROM users WHERE lower(username)=? AND id<>?", (un, tid)).fetchone():
                send_json({'error': 'اسم المستخدم مستخدم من قبل'}, 400)
                return True
            fields.append("username=?"); params.append(un)
        if not fields:
            send_json({'error': 'لا يوجد تعديل'}, 400)
            return True
        params.append(tid)
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", params)
        if reset_pw or data.get('is_active') in (0, False) or 'role' in data:
            ac.kill_user_sessions(conn, tid)
        ac.audit(conn, uid, 'UPDATE', 'user', tid,
                 new={k: v for k, v in data.items() if k not in ('new_password',)})
        conn.commit()
        send_json({'success': True, 'temp_password': reset_pw})
        return True

    if m and method == 'DELETE':
        # لا نحذف المستخدم نهائياً (مرتبط بالسجلات) — نوقفه
        tid = int(m.group(1))
        if tid == uid:
            send_json({'error': 'ما تقدر توقف حسابك أنت'}, 400)
            return True
        if _super_users_left(conn, excluding_id=tid) == 0:
            send_json({'error': 'لازم يبقى مستخدم واحد على الأقل بصلاحية كاملة'}, 400)
            return True
        conn.execute("UPDATE users SET is_active=0 WHERE id=?", (tid,))
        ac.kill_user_sessions(conn, tid)
        ac.audit(conn, uid, 'DEACTIVATE', 'user', tid)
        conn.commit()
        send_json({'success': True})
        return True

    # ----- الأدوار -----
    if path == '/api/admin/roles' and method == 'GET':
        roles = _rows(conn, """SELECT r.*, (SELECT COUNT(*) FROM users u WHERE u.role=r.key AND u.is_active=1) AS users_count
                               FROM roles r ORDER BY r.is_super DESC, r.name""")
        perms = {}
        for p in _rows(conn, "SELECT * FROM role_permissions"):
            perms.setdefault(p['role_key'], {})[p['module']] = {
                'view': bool(p['can_view']), 'create': bool(p['can_create']),
                'edit': bool(p['can_edit']), 'delete': bool(p['can_delete'])}
        for r in roles:
            r['perms'] = perms.get(r['key'], {})
        send_json({'roles': roles,
                   'modules': [{'key': k, 'label': l, 'group': g} for k, l, g in ac.MODULES]})
        return True

    if path == '/api/admin/roles' and method == 'POST':
        name = (data.get('name') or '').strip()
        if not name:
            send_json({'error': 'اكتب اسم الدور'}, 400)
            return True
        if conn.execute("SELECT 1 FROM roles WHERE name=?", (name,)).fetchone():
            send_json({'error': 'يوجد دور بنفس الاسم'}, 400)
            return True
        key = 'role_' + secrets.token_hex(3)
        conn.execute("INSERT INTO roles (key, name, description) VALUES (?,?,?)",
                     (key, name, data.get('description')))
        src = data.get('copy_from')
        if src:
            conn.execute("""INSERT INTO role_permissions (role_key, module, can_view, can_create, can_edit, can_delete)
                            SELECT ?, module, can_view, can_create, can_edit, can_delete
                            FROM role_permissions WHERE role_key=?""", (key, src))
        ac.audit(conn, uid, 'CREATE', 'role', None, new={'key': key, 'name': name})
        conn.commit()
        send_json({'success': True, 'key': key})
        return True

    m = re.match(r'^/api/admin/roles/([A-Za-z0-9_]+)$', path)
    if m and method == 'PUT':
        key = m.group(1)
        role = _row(conn, "SELECT * FROM roles WHERE key=?", (key,))
        if not role:
            send_json({'error': 'الدور غير موجود'}, 404)
            return True
        if 'name' in data and (data['name'] or '').strip():
            conn.execute("UPDATE roles SET name=?, description=? WHERE key=?",
                         (data['name'].strip(), data.get('description', role.get('description')), key))
        if 'perms' in data:
            if role['is_super']:
                send_json({'error': 'هذا الدور له صلاحية كاملة ثابتة'}, 400)
                return True
            old = _rows(conn, "SELECT * FROM role_permissions WHERE role_key=?", (key,))
            conn.execute("DELETE FROM role_permissions WHERE role_key=?", (key,))
            for mod, p in (data['perms'] or {}).items():
                if mod not in ac.MODULE_KEYS:
                    continue
                v, c, e, d = (bool(p.get('view')), bool(p.get('create')), bool(p.get('edit')), bool(p.get('delete')))
                if c or e or d:
                    v = True  # ما ينفع يضيف أو يعدل بدون ما يشوف
                if not (v or c or e or d):
                    continue
                conn.execute("""INSERT INTO role_permissions (role_key, module, can_view, can_create, can_edit, can_delete)
                                VALUES (?,?,?,?,?,?)""", (key, mod, int(v), int(c), int(e), int(d)))
            ac.audit(conn, uid, 'UPDATE_PERMS', 'role', None, old=old, new={'key': key, 'perms': data['perms']})
        conn.commit()
        send_json({'success': True})
        return True

    if m and method == 'DELETE':
        key = m.group(1)
        role = _row(conn, "SELECT * FROM roles WHERE key=?", (key,))
        if not role:
            send_json({'error': 'الدور غير موجود'}, 404)
            return True
        if role['is_super']:
            send_json({'error': 'ما ينحذف دور الصلاحية الكاملة'}, 400)
            return True
        n = conn.execute("SELECT COUNT(*) FROM users WHERE role=?", (key,)).fetchone()[0]
        if n:
            send_json({'error': f'الدور مرتبط بـ {n} مستخدم — انقلهم لدور آخر أولاً'}, 400)
            return True
        conn.execute("DELETE FROM role_permissions WHERE role_key=?", (key,))
        conn.execute("DELETE FROM roles WHERE key=?", (key,))
        ac.audit(conn, uid, 'DELETE', 'role', None, old=role)
        conn.commit()
        send_json({'success': True})
        return True

    # ----- الإعدادات -----
    if path == '/api/admin/settings' and method == 'GET':
        send_json(ac.get_settings(conn))
        return True
    if path == '/api/admin/settings' and method == 'PUT':
        for k, v in (data or {}).items():
            if k in ac.DEFAULT_SETTINGS:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, str(v)))
        ac.audit(conn, uid, 'UPDATE', 'settings', None, new={k: (v if not k.startswith('terms_') else '…')
                                                            for k, v in (data or {}).items()})
        conn.commit()
        send_json({'success': True})
        return True

    # ----- سجل العمليات -----
    if path == '/api/admin/audit' and method == 'GET':
        lim = int((query.get('limit') or ['200'])[0])
        send_json(_rows(conn, """SELECT a.*, u.full_name AS user_name FROM audit_log a
                                 LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT ?""", (min(lim, 1000),)))
        return True

    send_json({'error': 'المسار غير موجود'}, 404)
    return True


# ============================================================
# المبيعات: العملاء المحتملون
# ============================================================
def _leads(conn, method, path, query, data, ctx, send_json):
    uid = ctx['user']['id']
    if path == '/api/leads' and method == 'GET':
        sql = """SELECT l.*, u.full_name AS assigned_name,
                        (SELECT COUNT(*) FROM quotes q WHERE q.lead_id=l.id) AS quotes_count,
                        (SELECT MIN(a.appointment_date) FROM appointments a
                          WHERE a.lead_id=l.id AND a.status IN ('scheduled','confirmed') AND a.appointment_date>=date('now')) AS next_meeting
                 FROM leads l LEFT JOIN users u ON u.id=l.assigned_to WHERE 1=1"""
        params = []
        stage = (query.get('stage') or [None])[0]
        if stage:
            sql += " AND l.stage=?"; params.append(stage)
        if (query.get('mine') or [None])[0]:
            sql += " AND l.assigned_to=?"; params.append(uid)
        sql += " ORDER BY CASE l.stage WHEN 'won' THEN 8 WHEN 'lost' THEN 9 ELSE 1 END, COALESCE(l.next_followup,'9999'), l.id DESC"
        send_json(_rows(conn, sql, params))
        return True

    if path == '/api/leads' and method == 'POST':
        if not (data.get('full_name') or '').strip():
            send_json({'error': 'اكتب اسم العميل'}, 400)
            return True
        code = _next_code(conn, 'leads', 'lead_code', 'L')
        cur = conn.execute("""INSERT INTO leads (lead_code, full_name, phone, source, event_type, venue_kind,
                                expected_date, budget, stage, next_followup, assigned_to, notes, created_by)
                              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (code, data['full_name'].strip(), data.get('phone'), data.get('source'),
                            data.get('event_type'), data.get('venue_kind'), data.get('expected_date') or None,
                            _num(data.get('budget'), None) if data.get('budget') not in (None, '') else None,
                            data.get('stage') or 'new', data.get('next_followup') or None,
                            data.get('assigned_to') or uid, data.get('notes'), uid))
        ac.audit(conn, uid, 'CREATE', 'lead', cur.lastrowid)
        conn.commit()
        send_json({'success': True, 'id': cur.lastrowid, 'lead_code': code})
        return True

    m = re.match(r'^/api/leads/(\d+)$', path)
    if m and method == 'GET':
        lid = int(m.group(1))
        lead = _row(conn, """SELECT l.*, u.full_name AS assigned_name FROM leads l
                             LEFT JOIN users u ON u.id=l.assigned_to WHERE l.id=?""", (lid,))
        if not lead:
            send_json({'error': 'غير موجود'}, 404)
            return True
        lead['meetings'] = _rows(conn, """SELECT a.*, u.full_name AS assigned_name FROM appointments a
                                         LEFT JOIN users u ON u.id=a.assigned_to WHERE a.lead_id=?
                                         ORDER BY a.appointment_date DESC, a.start_time DESC""", (lid,))
        lead['quotes'] = _rows(conn, "SELECT id, quote_code, status, total_with_vat, created_at, contract_code FROM quotes WHERE lead_id=? ORDER BY id DESC", (lid,))
        send_json(lead)
        return True

    if m and method == 'PUT':
        lid = int(m.group(1))
        allowed = ('full_name', 'phone', 'source', 'event_type', 'venue_kind', 'expected_date', 'budget',
                   'stage', 'lost_reason', 'next_followup', 'assigned_to', 'notes')
        fields, params = [], []
        for k in allowed:
            if k in data:
                fields.append(f"{k}=?"); params.append(data[k] if data[k] != '' else None)
        if not fields:
            send_json({'error': 'لا يوجد تعديل'}, 400)
            return True
        if data.get('stage') == 'lost' and not (data.get('lost_reason') or '').strip():
            send_json({'error': 'اكتب سبب الخسارة'}, 400)
            return True
        fields.append("updated_at=CURRENT_TIMESTAMP")
        params.append(lid)
        conn.execute(f"UPDATE leads SET {', '.join(fields)} WHERE id=?", params)
        ac.audit(conn, uid, 'UPDATE', 'lead', lid, new=data)
        conn.commit()
        send_json({'success': True})
        return True

    if m and method == 'DELETE':
        lid = int(m.group(1))
        if conn.execute("SELECT 1 FROM quotes WHERE lead_id=? AND status='contracted'", (lid,)).fetchone():
            send_json({'error': 'ما ينحذف — عنده عقد'}, 400)
            return True
        conn.execute("DELETE FROM leads WHERE id=?", (lid,))
        ac.audit(conn, uid, 'DELETE', 'lead', lid)
        conn.commit()
        send_json({'success': True})
        return True

    m = re.match(r'^/api/leads/(\d+)/meetings$', path)
    if m and method == 'POST':
        lid = int(m.group(1))
        lead = _row(conn, "SELECT * FROM leads WHERE id=?", (lid,))
        if not lead:
            send_json({'error': 'غير موجود'}, 404)
            return True
        if not data.get('appointment_date') or not data.get('start_time'):
            send_json({'error': 'حدد التاريخ والوقت'}, 400)
            return True
        code = _next_code(conn, 'appointments', 'appointment_code', 'APT')
        atype = data.get('appointment_type') or 'consultation'
        if atype not in ('consultation', 'design_review', 'contract_signing', 'site_visit', 'meeting_internal', 'other'):
            atype = 'consultation'
        cur = conn.execute("""INSERT INTO appointments (appointment_code, customer_id, customer_name, customer_phone,
                                appointment_type, title, appointment_date, start_time, end_time, location,
                                assigned_to, notes, created_by, lead_id, status)
                              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'scheduled')""",
                           (code, lead.get('customer_id'), lead['full_name'], lead.get('phone'), atype,
                            data.get('title') or f"اجتماع مبيعات — {lead['full_name']}",
                            data['appointment_date'], data['start_time'], data.get('end_time'),
                            data.get('location'), data.get('assigned_to') or lead.get('assigned_to') or uid,
                            data.get('notes'), uid, lid))
        if lead['stage'] in ('new', 'contacted'):
            conn.execute("UPDATE leads SET stage='meeting', updated_at=CURRENT_TIMESTAMP WHERE id=?", (lid,))
        conn.commit()
        send_json({'success': True, 'id': cur.lastrowid})
        return True

    send_json({'error': 'المسار غير موجود'}, 404)
    return True


# ============================================================
# المبيعات: عروض الأسعار والعقود
# ============================================================
def _quote_full(conn, qid):
    q = _row(conn, """SELECT q.*, u.full_name AS created_by_name, c.full_name AS customer_name,
                             c.phone AS customer_phone, c.id_number AS customer_id_number,
                             e.operation_order, e.paid_amount, e.status AS event_status, e.event_code,
                             e.actual_date
                      FROM quotes q LEFT JOIN users u ON u.id=q.created_by
                      LEFT JOIN customers c ON c.id=q.customer_id
                      LEFT JOIN events e ON e.id=q.event_id WHERE q.id=?""", (qid,))
    if not q:
        return None
    q['items'] = _rows(conn, "SELECT * FROM quote_items WHERE quote_id=? ORDER BY sort_order, id", (qid,))
    if q.get('event_id'):
        q['payments'] = _rows(conn, """SELECT p.*, u.full_name AS received_by_name FROM event_payments p
                                       LEFT JOIN users u ON u.id=p.received_by WHERE p.event_id=? ORDER BY p.id""",
                              (q['event_id'],))
    else:
        q['payments'] = []
    s = ac.get_settings(conn)
    q['company'] = {k: s.get(k) for k in ('company_name', 'company_cr', 'company_vat', 'company_unified')}
    tkey = 'terms_' + ({'newborn': 'newborn_' + ('home' if q.get('venue_kind') == 'home' else 'hospital')}
                       .get(q['event_type'], q['event_type']))
    q['terms'] = s.get(tkey) or ''
    return q

def _save_items(conn, qid, items):
    conn.execute("DELETE FROM quote_items WHERE quote_id=?", (qid,))
    for i, it in enumerate(items or []):
        name = (it.get('name') or '').strip()
        if not name:
            continue
        conn.execute("INSERT INTO quote_items (quote_id, name, qty, notes, sort_order) VALUES (?,?,?,?,?)",
                     (qid, name, _num(it.get('qty'), 1), it.get('notes'), i))

def _quotes(conn, method, path, query, data, ctx, send_json):
    uid = ctx['user']['id']
    if path == '/api/quotes' and method == 'GET':
        sql = """SELECT q.id, q.quote_code, q.client_name, q.client_phone, q.event_type, q.venue_kind, q.venue_name,
                        q.expected_date, q.total_with_vat, q.deposit, q.status, q.valid_until, q.contract_code,
                        q.event_id, q.lead_id, q.customer_id, q.created_at, u.full_name AS created_by_name,
                        e.operation_order, e.paid_amount
                 FROM quotes q LEFT JOIN users u ON u.id=q.created_by
                 LEFT JOIN events e ON e.id=q.event_id WHERE 1=1"""
        params = []
        st = (query.get('status') or [None])[0]
        if st:
            sql += " AND q.status=?"; params.append(st)
        sql += " ORDER BY q.id DESC"
        send_json(_rows(conn, sql, params))
        return True

    if path == '/api/quotes' and method == 'POST':
        if data.get('event_type') not in TYPE_PREFIX:
            send_json({'error': 'اختر نوع المناسبة'}, 400)
            return True
        name = (data.get('client_name') or '').strip()
        cust = None
        if data.get('customer_id'):
            cust = _row(conn, "SELECT * FROM customers WHERE id=?", (data['customer_id'],))
        lead = _row(conn, "SELECT * FROM leads WHERE id=?", (data['lead_id'],)) if data.get('lead_id') else None
        if not name:
            name = (cust or {}).get('full_name') or (lead or {}).get('full_name') or ''
        if not name:
            send_json({'error': 'اكتب اسم العميل'}, 400)
            return True
        t = compute_totals(conn, data)
        code = _next_code(conn, 'quotes', 'quote_code', 'Q')
        valid_days = int(_num(ac.get_setting(conn, 'quote_valid_days', 7), 7))
        valid_until = (datetime.date.today() + datetime.timedelta(days=valid_days)).isoformat()
        cur = conn.execute("""INSERT INTO quotes (quote_code, lead_id, customer_id, client_name, client_phone, client_id_number,
                                event_type, venue_kind, venue_name, expected_date, event_time, guests_count, package,
                                execution_days, contract_value, additional, discount, vat_rate, vat_amount, total_with_vat,
                                insurance, deposit, status, valid_until, notes, internal_notes, created_by)
                              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?,?,?)""",
                           (code, data.get('lead_id'), data.get('customer_id'), name,
                            data.get('client_phone') or (cust or {}).get('phone') or (lead or {}).get('phone'),
                            data.get('client_id_number') or (cust or {}).get('id_number'),
                            data['event_type'], data.get('venue_kind'), data.get('venue_name'),
                            data.get('expected_date') or None, data.get('event_time'),
                            int(_num(data.get('guests_count'))) or None, data.get('package'),
                            int(_num(data.get('execution_days'))) or None,
                            _num(data.get('contract_value')), _num(data.get('additional')), _num(data.get('discount')),
                            t['vat_rate'], t['vat_amount'], t['total_with_vat'], t['insurance'], t['deposit'],
                            valid_until, data.get('notes'), data.get('internal_notes'), uid))
        qid = cur.lastrowid
        _save_items(conn, qid, data.get('items'))
        if lead and lead['stage'] in ('new', 'contacted', 'meeting'):
            conn.execute("UPDATE leads SET stage='quoted', updated_at=CURRENT_TIMESTAMP WHERE id=?", (lead['id'],))
        ac.audit(conn, uid, 'CREATE', 'quote', qid, new={'code': code, 'total': t['total_with_vat']})
        conn.commit()
        send_json({'success': True, 'id': qid, 'quote_code': code})
        return True

    m = re.match(r'^/api/quotes/(\d+)$', path)
    if m and method == 'GET':
        q = _quote_full(conn, int(m.group(1)))
        if not q:
            send_json({'error': 'غير موجود'}, 404)
            return True
        send_json(q)
        return True

    if m and method == 'PUT':
        qid = int(m.group(1))
        q = _row(conn, "SELECT * FROM quotes WHERE id=?", (qid,))
        if not q:
            send_json({'error': 'غير موجود'}, 404)
            return True
        if q['status'] == 'contracted':
            send_json({'error': 'العرض صار عقداً — أي تعديل بعد التعاقد يكون بملحق (المرحلة القادمة)'}, 400)
            return True
        merged = {**q, **data}
        if merged.get('event_type') not in TYPE_PREFIX:
            send_json({'error': 'اختر نوع المناسبة'}, 400)
            return True
        t = compute_totals(conn, merged)
        conn.execute("""UPDATE quotes SET client_name=?, client_phone=?, client_id_number=?, customer_id=?,
                          event_type=?, venue_kind=?, venue_name=?, expected_date=?, event_time=?, guests_count=?,
                          package=?, execution_days=?, contract_value=?, additional=?, discount=?, vat_rate=?,
                          vat_amount=?, total_with_vat=?, insurance=?, deposit=?, valid_until=?, notes=?,
                          internal_notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                     (merged.get('client_name'), merged.get('client_phone'), merged.get('client_id_number'),
                      merged.get('customer_id'), merged['event_type'], merged.get('venue_kind'),
                      merged.get('venue_name'), merged.get('expected_date') or None, merged.get('event_time'),
                      int(_num(merged.get('guests_count'))) or None, merged.get('package'),
                      int(_num(merged.get('execution_days'))) or None,
                      _num(merged.get('contract_value')), _num(merged.get('additional')), _num(merged.get('discount')),
                      t['vat_rate'], t['vat_amount'], t['total_with_vat'], t['insurance'], t['deposit'],
                      merged.get('valid_until'), merged.get('notes'), merged.get('internal_notes'), qid))
        if 'items' in data:
            _save_items(conn, qid, data['items'])
        ac.audit(conn, uid, 'UPDATE', 'quote', qid, new={'total': t['total_with_vat']})
        conn.commit()
        send_json({'success': True})
        return True

    if m and method == 'DELETE':
        qid = int(m.group(1))
        q = _row(conn, "SELECT status FROM quotes WHERE id=?", (qid,))
        if not q:
            send_json({'error': 'غير موجود'}, 404)
            return True
        if q['status'] == 'contracted':
            send_json({'error': 'ما ينحذف عرض صار عقداً'}, 400)
            return True
        conn.execute("DELETE FROM quote_items WHERE quote_id=?", (qid,))
        conn.execute("DELETE FROM quotes WHERE id=?", (qid,))
        ac.audit(conn, uid, 'DELETE', 'quote', qid)
        conn.commit()
        send_json({'success': True})
        return True

    m = re.match(r'^/api/quotes/(\d+)/status$', path)
    if m and method == 'POST':
        qid = int(m.group(1))
        st = data.get('status')
        if st not in ('draft', 'sent', 'accepted', 'rejected'):
            send_json({'error': 'حالة غير صحيحة'}, 400)
            return True
        q = _row(conn, "SELECT * FROM quotes WHERE id=?", (qid,))
        if not q or q['status'] == 'contracted':
            send_json({'error': 'ما يمكن تغيير الحالة'}, 400)
            return True
        conn.execute("UPDATE quotes SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (st, qid))
        if st == 'rejected' and q.get('lead_id'):
            conn.execute("UPDATE leads SET stage='lost', lost_reason=COALESCE(lost_reason,'رفض عرض السعر') WHERE id=? AND stage<>'won'",
                         (q['lead_id'],))
        ac.audit(conn, uid, 'STATUS', 'quote', qid, new={'status': st})
        conn.commit()
        send_json({'success': True})
        return True

    m = re.match(r'^/api/quotes/(\d+)/convert$', path)
    if m and method == 'POST':
        return _convert_quote(conn, int(m.group(1)), data, ctx, send_json)

    send_json({'error': 'المسار غير موجود'}, 404)
    return True

def _convert_quote(conn, qid, data, ctx, send_json):
    """تحويل عرض السعر لعقد: إنشاء/ربط العميل + إنشاء المناسبة برقم عقد B/W/E.
    رقم التشغيل O لا يُصرف هنا — يُصرف عند تسجيل العربون من المالية."""
    uid = ctx['user']['id']
    q = _row(conn, "SELECT * FROM quotes WHERE id=?", (qid,))
    if not q:
        send_json({'error': 'غير موجود'}, 404)
        return True
    if q['status'] == 'contracted':
        send_json({'error': 'العرض محوّل لعقد من قبل'}, 400)
        return True
    if not q.get('expected_date'):
        send_json({'error': 'حدد تاريخ المناسبة (المتوقع) قبل التحويل لعقد'}, 400)
        return True
    if _num(q.get('contract_value')) <= 0:
        send_json({'error': 'قيمة العقد صفر'}, 400)
        return True
    if not conn.execute("SELECT 1 FROM quote_items WHERE quote_id=?", (qid,)).fetchone():
        send_json({'error': 'أضف الخدمات المقدمة قبل التحويل لعقد'}, 400)
        return True

    cust_id = q.get('customer_id')
    if not cust_id:
        phone = (q.get('client_phone') or '').strip()
        existing = None
        if phone:
            existing = conn.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()
        if not existing:
            existing = conn.execute("SELECT id FROM customers WHERE full_name=?", (q['client_name'],)).fetchone()
        if existing:
            cust_id = existing[0]
        else:
            cur = conn.execute("""INSERT INTO customers (full_name, phone, id_number, customer_type, city, created_by)
                                  VALUES (?,?,?, 'individual', 'الرياض', ?)""",
                               (q['client_name'], phone or '', q.get('client_id_number'), uid))
            cust_id = cur.lastrowid

    contract_code = next_contract_code(conn, q['event_type'])
    year = datetime.date.today().year
    mx = 0
    for (v,) in conn.execute("SELECT event_code FROM events WHERE event_code LIKE ?", (f"EVT-{year}-%",)).fetchall():
        try:
            mx = max(mx, int(str(v).split('-')[-1]))
        except Exception:
            pass
    event_code = f"EVT-{year}-{mx + 1:04d}"
    title = f"{TYPE_LABELS.get(q['event_type'], 'مناسبة')} — {q['client_name']}"
    t = (q.get('event_time') or '').strip() or None
    cur = conn.execute("""INSERT INTO events (event_code, contract_code, customer_id, event_type, title, description,
                            event_date, event_start_time, venue_name, guests_count, status, total_price, paid_amount,
                            insurance_amount, discount, created_by, sync_source, quote_id)
                          VALUES (?,?,?,?,?,?,?,?,?,?, 'contract_issued', ?, 0, ?, ?, ?, 'system', ?)""",
                       (event_code, contract_code, cust_id, q['event_type'], title, q.get('notes'),
                        q['expected_date'], t, q.get('venue_name'), q.get('guests_count'),
                        q['total_with_vat'], q['insurance'], q['discount'], uid, qid))
    eid = cur.lastrowid
    conn.execute("""UPDATE quotes SET status='contracted', customer_id=?, event_id=?, contract_code=?,
                      contracted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                 (cust_id, eid, contract_code, qid))
    if q.get('lead_id'):
        conn.execute("UPDATE leads SET stage='won', customer_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (cust_id, q['lead_id']))
    conn.execute("INSERT OR IGNORE INTO event_confirmations (event_id, status) VALUES (?, 'pending')", (eid,))
    ac.audit(conn, uid, 'CONVERT', 'quote', qid, new={'event_id': eid, 'contract_code': contract_code})
    conn.commit()
    send_json({'success': True, 'event_id': eid, 'contract_code': contract_code, 'customer_id': cust_id})
    return True


# ============================================================
# خدمة العملاء: تأكيد مواعيد المناسبات
# ============================================================
def _confirmations(conn, method, path, query, data, ctx, send_json):
    uid = ctx['user']['id']
    s = ac.get_settings(conn)
    window = int(_num(s.get('confirm_window_days'), 30))
    recontact = int(_num(s.get('confirm_recontact_days'), 7))
    rush_days = int(_num(s.get('rush_fee_weeks'), 3)) * 7

    if path == '/api/confirmations' and method == 'GET':
        etype = (query.get('type') or [''])[0]
        sql = """SELECT e.id AS event_id, e.event_code, e.contract_code, e.operation_order, e.title, e.event_type,
                        e.event_date AS expected_date, e.actual_date, e.event_start_time, e.venue_name, e.status AS event_status,
                        e.sync_source, c.id AS customer_id, c.full_name AS customer_name, c.phone AS customer_phone,
                        c.emergency_phone, ec.status AS conf_status, ec.confirmed_date, ec.confirmed_time,
                        ec.next_contact_date, ec.last_contact_at, ec.rush_fee_due, ec.notes AS conf_notes,
                        (SELECT COUNT(*) FROM confirmation_logs l WHERE l.event_id=e.id) AS contacts_count
                 FROM events e JOIN customers c ON c.id=e.customer_id
                 LEFT JOIN event_confirmations ec ON ec.event_id=e.id
                 WHERE e.status NOT IN ('cancelled','completed','closed','lead','quoted')
                   AND COALESCE(ec.confirmed_date, e.actual_date, e.event_date) >= date('now','-3 day')"""
        params = []
        if etype:
            sql += " AND e.event_type=?"; params.append(etype)
        sql += " ORDER BY COALESCE(ec.confirmed_date, e.actual_date, e.event_date)"
        rows = _rows(conn, sql, params)
        today = datetime.date.today()
        for r in rows:
            st = r.get('conf_status') or ('confirmed' if r.get('actual_date') else 'pending')
            r['conf_status'] = st
            try:
                exp = datetime.date.fromisoformat(str(r['expected_date'])[:10])
                r['days_to_expected'] = (exp - today).days
            except Exception:
                r['days_to_expected'] = None
            due = False
            if st in ('pending', 'rescheduled'):
                ncd = r.get('next_contact_date')
                if ncd:
                    due = str(ncd)[:10] <= today.isoformat()
                elif r['days_to_expected'] is not None and r['days_to_expected'] <= window:
                    due = True
            r['needs_contact'] = due
            r['final_date'] = r.get('confirmed_date') or r.get('actual_date') or r['expected_date']
        send_json({'rows': rows, 'settings': {'window': window, 'recontact': recontact, 'rush_days': rush_days}})
        return True

    m = re.match(r'^/api/confirmations/(\d+)/log$', path)
    if m and method == 'GET':
        send_json(_rows(conn, """SELECT l.*, u.full_name AS by_name FROM confirmation_logs l
                                 LEFT JOIN users u ON u.id=l.created_by WHERE l.event_id=? ORDER BY l.id DESC""",
                        (int(m.group(1)),)))
        return True

    m = re.match(r'^/api/confirmations/(\d+)$', path)
    if m and method == 'POST':
        eid = int(m.group(1))
        ev = _row(conn, "SELECT * FROM events WHERE id=?", (eid,))
        if not ev:
            send_json({'error': 'المناسبة غير موجودة'}, 404)
            return True
        conn.execute("INSERT OR IGNORE INTO event_confirmations (event_id, status) VALUES (?, 'pending')", (eid,))
        action = data.get('action')
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        note = (data.get('note') or '').strip()
        if action == 'log':
            result = data.get('result') or 'no_answer'
            nxt = data.get('next_contact_date') or (datetime.date.today() + datetime.timedelta(
                days=1 if result == 'no_answer' else recontact)).isoformat()
            conn.execute("INSERT INTO confirmation_logs (event_id, channel, result, note, created_by) VALUES (?,?,?,?,?)",
                         (eid, data.get('channel') or 'call', result, note, uid))
            conn.execute("""UPDATE event_confirmations SET last_contact_at=?, next_contact_date=?, updated_by=?,
                              updated_at=CURRENT_TIMESTAMP WHERE event_id=?""", (now, nxt, uid, eid))
        elif action == 'confirm':
            d = data.get('confirmed_date')
            if not d:
                send_json({'error': 'حدد التاريخ المؤكد'}, 400)
                return True
            rush = 0
            try:
                if ev['event_type'] == 'newborn':
                    exp = datetime.date.fromisoformat(str(ev['event_date'])[:10])
                    if (exp - datetime.date.fromisoformat(d)).days > rush_days:
                        rush = 1
            except Exception:
                pass
            conn.execute("""UPDATE event_confirmations SET status='confirmed', confirmed_date=?, confirmed_time=?,
                              rush_fee_due=?, next_contact_date=NULL, last_contact_at=?, notes=COALESCE(?, notes),
                              updated_by=?, updated_at=CURRENT_TIMESTAMP WHERE event_id=?""",
                         (d, data.get('confirmed_time'), rush, now, note or None, uid, eid))
            conn.execute("UPDATE events SET actual_date=?, event_start_time=COALESCE(?, event_start_time), updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         (d, data.get('confirmed_time') or None, eid))
            conn.execute("INSERT INTO confirmation_logs (event_id, channel, result, note, created_by) VALUES (?,?,?,?,?)",
                         (eid, data.get('channel') or 'call', 'confirmed', f"تأكيد التاريخ {d}" + (f" — {note}" if note else ''), uid))
            ac.audit(conn, uid, 'CONFIRM_DATE', 'event', eid, old={'expected': ev['event_date'], 'actual': ev['actual_date']},
                     new={'confirmed_date': d, 'rush_fee_due': rush})
        elif action == 'reset':
            conn.execute("""UPDATE event_confirmations SET status='rescheduled', confirmed_date=NULL, confirmed_time=NULL,
                              rush_fee_due=0, next_contact_date=?, updated_by=?, updated_at=CURRENT_TIMESTAMP WHERE event_id=?""",
                         (_today(), uid, eid))
            conn.execute("UPDATE events SET actual_date=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?", (eid,))
            conn.execute("INSERT INTO confirmation_logs (event_id, channel, result, note, created_by) VALUES (?,?,?,?,?)",
                         (eid, 'system', 'rescheduled', note or 'إلغاء التأكيد وإعادة المتابعة', uid))
            ac.audit(conn, uid, 'UNCONFIRM_DATE', 'event', eid, old={'actual': ev['actual_date']})
        else:
            send_json({'error': 'إجراء غير معروف'}, 400)
            return True
        conn.commit()
        send_json({'success': True})
        return True

    send_json({'error': 'المسار غير موجود'}, 404)
    return True


# ============================================================
# ملف العميل الشامل
# ============================================================
def _customer_profile(conn, cid, ctx, send_json):
    perms = ctx['perms']
    c = _row(conn, "SELECT * FROM customers WHERE id=?", (cid,))
    if not c:
        send_json({'error': 'العميل غير موجود'}, 404)
        return True
    show_money = ac.can(perms, 'payments', 'view') or ac.can(perms, 'quotes', 'view') or ac.can(perms, 'finance', 'view')
    c['events'] = _rows(conn, """SELECT e.id, e.event_code, e.contract_code, e.operation_order, e.title, e.event_type,
                                        e.event_date, e.actual_date, e.venue_name, e.status, e.total_price, e.paid_amount,
                                        e.sync_source, ec.status AS conf_status, ec.confirmed_date
                                 FROM events e LEFT JOIN event_confirmations ec ON ec.event_id=e.id
                                 WHERE e.customer_id=? ORDER BY e.event_date DESC""", (cid,))
    if not show_money:
        for e in c['events']:
            e.pop('total_price', None); e.pop('paid_amount', None)
    c['appointments'] = _rows(conn, """SELECT a.*, u.full_name AS assigned_name FROM appointments a
                                       LEFT JOIN users u ON u.id=a.assigned_to
                                       WHERE a.customer_id=? OR (a.customer_id IS NULL AND a.customer_phone=? AND a.customer_phone<>'')
                                       ORDER BY a.appointment_date DESC""", (cid, c.get('phone') or ''))
    c['quotes'] = _rows(conn, "SELECT id, quote_code, status, total_with_vat, contract_code, created_at FROM quotes WHERE customer_id=? ORDER BY id DESC", (cid,)) \
        if ac.can(perms, 'quotes', 'view') else []
    c['leads'] = _rows(conn, "SELECT id, lead_code, stage, source, created_at FROM leads WHERE customer_id=? ORDER BY id DESC", (cid,)) \
        if ac.can(perms, 'leads', 'view') else []
    c['show_money'] = show_money
    send_json(c)
    return True


# ============================================================
# المالية: الدفعات والمستحقات
# ============================================================
def _recalc_paid(conn, eid):
    paid = conn.execute("SELECT COALESCE(SUM(amount),0) FROM event_payments WHERE event_id=?", (eid,)).fetchone()[0]
    conn.execute("UPDATE events SET paid_amount=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (paid, eid))
    return paid

def _payments(conn, method, path, query, data, ctx, send_json):
    uid = ctx['user']['id']
    if path == '/api/payments/dues' and method == 'GET':
        system = _rows(conn, """SELECT e.id AS event_id, e.event_code, e.contract_code, e.operation_order, e.title,
                                       e.event_type, e.event_date, e.actual_date, e.status, e.total_price, e.paid_amount,
                                       e.insurance_amount, c.full_name AS customer_name, c.phone AS customer_phone,
                                       q.id AS quote_id, q.quote_code, q.deposit
                                FROM events e JOIN customers c ON c.id=e.customer_id
                                LEFT JOIN quotes q ON q.id=e.quote_id
                                WHERE e.sync_source='system' AND e.quote_id IS NOT NULL AND e.status<>'cancelled'
                                ORDER BY e.event_date""")
        for r in system:
            r['remaining'] = round((r['total_price'] or 0) - (r['paid_amount'] or 0), 2)
            r['deposit_paid'] = (r['paid_amount'] or 0) >= (r['deposit'] or 0) - 0.01
        sheet = _rows(conn, """SELECT contract_code, operation_order, customer_name, event_type, expected_date, actual_date,
                                      total_revenue, received, remaining, status
                               FROM sheet_contracts WHERE COALESCE(remaining,0) > 0.5 ORDER BY expected_date""")
        send_json({'system': system, 'sheet': sheet})
        return True

    if path == '/api/payments' and method == 'GET':
        eid = (query.get('event_id') or [None])[0]
        sql = """SELECT p.*, u.full_name AS received_by_name, e.contract_code, e.operation_order, c.full_name AS customer_name
                 FROM event_payments p LEFT JOIN users u ON u.id=p.received_by
                 LEFT JOIN events e ON e.id=p.event_id LEFT JOIN customers c ON c.id=e.customer_id"""
        params = []
        if eid:
            sql += " WHERE p.event_id=?"; params.append(eid)
        sql += " ORDER BY p.id DESC LIMIT 500"
        send_json(_rows(conn, sql, params))
        return True

    if path == '/api/payments' and method == 'POST':
        eid = data.get('event_id')
        amount = _num(data.get('amount'))
        ev = _row(conn, "SELECT * FROM events WHERE id=?", (eid,))
        if not ev:
            send_json({'error': 'المناسبة غير موجودة'}, 404)
            return True
        if ev.get('sync_source') != 'system':
            send_json({'error': 'هذا العقد من جدول Google — دفعاته تُسجّل في مولّد العقود حتى يتم نقل البيانات'}, 400)
            return True
        if amount <= 0:
            send_json({'error': 'اكتب مبلغاً صحيحاً'}, 400)
            return True
        remaining = (ev['total_price'] or 0) - (ev['paid_amount'] or 0)
        if amount > remaining + 0.01:
            send_json({'error': f'المبلغ أكبر من المتبقي ({remaining:,.2f})'}, 400)
            return True
        conn.execute("""INSERT INTO event_payments (event_id, amount, payment_method, payment_type, reference,
                          payment_date, received_by, notes) VALUES (?,?,?,?,?,?,?,?)""",
                     (eid, amount, data.get('payment_method') or 'bank_transfer', data.get('payment_type') or 'installment',
                      data.get('reference'), data.get('payment_date') or _today(), uid, data.get('notes')))
        paid = _recalc_paid(conn, eid)
        new_op = None
        q = _row(conn, "SELECT deposit FROM quotes WHERE id=?", (ev.get('quote_id'),)) if ev.get('quote_id') else None
        deposit = (q or {}).get('deposit') or (ev['total_price'] or 0) * 0.5
        if not ev.get('operation_order') and paid >= deposit - 0.01:
            new_op = next_operation_order(conn)
            conn.execute("UPDATE events SET operation_order=?, status=CASE WHEN status='contract_issued' THEN 'contracted' ELSE status END WHERE id=?",
                         (new_op, eid))
        ac.audit(conn, uid, 'PAYMENT', 'event', eid, new={'amount': amount, 'operation_order': new_op})
        conn.commit()
        send_json({'success': True, 'paid': paid, 'operation_order': new_op})
        return True

    m = re.match(r'^/api/payments/(\d+)$', path)
    if m and method == 'DELETE':
        pid = int(m.group(1))
        p = _row(conn, "SELECT p.*, e.sync_source FROM event_payments p JOIN events e ON e.id=p.event_id WHERE p.id=?", (pid,))
        if not p:
            send_json({'error': 'غير موجود'}, 404)
            return True
        if p['sync_source'] != 'system':
            send_json({'error': 'دفعة عقد من Google — ما تنحذف من هنا'}, 400)
            return True
        conn.execute("DELETE FROM event_payments WHERE id=?", (pid,))
        _recalc_paid(conn, p['event_id'])
        ac.audit(conn, uid, 'DELETE_PAYMENT', 'event', p['event_id'], old=p)
        conn.commit()
        send_json({'success': True, 'note': 'رقم التشغيل (إن صُرف) يبقى كما هو'})
        return True

    send_json({'error': 'المسار غير موجود'}, 404)
    return True
