"""
الموارد البشرية والأصول — نظام أبيلا (الإصدار 4.1)
====================================================
- الموظفون: الملف الوظيفي، الوثائق وتنبيهات انتهائها، الربط بحساب الدخول، تقدير مكافأة نهاية الخدمة
- الإجازات: الطلب والاعتماد والأرصدة (م109 / م117 / تعديلات 2025)
- الرواتب: مسيّر شهري + التأمينات + السلف وأقساطها + الخصومات
- المهام: إسناد مهام للموظفين ومتابعتها
- الأصول: المعدات والأجهزة والسيارات، العُهد، الصيانة، وثائق السيارات
- الخدمة الذاتية: كل موظف يشوف ملفه ورصيده ويطلب إجازة ويحدّث مهامه
"""
import re, json, datetime
import access_control as ac

LEAVE_TYPES = {
    'annual':      ('سنوية', None),
    'sick':        ('مرضية', None),
    'unpaid':      ('بدون راتب', None),
    'marriage':    ('زواج', 5),
    'paternity':   ('مولود', 3),
    'bereavement': ('وفاة (زوج/أصل/فرع)', 5),
    'sibling_death': ('وفاة أخ/أخت', 2),
    'maternity':   ('وضع (أمومة)', 84),
    'iddah':       ('عدة', 130),
    'hajj':        ('حج', 15),
    'exam':        ('امتحان', None),
    'other':       ('أخرى', None),
}
ASSET_CATS = {'vehicle': 'VEH', 'equipment': 'EQP', 'tool': 'TLS', 'device': 'DEV', 'furniture': 'FUR', 'other': 'OTH'}
SALARY_FIELDS = ('basic_salary', 'housing_allowance', 'transport_allowance', 'other_allowances', 'iban', 'bank_name')


def _rows(conn, sql, p=()):
    return [dict(r) for r in conn.execute(sql, p).fetchall()]

def _row(conn, sql, p=()):
    r = conn.execute(sql, p).fetchone()
    return dict(r) if r else None

def _num(v, d=0.0):
    try:
        return d if v in (None, '') else float(v)
    except (TypeError, ValueError):
        return d

def _d(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None

def _today():
    return datetime.date.today()


# ============================================================
# الجداول
# ============================================================
def init_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp_no TEXT UNIQUE,
        full_name TEXT NOT NULL,
        user_id INTEGER,
        nationality TEXT,
        is_saudi INTEGER DEFAULT 0,
        gender TEXT,
        id_number TEXT,
        id_expiry TEXT,
        passport_no TEXT,
        passport_expiry TEXT,
        phone TEXT,
        email TEXT,
        department TEXT,
        job_title TEXT,
        manager_id INTEGER,
        hire_date TEXT,
        probation_end TEXT,
        contract_type TEXT DEFAULT 'fixed',
        contract_end TEXT,
        work_location TEXT,
        basic_salary REAL DEFAULT 0,
        housing_allowance REAL DEFAULT 0,
        transport_allowance REAL DEFAULT 0,
        other_allowances REAL DEFAULT 0,
        iban TEXT,
        bank_name TEXT,
        gosi_registered INTEGER DEFAULT 1,
        gosi_category TEXT DEFAULT 'legacy',
        leave_opening_balance REAL DEFAULT 0,
        leave_opening_date TEXT,
        status TEXT DEFAULT 'active',
        termination_date TEXT,
        termination_reason TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        leave_type TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        days REAL NOT NULL,
        reason TEXT,
        status TEXT DEFAULT 'pending',
        requested_by INTEGER,
        decided_by INTEGER,
        decided_at TEXT,
        decision_note TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS payroll_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT UNIQUE NOT NULL,
        status TEXT DEFAULT 'draft',
        notes TEXT,
        created_by INTEGER,
        approved_by INTEGER,
        approved_at TEXT,
        paid_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS payroll_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        employee_id INTEGER NOT NULL,
        days_worked REAL DEFAULT 30,
        basic REAL DEFAULT 0, housing REAL DEFAULT 0, transport REAL DEFAULT 0, other_allow REAL DEFAULT 0,
        overtime REAL DEFAULT 0, bonus REAL DEFAULT 0,
        unpaid_leave_days REAL DEFAULT 0, unpaid_leave_ded REAL DEFAULT 0,
        absence_ded REAL DEFAULT 0, penalty_ded REAL DEFAULT 0, advance_ded REAL DEFAULT 0, other_ded REAL DEFAULT 0,
        gosi_employee REAL DEFAULT 0, gosi_employer REAL DEFAULT 0,
        gross REAL DEFAULT 0, total_ded REAL DEFAULT 0, net REAL DEFAULT 0,
        notes TEXT
    );
    CREATE TABLE IF NOT EXISTS advances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        monthly_installment REAL NOT NULL,
        start_period TEXT NOT NULL,
        remaining REAL NOT NULL,
        status TEXT DEFAULT 'active',
        reason TEXT,
        created_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS hr_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        assigned_to INTEGER,
        assigned_by INTEGER,
        due_date TEXT,
        priority TEXT DEFAULT 'normal',
        status TEXT DEFAULT 'todo',
        related TEXT,
        completion_note TEXT,
        completed_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_code TEXT UNIQUE,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        brand TEXT, model TEXT, serial_no TEXT,
        purchase_date TEXT, purchase_price REAL, supplier TEXT, useful_life_years REAL,
        location TEXT,
        status TEXT DEFAULT 'active',
        custodian_id INTEGER,
        custody_since TEXT,
        plate_no TEXT, vin TEXT, year INTEGER, color TEXT,
        registration_expiry TEXT, insurance_expiry TEXT, inspection_expiry TEXT, authorization_expiry TEXT,
        odometer INTEGER, next_service_km INTEGER, next_service_date TEXT,
        warranty_expiry TEXT,
        notes TEXT,
        created_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS asset_custody_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL,
        employee_id INTEGER,
        action TEXT,
        condition TEXT,
        notes TEXT,
        created_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS asset_maintenance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL,
        m_date TEXT NOT NULL,
        m_type TEXT,
        description TEXT,
        cost REAL DEFAULT 0,
        vendor TEXT,
        odometer INTEGER,
        next_due_date TEXT,
        next_due_km INTEGER,
        created_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_leave_emp ON leave_requests(employee_id);
    CREATE INDEX IF NOT EXISTS idx_pl_run ON payroll_lines(run_id);
    CREATE INDEX IF NOT EXISTS idx_tasks_to ON hr_tasks(assigned_to);
    CREATE INDEX IF NOT EXISTS idx_custody_asset ON asset_custody_log(asset_id);
    CREATE INDEX IF NOT EXISTS idx_maint_asset ON asset_maintenance(asset_id);
    """)
    conn.commit()


# ============================================================
# حسابات
# ============================================================
def monthly_wage(e):
    return _num(e.get('basic_salary')) + _num(e.get('housing_allowance')) + _num(e.get('transport_allowance')) + _num(e.get('other_allowances'))

def service_years(e, until=None):
    h = _d(e.get('hire_date'))
    if not h:
        return 0
    u = until or _d(e.get('termination_date')) or _today()
    return max((u - h).days, 0) / 365.25

def end_of_service(e, until=None):
    """تقدير مكافأة نهاية الخدمة — م84 (نصف شهر عن كل سنة من الخمس الأولى، وشهر عمّا بعدها)
    و م85 (عند الاستقالة: لا شيء قبل سنتين، الثلث 2–5، الثلثان 5–10، كاملة 10+)"""
    y = service_years(e, until)
    w = monthly_wage(e)
    full = 0.5 * w * min(y, 5) + w * max(y - 5, 0)
    if y < 2:
        f = 0
    elif y < 5:
        f = 1 / 3
    elif y < 10:
        f = 2 / 3
    else:
        f = 1
    return {'years': round(y, 2), 'wage': round(w, 2), 'termination': round(full, 2),
            'resignation': round(full * f, 2), 'resignation_factor': f}

def annual_balance(conn, e, asof=None):
    asof = asof or _today()
    base = _num(ac.get_setting(conn, 'annual_leave_days', 21), 21)
    after5 = _num(ac.get_setting(conn, 'annual_leave_days_5y', 30), 30)
    hire = _d(e.get('hire_date'))
    start = _d(e.get('leave_opening_date')) or hire
    if not start:
        return {'entitlement': base, 'accrued': 0, 'taken': 0, 'pending': 0, 'balance': _num(e.get('leave_opening_balance'))}
    five = None
    if hire:
        try:
            five = hire.replace(year=hire.year + 5)
        except ValueError:
            five = hire + datetime.timedelta(days=5 * 365 + 1)
    accrued = 0.0
    if asof > start:
        if five and five <= start:
            accrued = (asof - start).days * after5 / 365
        elif five and five < asof:
            accrued = (five - start).days * base / 365 + (asof - five).days * after5 / 365
        else:
            accrued = (asof - start).days * base / 365
    taken = conn.execute("""SELECT COALESCE(SUM(days),0) FROM leave_requests WHERE employee_id=? AND leave_type='annual'
                            AND status='approved' AND start_date>=?""", (e['id'], start.isoformat())).fetchone()[0]
    pending = conn.execute("""SELECT COALESCE(SUM(days),0) FROM leave_requests WHERE employee_id=? AND leave_type='annual'
                              AND status='pending'""", (e['id'],)).fetchone()[0]
    ent = after5 if (five and asof >= five) else base
    bal = _num(e.get('leave_opening_balance')) + accrued - taken
    return {'entitlement': ent, 'accrued': round(accrued, 1), 'taken': taken, 'pending': pending,
            'balance': round(bal, 1), 'available': round(bal - pending, 1)}

def sick_used(conn, emp_id):
    since = (_today() - datetime.timedelta(days=365)).isoformat()
    used = conn.execute("""SELECT COALESCE(SUM(days),0) FROM leave_requests WHERE employee_id=? AND leave_type='sick'
                           AND status='approved' AND start_date>=?""", (emp_id, since)).fetchone()[0]
    # م117: 30 يوم بأجر كامل، 60 بثلاثة أرباع، 30 بدون أجر خلال السنة
    return {'used': used, 'full_pay_left': max(30 - used, 0), 'three_quarter_left': max(90 - max(used, 30), 0) if used < 90 else 0}

def _leave_days(a, b):
    da, db = _d(a), _d(b)
    if not da or not db or db < da:
        return None
    return (db - da).days + 1

def _overlap_days(a1, b1, a2, b2):
    s, e = max(a1, a2), min(b1, b2)
    return max((e - s).days + 1, 0)


# ============================================================
# الموجّه
# ============================================================
def handle(h, conn, method, path, query, data, ctx, send_json):
    if path.startswith('/api/hr/'):
        return _hr(conn, method, path, query, data, ctx, send_json)
    if path.startswith('/api/assets'):
        return _assets(conn, method, path, query, data, ctx, send_json)
    if path.startswith('/api/me/'):
        return _self(conn, method, path, query, data, ctx, send_json)
    return False

def _err(send_json, msg, code=400):
    send_json({'error': msg}, code)
    return True

def _ok(send_json, payload=None):
    send_json(payload if payload is not None else {'success': True})
    return True


# ============================================================
# /api/hr/*
# ============================================================
def _hr(conn, method, path, query, data, ctx, send_json):
    uid = ctx['user']['id']
    perms = ctx['perms']
    can_pay = ac.can(perms, 'payroll', 'view')

    # ---------- تنبيهات ----------
    if path == '/api/hr/alerts' and method == 'GET':
        return _ok(send_json, alerts(conn, perms))

    # ---------- الموظفون ----------
    if path == '/api/hr/employees' and method == 'GET':
        rows = _rows(conn, """SELECT e.*, u.username, u.is_active AS user_active, m.full_name AS manager_name
                              FROM employees e LEFT JOIN users u ON u.id=e.user_id
                              LEFT JOIN employees m ON m.id=e.manager_id
                              ORDER BY CASE e.status WHEN 'terminated' THEN 1 ELSE 0 END, e.department, e.full_name""")
        for r in rows:
            r['wage'] = monthly_wage(r)
            if not can_pay:
                for f in SALARY_FIELDS + ('wage',):
                    r.pop(f, None)
        return _ok(send_json, rows)

    if path == '/api/hr/employees' and method == 'POST':
        return _emp_save(conn, None, data, uid, can_pay, send_json)

    m = re.match(r'^/api/hr/employees/(\d+)$', path)
    if m and method == 'GET':
        eid = int(m.group(1))
        e = _row(conn, """SELECT e.*, u.username, u.role AS user_role, m.full_name AS manager_name FROM employees e
                          LEFT JOIN users u ON u.id=e.user_id LEFT JOIN employees m ON m.id=e.manager_id WHERE e.id=?""", (eid,))
        if not e:
            return _err(send_json, 'الموظف غير موجود', 404)
        e['annual'] = annual_balance(conn, e)
        e['sick'] = sick_used(conn, eid)
        e['leaves'] = _rows(conn, "SELECT * FROM leave_requests WHERE employee_id=? ORDER BY start_date DESC LIMIT 50", (eid,))
        e['custody'] = _rows(conn, "SELECT id, asset_code, name, category, plate_no, custody_since FROM assets WHERE custodian_id=? AND status<>'disposed'", (eid,))
        e['tasks_open'] = conn.execute("SELECT COUNT(*) FROM hr_tasks WHERE assigned_to=? AND status IN ('todo','in_progress')", (e.get('user_id') or -1,)).fetchone()[0]
        if can_pay:
            e['wage'] = monthly_wage(e)
            e['eos'] = end_of_service(e)
            e['advances'] = _rows(conn, "SELECT * FROM advances WHERE employee_id=? ORDER BY id DESC", (eid,))
            e['payslips'] = _rows(conn, """SELECT r.period, r.status, l.gross, l.total_ded, l.net FROM payroll_lines l
                                           JOIN payroll_runs r ON r.id=l.run_id WHERE l.employee_id=? ORDER BY r.period DESC LIMIT 12""", (eid,))
        else:
            for f in SALARY_FIELDS:
                e.pop(f, None)
        return _ok(send_json, e)

    if m and method == 'PUT':
        return _emp_save(conn, int(m.group(1)), data, uid, can_pay, send_json)

    if m and method == 'DELETE':
        eid = int(m.group(1))
        if conn.execute("SELECT 1 FROM payroll_lines WHERE employee_id=?", (eid,)).fetchone() or \
           conn.execute("SELECT 1 FROM leave_requests WHERE employee_id=?", (eid,)).fetchone():
            return _err(send_json, 'الموظف له سجلات رواتب أو إجازات — استخدم «إنهاء الخدمة» بدل الحذف')
        if conn.execute("SELECT 1 FROM assets WHERE custodian_id=?", (eid,)).fetchone():
            return _err(send_json, 'عليه عُهد — استلمها أولاً')
        conn.execute("DELETE FROM employees WHERE id=?", (eid,))
        ac.audit(conn, uid, 'DELETE', 'employee', eid)
        conn.commit()
        return _ok(send_json)

    # ---------- الإجازات ----------
    if path == '/api/hr/leaves' and method == 'GET':
        st = (query.get('status') or [''])[0]
        sql = """SELECT l.*, e.full_name AS employee_name, e.department, u.full_name AS decided_by_name, r.full_name AS requested_by_name
                 FROM leave_requests l JOIN employees e ON e.id=l.employee_id
                 LEFT JOIN users u ON u.id=l.decided_by LEFT JOIN users r ON r.id=l.requested_by"""
        p = []
        if st:
            sql += " WHERE l.status=?"; p.append(st)
        sql += " ORDER BY CASE l.status WHEN 'pending' THEN 0 ELSE 1 END, l.start_date DESC LIMIT 500"
        rows = _rows(conn, sql, p)
        for r in rows:
            r['type_label'] = LEAVE_TYPES.get(r['leave_type'], (r['leave_type'],))[0]
        return _ok(send_json, {'rows': rows, 'types': {k: {'label': v[0], 'max': v[1]} for k, v in LEAVE_TYPES.items()}})

    if path == '/api/hr/leaves' and method == 'POST':
        emp = _row(conn, "SELECT * FROM employees WHERE id=?", (data.get('employee_id'),))
        if not emp:
            return _err(send_json, 'اختر الموظف')
        res = _create_leave(conn, emp, data, uid)
        if isinstance(res, str):
            return _err(send_json, res)
        if data.get('approve_now') and ac.can(perms, 'leaves', 'edit'):
            conn.execute("UPDATE leave_requests SET status='approved', decided_by=?, decided_at=CURRENT_TIMESTAMP WHERE id=?", (uid, res))
        conn.commit()
        return _ok(send_json, {'success': True, 'id': res})

    m = re.match(r'^/api/hr/leaves/(\d+)/decision$', path)
    if m and method == 'POST':
        lid = int(m.group(1))
        lr = _row(conn, "SELECT * FROM leave_requests WHERE id=?", (lid,))
        if not lr:
            return _err(send_json, 'الطلب غير موجود', 404)
        dec = data.get('decision')
        if dec not in ('approved', 'rejected'):
            return _err(send_json, 'قرار غير صحيح')
        if lr['status'] not in ('pending', 'approved'):
            return _err(send_json, 'الطلب مقفل')
        conn.execute("UPDATE leave_requests SET status=?, decided_by=?, decided_at=CURRENT_TIMESTAMP, decision_note=? WHERE id=?",
                     (dec, uid, data.get('note'), lid))
        ac.audit(conn, uid, 'LEAVE_' + dec.upper(), 'leave', lid)
        conn.commit()
        return _ok(send_json)

    m = re.match(r'^/api/hr/leaves/(\d+)$', path)
    if m and method == 'DELETE':
        conn.execute("UPDATE leave_requests SET status='cancelled' WHERE id=?", (int(m.group(1)),))
        ac.audit(conn, uid, 'LEAVE_CANCEL', 'leave', int(m.group(1)))
        conn.commit()
        return _ok(send_json)

    # ---------- السلف ----------
    if path == '/api/hr/advances' and method == 'GET':
        return _ok(send_json, _rows(conn, """SELECT a.*, e.full_name AS employee_name FROM advances a
                                             JOIN employees e ON e.id=a.employee_id ORDER BY a.status, a.id DESC"""))
    if path == '/api/hr/advances' and method == 'POST':
        amt, inst = _num(data.get('amount')), _num(data.get('monthly_installment'))
        if amt <= 0 or inst <= 0:
            return _err(send_json, 'اكتب المبلغ والقسط الشهري')
        if not re.match(r'^\d{4}-\d{2}$', data.get('start_period') or ''):
            return _err(send_json, 'حدد شهر بداية الخصم')
        if not conn.execute("SELECT 1 FROM employees WHERE id=?", (data.get('employee_id'),)).fetchone():
            return _err(send_json, 'اختر الموظف')
        cur = conn.execute("""INSERT INTO advances (employee_id, amount, monthly_installment, start_period, remaining, reason, created_by)
                              VALUES (?,?,?,?,?,?,?)""", (data['employee_id'], amt, min(inst, amt), data['start_period'], amt, data.get('reason'), uid))
        ac.audit(conn, uid, 'CREATE', 'advance', cur.lastrowid, new={'amount': amt})
        conn.commit()
        return _ok(send_json, {'success': True, 'id': cur.lastrowid})
    m = re.match(r'^/api/hr/advances/(\d+)$', path)
    if m and method == 'DELETE':
        a = _row(conn, "SELECT * FROM advances WHERE id=?", (int(m.group(1)),))
        if not a:
            return _err(send_json, 'غير موجودة', 404)
        if a['remaining'] < a['amount'] - 0.01:
            return _err(send_json, 'بدأ خصمها من الرواتب — ما تنحذف')
        conn.execute("DELETE FROM advances WHERE id=?", (a['id'],))
        conn.commit()
        return _ok(send_json)

    # ---------- الرواتب ----------
    if path == '/api/hr/payroll' and method == 'GET':
        return _ok(send_json, _rows(conn, """SELECT r.*, (SELECT COUNT(*) FROM payroll_lines l WHERE l.run_id=r.id) AS employees,
                                             (SELECT COALESCE(SUM(net),0) FROM payroll_lines l WHERE l.run_id=r.id) AS total_net,
                                             (SELECT COALESCE(SUM(gross),0) FROM payroll_lines l WHERE l.run_id=r.id) AS total_gross,
                                             (SELECT COALESCE(SUM(gosi_employer),0) FROM payroll_lines l WHERE l.run_id=r.id) AS total_gosi_employer
                                             FROM payroll_runs r ORDER BY r.period DESC"""))
    if path == '/api/hr/payroll' and method == 'POST':
        period = data.get('period') or ''
        if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', period):
            return _err(send_json, 'حدد الشهر')
        if conn.execute("SELECT 1 FROM payroll_runs WHERE period=?", (period,)).fetchone():
            return _err(send_json, 'مسيّر هذا الشهر موجود')
        cur = conn.execute("INSERT INTO payroll_runs (period, created_by) VALUES (?,?)", (period, uid))
        _generate_lines(conn, cur.lastrowid, period)
        ac.audit(conn, uid, 'CREATE', 'payroll', cur.lastrowid, new={'period': period})
        conn.commit()
        return _ok(send_json, {'success': True, 'id': cur.lastrowid})

    m = re.match(r'^/api/hr/payroll/(\d+)$', path)
    if m and method == 'GET':
        rid = int(m.group(1))
        run = _row(conn, "SELECT r.*, u.full_name AS approved_by_name FROM payroll_runs r LEFT JOIN users u ON u.id=r.approved_by WHERE r.id=?", (rid,))
        if not run:
            return _err(send_json, 'غير موجود', 404)
        run['lines'] = _rows(conn, """SELECT l.*, e.full_name, e.emp_no, e.department, e.job_title, e.iban, e.bank_name, e.is_saudi, e.id_number
                                      FROM payroll_lines l JOIN employees e ON e.id=l.employee_id WHERE l.run_id=? ORDER BY e.department, e.full_name""", (rid,))
        run['company'] = ac.get_setting(conn, 'company_name')
        return _ok(send_json, run)
    if m and method == 'DELETE':
        rid = int(m.group(1))
        run = _row(conn, "SELECT * FROM payroll_runs WHERE id=?", (rid,))
        if not run or run['status'] != 'draft':
            return _err(send_json, 'ينحذف المسيّر وهو مسودة فقط')
        conn.execute("DELETE FROM payroll_lines WHERE run_id=?", (rid,))
        conn.execute("DELETE FROM payroll_runs WHERE id=?", (rid,))
        conn.commit()
        return _ok(send_json)

    m = re.match(r'^/api/hr/payroll/(\d+)/(regenerate|approve|paid|reopen)$', path)
    if m and method == 'POST':
        rid, act = int(m.group(1)), m.group(2)
        run = _row(conn, "SELECT * FROM payroll_runs WHERE id=?", (rid,))
        if not run:
            return _err(send_json, 'غير موجود', 404)
        if act == 'regenerate':
            if run['status'] != 'draft':
                return _err(send_json, 'المسيّر معتمد — ما يُعاد توليده')
            conn.execute("DELETE FROM payroll_lines WHERE run_id=?", (rid,))
            _generate_lines(conn, rid, run['period'])
        elif act == 'approve':
            if run['status'] != 'draft':
                return _err(send_json, 'المسيّر معتمد من قبل')
            conn.execute("UPDATE payroll_runs SET status='approved', approved_by=?, approved_at=CURRENT_TIMESTAMP WHERE id=?", (uid, rid))
        elif act == 'reopen':
            if run['status'] != 'approved':
                return _err(send_json, 'يُعاد فتح المسيّر المعتمد (غير المصروف) فقط')
            conn.execute("UPDATE payroll_runs SET status='draft', approved_by=NULL, approved_at=NULL WHERE id=?", (rid,))
        elif act == 'paid':
            if run['status'] != 'approved':
                return _err(send_json, 'اعتمد المسيّر أولاً')
            for l in _rows(conn, "SELECT employee_id, advance_ded FROM payroll_lines WHERE run_id=? AND advance_ded>0", (rid,)):
                left = l['advance_ded']
                for a in _rows(conn, "SELECT * FROM advances WHERE employee_id=? AND status='active' AND start_period<=? ORDER BY id",
                               (l['employee_id'], run['period'])):
                    if left <= 0:
                        break
                    take = min(left, a['remaining'])
                    rem = round(a['remaining'] - take, 2)
                    conn.execute("UPDATE advances SET remaining=?, status=? WHERE id=?", (rem, 'settled' if rem <= 0.01 else 'active', a['id']))
                    left -= take
            conn.execute("UPDATE payroll_runs SET status='paid', paid_at=CURRENT_TIMESTAMP WHERE id=?", (rid,))
        ac.audit(conn, uid, 'PAYROLL_' + act.upper(), 'payroll', rid)
        conn.commit()
        return _ok(send_json)

    m = re.match(r'^/api/hr/payroll/lines/(\d+)$', path)
    if m and method == 'PUT':
        lid = int(m.group(1))
        line = _row(conn, "SELECT l.*, r.status AS run_status FROM payroll_lines l JOIN payroll_runs r ON r.id=l.run_id WHERE l.id=?", (lid,))
        if not line:
            return _err(send_json, 'غير موجود', 404)
        if line['run_status'] != 'draft':
            return _err(send_json, 'المسيّر معتمد — أعد فتحه للتعديل')
        for k in ('overtime', 'bonus', 'absence_ded', 'penalty_ded', 'advance_ded', 'other_ded', 'unpaid_leave_ded', 'gosi_employee'):
            if k in data:
                line[k] = _num(data[k])
        if 'notes' in data:
            line['notes'] = data['notes']
        _calc_line(line)
        conn.execute("""UPDATE payroll_lines SET overtime=?, bonus=?, absence_ded=?, penalty_ded=?, advance_ded=?, other_ded=?,
                          unpaid_leave_ded=?, gosi_employee=?, gross=?, total_ded=?, net=?, notes=? WHERE id=?""",
                     (line['overtime'], line['bonus'], line['absence_ded'], line['penalty_ded'], line['advance_ded'], line['other_ded'],
                      line['unpaid_leave_ded'], line['gosi_employee'], line['gross'], line['total_ded'], line['net'], line.get('notes'), lid))
        conn.commit()
        return _ok(send_json, {'success': True, 'line': line})

    # ---------- المهام ----------
    if path == '/api/hr/tasks' and method == 'GET':
        sql = """SELECT t.*, a.full_name AS assigned_name, b.full_name AS assigned_by_name FROM hr_tasks t
                 LEFT JOIN users a ON a.id=t.assigned_to LEFT JOIN users b ON b.id=t.assigned_by WHERE 1=1"""
        p = []
        st = (query.get('status') or [''])[0]
        if st == 'open':
            sql += " AND t.status IN ('todo','in_progress')"
        elif st:
            sql += " AND t.status=?"; p.append(st)
        who = (query.get('assignee') or [''])[0]
        if who:
            sql += " AND t.assigned_to=?"; p.append(who)
        sql += " ORDER BY CASE t.status WHEN 'done' THEN 2 WHEN 'cancelled' THEN 3 ELSE 0 END, COALESCE(t.due_date,'9999'), t.id DESC LIMIT 500"
        return _ok(send_json, _rows(conn, sql, p))
    if path == '/api/hr/tasks' and method == 'POST':
        if not (data.get('title') or '').strip():
            return _err(send_json, 'اكتب عنوان المهمة')
        if not data.get('assigned_to'):
            return _err(send_json, 'اختر الموظف')
        cur = conn.execute("""INSERT INTO hr_tasks (title, description, assigned_to, assigned_by, due_date, priority, related)
                              VALUES (?,?,?,?,?,?,?)""", (data['title'].strip(), data.get('description'), data['assigned_to'], uid,
                                                          data.get('due_date') or None, data.get('priority') or 'normal', data.get('related')))
        conn.commit()
        return _ok(send_json, {'success': True, 'id': cur.lastrowid})
    m = re.match(r'^/api/hr/tasks/(\d+)$', path)
    if m and method == 'PUT':
        tid = int(m.group(1))
        fields, p = [], []
        for k in ('title', 'description', 'assigned_to', 'due_date', 'priority', 'status', 'related', 'completion_note'):
            if k in data:
                fields.append(f"{k}=?"); p.append(data[k] if data[k] != '' else None)
        if data.get('status') == 'done':
            fields.append("completed_at=CURRENT_TIMESTAMP")
        if not fields:
            return _err(send_json, 'لا يوجد تعديل')
        fields.append("updated_at=CURRENT_TIMESTAMP")
        p.append(tid)
        conn.execute(f"UPDATE hr_tasks SET {', '.join(fields)} WHERE id=?", p)
        conn.commit()
        return _ok(send_json)
    if m and method == 'DELETE':
        conn.execute("DELETE FROM hr_tasks WHERE id=?", (int(m.group(1)),))
        conn.commit()
        return _ok(send_json)

    return _err(send_json, 'المسار غير موجود', 404)


EMP_FIELDS = ('full_name', 'user_id', 'nationality', 'is_saudi', 'gender', 'id_number', 'id_expiry', 'passport_no', 'passport_expiry',
              'phone', 'email', 'department', 'job_title', 'manager_id', 'hire_date', 'probation_end', 'contract_type', 'contract_end',
              'work_location', 'gosi_registered', 'gosi_category', 'leave_opening_balance', 'leave_opening_date', 'status',
              'termination_date', 'termination_reason', 'notes')

def _emp_save(conn, eid, data, uid, can_pay, send_json):
    fields = list(EMP_FIELDS) + (list(SALARY_FIELDS) if can_pay else [])
    vals = {}
    for k in fields:
        if k in data:
            v = data[k]
            if k in ('is_saudi', 'gosi_registered'):
                v = 1 if v in (1, True, '1', 'true', 'on') else 0
            elif k in ('basic_salary', 'housing_allowance', 'transport_allowance', 'other_allowances', 'leave_opening_balance'):
                v = _num(v)
            elif k in ('user_id', 'manager_id'):
                v = int(v) if str(v or '').isdigit() else None
            elif v == '':
                v = None
            vals[k] = v
    if eid is None:
        if not (vals.get('full_name') or '').strip():
            return _err(send_json, 'اكتب اسم الموظف')
        if not vals.get('hire_date'):
            return _err(send_json, 'حدد تاريخ المباشرة')
    if vals.get('user_id'):
        other = conn.execute("SELECT full_name FROM employees WHERE user_id=? AND id IS NOT ?", (vals['user_id'], eid)).fetchone()
        if other:
            return _err(send_json, f'الحساب مربوط بموظف آخر ({other[0]})')
    if vals.get('hire_date') and not vals.get('probation_end') and eid is None:
        h = _d(vals['hire_date'])
        if h:
            vals['probation_end'] = (h + datetime.timedelta(days=90)).isoformat()
    if eid is None:
        mx = conn.execute("SELECT MAX(CAST(SUBSTR(emp_no,5) AS INTEGER)) FROM employees WHERE emp_no LIKE 'EMP-%'").fetchone()[0] or 0
        vals['emp_no'] = f"EMP-{mx + 1:03d}"
        if not vals.get('leave_opening_date'):
            # موظف قديم: الرصيد يبدأ من اليوم (أدخل رصيده الحالي في «رصيد افتتاحي») — موظف جديد: من تاريخ المباشرة
            h = _d(vals.get('hire_date'))
            vals['leave_opening_date'] = _today().isoformat() if h and h < _today() - datetime.timedelta(days=30) else vals.get('hire_date')
        cols = ','.join(vals.keys())
        cur = conn.execute(f"INSERT INTO employees ({cols}) VALUES ({','.join('?' * len(vals))})", list(vals.values()))
        eid = cur.lastrowid
        ac.audit(conn, uid, 'CREATE', 'employee', eid, new={'name': vals.get('full_name')})
    else:
        old = _row(conn, "SELECT * FROM employees WHERE id=?", (eid,))
        if not old:
            return _err(send_json, 'غير موجود', 404)
        if not vals:
            return _err(send_json, 'لا يوجد تعديل')
        sets = ', '.join(f"{k}=?" for k in vals) + ", updated_at=CURRENT_TIMESTAMP"
        conn.execute(f"UPDATE employees SET {sets} WHERE id=?", list(vals.values()) + [eid])
        changed = {k: v for k, v in vals.items() if str(old.get(k)) != str(v)}
        ac.audit(conn, uid, 'UPDATE', 'employee', eid,
                 old={k: old.get(k) for k in changed}, new=changed)
    conn.commit()
    return _ok(send_json, {'success': True, 'id': eid})

def _create_leave(conn, emp, data, uid):
    lt = data.get('leave_type')
    if lt not in LEAVE_TYPES:
        return 'اختر نوع الإجازة'
    days = _leave_days(data.get('start_date'), data.get('end_date'))
    if not days:
        return 'تحقق من تاريخ البداية والنهاية'
    if data.get('days') not in (None, ''):
        days = _num(data['days'], days)
    ov = conn.execute("""SELECT 1 FROM leave_requests WHERE employee_id=? AND status IN ('pending','approved')
                         AND NOT (end_date < ? OR start_date > ?)""", (emp['id'], data['start_date'], data['end_date'])).fetchone()
    if ov:
        return 'فيه إجازة أخرى في نفس الفترة'
    cur = conn.execute("""INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, days, reason, requested_by)
                          VALUES (?,?,?,?,?,?,?)""", (emp['id'], lt, data['start_date'], data['end_date'], days, data.get('reason'), uid))
    return cur.lastrowid


# ============================================================
# المسيّر
# ============================================================
def _calc_line(l):
    l['gross'] = round(sum(_num(l.get(k)) for k in ('basic', 'housing', 'transport', 'other_allow', 'overtime', 'bonus')), 2)
    l['total_ded'] = round(sum(_num(l.get(k)) for k in ('unpaid_leave_ded', 'absence_ded', 'penalty_ded', 'advance_ded', 'other_ded', 'gosi_employee')), 2)
    l['net'] = round(l['gross'] - l['total_ded'], 2)
    return l

def _generate_lines(conn, run_id, period):
    s = ac.get_settings(conn)
    y, mth = map(int, period.split('-'))
    p_start = datetime.date(y, mth, 1)
    p_end = (datetime.date(y + (mth == 12), mth % 12 + 1, 1) - datetime.timedelta(days=1))
    cap = _num(s.get('gosi_cap'), 45000)
    emps = _rows(conn, """SELECT * FROM employees WHERE hire_date<=? AND (status<>'terminated' OR termination_date>=?)""",
                 (p_end.isoformat(), p_start.isoformat()))
    for e in emps:
        hire = _d(e['hire_date']) or p_start
        term = _d(e.get('termination_date')) if e.get('status') == 'terminated' else None
        a, b = max(hire, p_start), min(term or p_end, p_end)
        worked = 30 if (a == p_start and b == p_end) else max(min((b - a).days + 1, 30), 0)
        f = worked / 30
        l = {'basic': round(_num(e['basic_salary']) * f, 2), 'housing': round(_num(e['housing_allowance']) * f, 2),
             'transport': round(_num(e['transport_allowance']) * f, 2), 'other_allow': round(_num(e['other_allowances']) * f, 2),
             'overtime': 0, 'bonus': 0, 'absence_ded': 0, 'penalty_ded': 0, 'other_ded': 0}
        # إجازات بدون راتب داخل الشهر
        unpaid = 0
        for lr in _rows(conn, """SELECT start_date, end_date FROM leave_requests WHERE employee_id=? AND leave_type='unpaid'
                                 AND status='approved' AND NOT (end_date < ? OR start_date > ?)""",
                        (e['id'], p_start.isoformat(), p_end.isoformat())):
            unpaid += _overlap_days(_d(lr['start_date']), _d(lr['end_date']), p_start, p_end)
        unpaid = min(unpaid, worked)
        l['unpaid_leave_days'] = unpaid
        l['unpaid_leave_ded'] = round(monthly_wage(e) / 30 * unpaid, 2)
        # السلف
        adv = 0
        for ad in _rows(conn, "SELECT * FROM advances WHERE employee_id=? AND status='active' AND start_period<=?", (e['id'], period)):
            adv += min(ad['monthly_installment'], ad['remaining'])
        l['advance_ded'] = round(adv, 2)
        # التأمينات (على الأساسي + السكن، بحد أعلى)
        gbase = min(_num(e['basic_salary']) + _num(e['housing_allowance']), cap) * f
        if e.get('gosi_registered'):
            if e.get('is_saudi'):
                cat = 'new' if e.get('gosi_category') == 'new' else 'legacy'
                l['gosi_employee'] = round(gbase * _num(s.get(f'gosi_{cat}_employee')), 2)
                l['gosi_employer'] = round(gbase * _num(s.get(f'gosi_{cat}_employer')), 2)
            else:
                l['gosi_employee'] = 0
                l['gosi_employer'] = round(gbase * _num(s.get('gosi_nonsaudi_employer'), 0.02), 2)
        else:
            l['gosi_employee'] = l['gosi_employer'] = 0
        _calc_line(l)
        conn.execute("""INSERT INTO payroll_lines (run_id, employee_id, days_worked, basic, housing, transport, other_allow, overtime, bonus,
                          unpaid_leave_days, unpaid_leave_ded, absence_ded, penalty_ded, advance_ded, other_ded, gosi_employee, gosi_employer,
                          gross, total_ded, net) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (run_id, e['id'], worked, l['basic'], l['housing'], l['transport'], l['other_allow'], 0, 0, unpaid,
                      l['unpaid_leave_ded'], 0, 0, l['advance_ded'], 0, l['gosi_employee'], l['gosi_employer'],
                      l['gross'], l['total_ded'], l['net']))


# ============================================================
# التنبيهات
# ============================================================
def alerts(conn, perms):
    days = int(_num(ac.get_setting(conn, 'expiry_alert_days', 60), 60))
    lim = (_today() + datetime.timedelta(days=days)).isoformat()
    out = []
    if ac.can(perms, 'employees', 'view'):
        for e in _rows(conn, "SELECT * FROM employees WHERE status<>'terminated'"):
            for f, lbl in (('id_expiry', 'انتهاء الهوية/الإقامة'), ('passport_expiry', 'انتهاء الجواز'),
                           ('contract_end', 'انتهاء العقد'), ('probation_end', 'نهاية فترة التجربة')):
                v = e.get(f)
                if v and str(v)[:10] <= lim and (f != 'probation_end' or str(v)[:10] >= _today().isoformat()):
                    out.append({'kind': 'employee', 'id': e['id'], 'name': e['full_name'], 'what': lbl, 'date': str(v)[:10]})
    if ac.can(perms, 'assets', 'view'):
        for a in _rows(conn, "SELECT * FROM assets WHERE status NOT IN ('disposed','lost')"):
            for f, lbl in (('registration_expiry', 'انتهاء الاستمارة'), ('insurance_expiry', 'انتهاء التأمين'),
                           ('inspection_expiry', 'انتهاء الفحص الدوري'), ('authorization_expiry', 'انتهاء تفويض القيادة'),
                           ('next_service_date', 'موعد الصيانة'), ('warranty_expiry', 'انتهاء الضمان')):
                v = a.get(f)
                if v and str(v)[:10] <= lim:
                    out.append({'kind': 'asset', 'id': a['id'], 'name': f"{a['name']}{' — ' + a['plate_no'] if a.get('plate_no') else ''}",
                                'what': lbl, 'date': str(v)[:10]})
            if a.get('next_service_km') and a.get('odometer') and a['odometer'] >= a['next_service_km'] - 500:
                out.append({'kind': 'asset', 'id': a['id'], 'name': a['name'], 'what': f"صيانة عند {a['next_service_km']:,} كم (العداد {a['odometer']:,})", 'date': _today().isoformat()})
    out.sort(key=lambda x: x['date'])
    for o in out:
        o['days_left'] = (_d(o['date']) - _today()).days
    pending = conn.execute("SELECT COUNT(*) FROM leave_requests WHERE status='pending'").fetchone()[0] if ac.can(perms, 'leaves', 'edit') else 0
    return {'items': out, 'pending_leaves': pending, 'window': days}


# ============================================================
# الأصول
# ============================================================
ASSET_FIELDS = ('name', 'category', 'brand', 'model', 'serial_no', 'purchase_date', 'purchase_price', 'supplier', 'useful_life_years',
                'location', 'status', 'plate_no', 'vin', 'year', 'color', 'registration_expiry', 'insurance_expiry', 'inspection_expiry',
                'authorization_expiry', 'odometer', 'next_service_km', 'next_service_date', 'warranty_expiry', 'notes')

def book_value(a):
    price = _num(a.get('purchase_price'))
    life = _num(a.get('useful_life_years'))
    pd = _d(a.get('purchase_date'))
    if not price or not life or not pd:
        return None
    yrs = max((_today() - pd).days, 0) / 365.25
    return round(max(price - price * yrs / life, 0), 2)

def _assets(conn, method, path, query, data, ctx, send_json):
    uid = ctx['user']['id']
    if path == '/api/assets' and method == 'GET':
        cat = (query.get('category') or [''])[0]
        sql = """SELECT a.*, e.full_name AS custodian_name,
                        (SELECT COALESCE(SUM(cost),0) FROM asset_maintenance m WHERE m.asset_id=a.id) AS maintenance_cost
                 FROM assets a LEFT JOIN employees e ON e.id=a.custodian_id"""
        p = []
        if cat:
            sql += " WHERE a.category=?"; p.append(cat)
        sql += " ORDER BY CASE a.status WHEN 'disposed' THEN 2 WHEN 'lost' THEN 2 ELSE 0 END, a.category, a.asset_code"
        rows = _rows(conn, sql, p)
        for r in rows:
            r['book_value'] = book_value(r)
        return _ok(send_json, rows)

    if path == '/api/assets' and method == 'POST':
        cat = data.get('category')
        if cat not in ASSET_CATS:
            return _err(send_json, 'اختر التصنيف')
        if not (data.get('name') or '').strip():
            return _err(send_json, 'اكتب اسم الأصل')
        pre = ASSET_CATS[cat]
        mx = 0
        for (c,) in conn.execute("SELECT asset_code FROM assets WHERE asset_code LIKE ?", (pre + '-%',)).fetchall():
            try:
                mx = max(mx, int(c.split('-')[-1]))
            except Exception:
                pass
        vals = {k: (data[k] if data[k] != '' else None) for k in ASSET_FIELDS if k in data}
        vals['asset_code'] = f"{pre}-{mx + 1:03d}"
        vals['created_by'] = uid
        cols = ','.join(vals.keys())
        cur = conn.execute(f"INSERT INTO assets ({cols}) VALUES ({','.join('?' * len(vals))})", list(vals.values()))
        aid = cur.lastrowid
        if data.get('custodian_id'):
            _set_custody(conn, aid, data['custodian_id'], data.get('condition'), 'تسليم عند التسجيل', uid)
        ac.audit(conn, uid, 'CREATE', 'asset', aid, new={'code': vals['asset_code'], 'name': vals.get('name')})
        conn.commit()
        return _ok(send_json, {'success': True, 'id': aid, 'asset_code': vals['asset_code']})

    m = re.match(r'^/api/assets/(\d+)$', path)
    if m and method == 'GET':
        aid = int(m.group(1))
        a = _row(conn, "SELECT a.*, e.full_name AS custodian_name FROM assets a LEFT JOIN employees e ON e.id=a.custodian_id WHERE a.id=?", (aid,))
        if not a:
            return _err(send_json, 'غير موجود', 404)
        a['book_value'] = book_value(a)
        a['custody_log'] = _rows(conn, """SELECT c.*, e.full_name AS employee_name, u.full_name AS by_name FROM asset_custody_log c
                                          LEFT JOIN employees e ON e.id=c.employee_id LEFT JOIN users u ON u.id=c.created_by
                                          WHERE c.asset_id=? ORDER BY c.id DESC""", (aid,))
        a['maintenance'] = _rows(conn, """SELECT m.*, u.full_name AS by_name FROM asset_maintenance m LEFT JOIN users u ON u.id=m.created_by
                                          WHERE m.asset_id=? ORDER BY m.m_date DESC, m.id DESC""", (aid,))
        return _ok(send_json, a)
    if m and method == 'PUT':
        aid = int(m.group(1))
        vals = {k: (data[k] if data[k] != '' else None) for k in ASSET_FIELDS if k in data}
        if 'category' in vals and vals['category'] not in ASSET_CATS:
            return _err(send_json, 'تصنيف غير صحيح')
        if not vals:
            return _err(send_json, 'لا يوجد تعديل')
        conn.execute(f"UPDATE assets SET {', '.join(k + '=?' for k in vals)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", list(vals.values()) + [aid])
        ac.audit(conn, uid, 'UPDATE', 'asset', aid, new=vals)
        conn.commit()
        return _ok(send_json)
    if m and method == 'DELETE':
        aid = int(m.group(1))
        conn.execute("DELETE FROM asset_custody_log WHERE asset_id=?", (aid,))
        conn.execute("DELETE FROM asset_maintenance WHERE asset_id=?", (aid,))
        conn.execute("DELETE FROM assets WHERE id=?", (aid,))
        ac.audit(conn, uid, 'DELETE', 'asset', aid)
        conn.commit()
        return _ok(send_json)

    m = re.match(r'^/api/assets/(\d+)/custody$', path)
    if m and method == 'POST':
        aid = int(m.group(1))
        if not conn.execute("SELECT 1 FROM assets WHERE id=?", (aid,)).fetchone():
            return _err(send_json, 'غير موجود', 404)
        _set_custody(conn, aid, data.get('employee_id') or None, data.get('condition'), data.get('notes'), uid)
        conn.commit()
        return _ok(send_json)

    m = re.match(r'^/api/assets/(\d+)/maintenance$', path)
    if m and method == 'POST':
        aid = int(m.group(1))
        if not data.get('m_date'):
            return _err(send_json, 'حدد التاريخ')
        odo = int(_num(data.get('odometer'))) or None
        conn.execute("""INSERT INTO asset_maintenance (asset_id, m_date, m_type, description, cost, vendor, odometer, next_due_date, next_due_km, created_by)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""", (aid, data['m_date'], data.get('m_type') or 'service', data.get('description'),
                                                         _num(data.get('cost')), data.get('vendor'), odo, data.get('next_due_date') or None,
                                                         int(_num(data.get('next_due_km'))) or None, uid))
        upd, p = [], []
        if odo:
            upd.append("odometer=MAX(COALESCE(odometer,0), ?)"); p.append(odo)
        if data.get('next_due_date'):
            upd.append("next_service_date=?"); p.append(data['next_due_date'])
        if data.get('next_due_km'):
            upd.append("next_service_km=?"); p.append(int(_num(data['next_due_km'])))
        if upd:
            conn.execute(f"UPDATE assets SET {', '.join(upd)} WHERE id=?", p + [aid])
        conn.commit()
        return _ok(send_json)

    return _err(send_json, 'المسار غير موجود', 404)

def _set_custody(conn, aid, emp_id, condition, notes, uid):
    a = _row(conn, "SELECT custodian_id FROM assets WHERE id=?", (aid,))
    if a and a['custodian_id']:
        conn.execute("INSERT INTO asset_custody_log (asset_id, employee_id, action, condition, notes, created_by) VALUES (?,?,?,?,?,?)",
                     (aid, a['custodian_id'], 'return', condition, notes, uid))
    if emp_id:
        conn.execute("INSERT INTO asset_custody_log (asset_id, employee_id, action, condition, notes, created_by) VALUES (?,?,?,?,?,?)",
                     (aid, emp_id, 'assign', condition, notes, uid))
    conn.execute("UPDATE assets SET custodian_id=?, custody_since=? WHERE id=?",
                 (emp_id, _today().isoformat() if emp_id else None, aid))


# ============================================================
# الخدمة الذاتية /api/me/*
# ============================================================
def _self(conn, method, path, query, data, ctx, send_json):
    user = ctx['user']
    uid = user['id']
    emp = _row(conn, "SELECT * FROM employees WHERE user_id=?", (uid,))

    if path == '/api/me/hr' and method == 'GET':
        out = {'employee': None, 'tasks': _rows(conn, """SELECT t.*, b.full_name AS assigned_by_name FROM hr_tasks t
                                                        LEFT JOIN users b ON b.id=t.assigned_by WHERE t.assigned_to=?
                                                        ORDER BY CASE t.status WHEN 'done' THEN 2 WHEN 'cancelled' THEN 3 ELSE 0 END,
                                                        COALESCE(t.due_date,'9999') LIMIT 100""", (uid,)),
               'types': {k: {'label': v[0], 'max': v[1]} for k, v in LEAVE_TYPES.items()}}
        if emp:
            e = {k: emp.get(k) for k in ('id', 'emp_no', 'full_name', 'job_title', 'department', 'hire_date', 'id_expiry',
                                          'contract_end', 'probation_end', 'status')}
            out['employee'] = e
            out['annual'] = annual_balance(conn, emp)
            out['sick'] = sick_used(conn, emp['id'])
            out['leaves'] = _rows(conn, "SELECT * FROM leave_requests WHERE employee_id=? ORDER BY start_date DESC LIMIT 30", (emp['id'],))
            out['custody'] = _rows(conn, "SELECT asset_code, name, category, plate_no, custody_since FROM assets WHERE custodian_id=?", (emp['id'],))
            out['payslips'] = _rows(conn, """SELECT r.period, l.* FROM payroll_lines l JOIN payroll_runs r ON r.id=l.run_id
                                             WHERE l.employee_id=? AND r.status IN ('approved','paid') ORDER BY r.period DESC LIMIT 12""", (emp['id'],))
        return _ok(send_json, out)

    if path == '/api/me/leaves' and method == 'POST':
        if not emp:
            return _err(send_json, 'حسابك غير مربوط بملف موظف — راجع الموارد البشرية')
        res = _create_leave(conn, emp, data, uid)
        if isinstance(res, str):
            return _err(send_json, res)
        conn.commit()
        return _ok(send_json, {'success': True, 'id': res})

    m = re.match(r'^/api/me/leaves/(\d+)$', path)
    if m and method == 'DELETE':
        if not emp:
            return _err(send_json, 'غير مصرح', 403)
        n = conn.execute("UPDATE leave_requests SET status='cancelled' WHERE id=? AND employee_id=? AND status='pending'",
                         (int(m.group(1)), emp['id'])).rowcount
        conn.commit()
        return _ok(send_json) if n else _err(send_json, 'ما يمكن إلغاء الطلب')

    m = re.match(r'^/api/me/tasks/(\d+)$', path)
    if m and method == 'POST':
        st = data.get('status')
        if st not in ('todo', 'in_progress', 'done'):
            return _err(send_json, 'حالة غير صحيحة')
        n = conn.execute("""UPDATE hr_tasks SET status=?, completion_note=COALESCE(?, completion_note),
                              completed_at=CASE WHEN ?='done' THEN CURRENT_TIMESTAMP ELSE NULL END, updated_at=CURRENT_TIMESTAMP
                            WHERE id=? AND assigned_to=?""", (st, data.get('note') or None, st, int(m.group(1)), uid)).rowcount
        conn.commit()
        return _ok(send_json) if n else _err(send_json, 'المهمة غير موجودة', 404)

    return False
