#!/usr/bin/env python3
"""
نظام أبيلا للمناسبات - الخادم الرئيسي (الإصدار 2)
Abela Events Management System

تشغيل: python server.py
المتصفح: http://localhost:8080
"""

import http.server, socketserver, json, sqlite3, os, sys, urllib.parse
import hashlib, secrets, datetime, re, base64, mimetypes, uuid
from pathlib import Path

# ضمان طباعة الحروف العربية والرموز على ويندوز
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import comments_routes
except ImportError:
    comments_routes = None
try:
    import sync_sheets
except ImportError:
    sync_sheets = None
try:
    import sync_to_excel
except ImportError:
    sync_to_excel = None
try:
    import new_routes
except ImportError:
    new_routes = None
try:
    import permissions as perms_module
except ImportError:
    perms_module = None
try:
    import code_generator
except ImportError:
    code_generator = None
import access_control as ac
import crm_routes
import wpgen_routes
import ops_routes
import expenses_routes
import jard_native
import today_routes
import contracts_routes
import hr_routes

# ============================================================
# Excel auto-export hook (مزامنة ثنائية الاتجاه)
# ============================================================
import threading as _threading
_excel_export_lock = _threading.Lock()
_excel_export_pending = {'flag': False, 'timer': None}

def trigger_excel_export(what='all', delay=8.0):
    """
    يفعّل تصدير Excel بعد كل تعديل، مع debouncing لتفادي التصدير المتكرر.
    يجمع كل التعديلات خلال `delay` ثوانٍ ثم يصدّر مرة واحدة.
    """
    if not sync_to_excel:
        return
    def _run():
        with _excel_export_lock:
            _excel_export_pending['flag'] = False
            _excel_export_pending['timer'] = None
        try:
            sync_to_excel.export_quick(DB_PATH, 'events')
            sync_to_excel.export_quick(DB_PATH, 'inventory')
        except Exception as e:
            print(f"  ⚠ Excel auto-export: {e}")

    with _excel_export_lock:
        if _excel_export_pending['timer']:
            try: _excel_export_pending['timer'].cancel()
            except Exception: pass
        t = _threading.Timer(delay, _run)
        t.daemon = True
        _excel_export_pending['timer'] = t
        _excel_export_pending['flag'] = True
        t.start()

# ============================================================
# الإعدادات
# ============================================================
PORT = int(os.environ.get('PORT', '8080'))
HOST = '0.0.0.0'

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ['DATA_DIR']) if os.environ.get('DATA_DIR') else None
DB_PATH = (DATA_DIR / 'abela.db') if DATA_DIR else (BASE_DIR / 'backend' / 'db' / 'abela.db')
SCHEMA_PATH = BASE_DIR / 'backend' / 'db' / 'schema.sql'
DASHBOARD_DIR = BASE_DIR / 'dashboard'
MOBILE_DIR = BASE_DIR / 'mobile'
ASSETS_DIR = BASE_DIR / 'assets'
UPLOADS_DIR = (DATA_DIR / 'uploads') if DATA_DIR else (BASE_DIR / 'backend' / 'uploads')

SESSIONS = {}

# ============================================================
# قاعدة البيانات
# ============================================================
def _parse_create_table_columns(create_stmt):
    """يستخرج {col_name: col_definition} من CREATE TABLE statement"""
    s = create_stmt
    start = s.find('(')
    end = s.rfind(')')
    if start < 0 or end < 0:
        return {}
    body = s[start+1:end]

    # نزيل التعليقات السطرية -- ... قبل التحليل (تربك parser)
    cleaned_lines = []
    for line in body.split('\n'):
        # نقطع كل ما بعد -- في السطر
        idx = line.find('--')
        if idx >= 0:
            line = line[:idx]
        cleaned_lines.append(line)
    body = '\n'.join(cleaned_lines)

    # نقسم على الفواصل مع احترام الأقواس
    parts = []
    buf, depth = [], 0
    for ch in body:
        if ch == '(': depth += 1
        elif ch == ')': depth -= 1
        if ch == ',' and depth == 0:
            parts.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append(''.join(buf).strip())

    cols = {}
    for p in parts:
        if not p:
            continue
        # نتجاهل CONSTRAINTS
        upper = p.upper().lstrip()
        if upper.startswith(('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK', 'CONSTRAINT')):
            continue
        tokens = p.split()
        if not tokens:
            continue
        first = tokens[0].strip('`"[]')
        if first and first.upper() not in ('PRIMARY','FOREIGN','UNIQUE','CHECK','CONSTRAINT'):
            # تنظيف الـ definition: يكفي اسم العمود + النوع
            cols[first] = p
    return cols


def migrate_database(conn):
    """
    Migration آمن: يضيف الجداول والفهارس والأعمدة الناقصة من schema.sql
    بدون مسح أي بيانات موجودة.

    يتعامل مع ٣ حالات:
      ١. جدول جديد كلياً → CREATE TABLE IF NOT EXISTS
      ٢. فهرس جديد → CREATE INDEX IF NOT EXISTS
      ٣. عمود جديد على جدول موجود → ALTER TABLE ADD COLUMN
    """
    before_tables = {r['name'] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    before_indexes = {r['name'] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()}

    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = f.read()

    # نمشي statement-by-statement
    safe_statements = []
    create_table_stmts = {}  # {table_name: original_create_stmt}
    for stmt in schema.split(';'):
        # نزيل تعليقات السطور -- ... قبل أي شيء
        cleaned_lines = []
        for line in stmt.splitlines():
            i = line.find('--')
            cleaned_lines.append(line[:i] if i >= 0 else line)
        s = '\n'.join(cleaned_lines).strip()
        if not s:
            continue
        head = s.upper()
        if head.startswith('DROP '):
            continue
        if head.startswith('INSERT '):
            continue
        # CREATE TABLE (نستخدم search لأن قد يبدأ بـ whitespace)
        m = re.search(r'(?i)^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)', s)
        if m:
            table_name = m.group(1)
            create_table_stmts[table_name] = s
            if 'IF NOT EXISTS' not in head:
                s = re.sub(r'(?i)\bCREATE\s+TABLE\b(?!\s+IF\s+NOT\s+EXISTS)',
                          'CREATE TABLE IF NOT EXISTS', s, count=1)
        # CREATE INDEX
        elif head.startswith('CREATE INDEX') or head.startswith('CREATE UNIQUE INDEX'):
            if 'IF NOT EXISTS' not in head:
                s = re.sub(r'(?i)\bCREATE(\s+UNIQUE)?\s+INDEX\b(?!\s+IF\s+NOT\s+EXISTS)',
                          r'CREATE\1 INDEX IF NOT EXISTS', s, count=1)
        safe_statements.append(s)

    # تنفيذ — يضيف الجداول/الفهارس الناقصة
    for stmt in safe_statements:
        try:
            conn.execute(stmt)
        except sqlite3.Error as e:
            print(f"  ⚠ migration warning: {str(e)[:80]}")
    conn.commit()

    # الآن نتحقق من الأعمدة الناقصة في الجداول الموجودة
    added_columns = []
    for table_name, create_stmt in create_table_stmts.items():
        try:
            existing_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        except sqlite3.Error:
            continue
        if not existing_cols:
            continue
        schema_cols = _parse_create_table_columns(create_stmt)
        missing = [(c, defn) for c, defn in schema_cols.items() if c not in existing_cols]
        for col_name, col_def in missing:
            try:
                # SQLite ALTER TABLE ADD COLUMN: ما يدعم بعض constraints (مثل NOT NULL بدون DEFAULT)
                # نزيل NOT NULL لو ما في DEFAULT
                safe_def = col_def
                if 'NOT NULL' in safe_def.upper() and 'DEFAULT' not in safe_def.upper():
                    safe_def = re.sub(r'(?i)\s+NOT\s+NULL', '', safe_def)
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {safe_def}")
                added_columns.append(f"{table_name}.{col_name}")
            except sqlite3.Error as e:
                # ممكن العمود يكون موجود فعلاً أو constraint غير مدعوم — نتجاهل
                pass
    conn.commit()

    after_tables = {r['name'] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    after_indexes = {r['name'] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()}

    new_tables = sorted(after_tables - before_tables)
    new_indexes = sorted(after_indexes - before_indexes)
    if new_tables or new_indexes or added_columns:
        bits = []
        if new_tables: bits.append(f"+{len(new_tables)} جدول")
        if new_indexes: bits.append(f"+{len(new_indexes)} فهرس")
        if added_columns: bits.append(f"+{len(added_columns)} عمود")
        print(f"⚙ ترقية القاعدة: {' / '.join(bits)}")
        if new_tables:
            print(f"  جداول جديدة: {', '.join(new_tables)}")
        if added_columns:
            print(f"  أعمدة جديدة: {', '.join(added_columns)}")


def init_database():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # تهيئة إذا كان الملف جديدًا أو لا يحتوي على جداول (ملف فاضي بسبب كراش سابق)
    has_tables = conn.execute(
        "SELECT COUNT(*) c FROM sqlite_master WHERE type='table'"
    ).fetchone()['c'] > 0
    if not has_tables:
        # قاعدة جديدة كلياً → تنفيذ schema كامل + بيانات تجريبية
        print("📦 إنشاء قاعدة بيانات جديدة...")
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            conn.executescript(f.read())
        conn.commit()
        print("✓ قاعدة البيانات جاهزة")
        seed_demo_data(conn)
    else:
        # قاعدة موجودة → migration آمن للجداول الناقصة فقط
        migrate_database(conn)
    # الإصدار 4: الصلاحيات + المبيعات + خدمة العملاء
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    ac.init_tables(conn)
    crm_routes.init_tables(conn)
    hr_routes.init_tables(conn)
    try:
        import sync_generator
        sync_generator.init_tables(conn)
        wpgen_routes.init_tables(conn)
        ops_routes.init_tables(conn)
        expenses_routes.init_tables(conn)
        import ops_native
        ops_native.init_tables(conn)
        import exec_native
        exec_native.init_tables(conn)
        jard_native.init_tables(conn)
        for _col in ("extra_roles TEXT", "deleted INTEGER DEFAULT 0"):
            try:
                conn.execute("ALTER TABLE users ADD COLUMN " + _col)
            except Exception:
                pass
        _seed_team_20261120(conn)
        conn.commit()
    except Exception as e:
        print('⚠ gen tables', e)
    return conn

def _seed_team_20261120(conn):
    """طلب منصور 2026-11-20: حسابات أحمد أبو بكر وإسلام وريّان ورضوى + تفعيل رهف وروز وداريل ونوف وبدرالدين وعمران وفهيم.
    كلمة المرور عشوائية لا يعرفها أحد — منصور يضغط «كلمة مرور مؤقتة» لكل واحد من شاشة المستخدمين ويعطيه إياها."""
    import secrets
    if conn.execute("SELECT 1 FROM settings WHERE key='seed_team_20261120'").fetchone():
        return
    for un, name, role, title in (('ahmed', 'أحمد أبو بكر', 'inventory_manager', 'مدير المستودع — الجرد'),
                                  ('islam', 'إسلام', 'field', 'مدير تشغيل'),
                                  ('rayyan', 'ريّان', 'supervisor', 'مشرفة'),
                                  ('radwa', 'رضوى', 'supervisor', 'مشرفة')):
        if conn.execute("SELECT 1 FROM users WHERE lower(username)=? OR full_name=?", (un, name)).fetchone():
            continue
        if not conn.execute("SELECT 1 FROM roles WHERE key=?", (role,)).fetchone():
            continue
        conn.execute("""INSERT INTO users (username, password_hash, full_name, role, job_title, language, is_active, must_change_password)
                        VALUES (?,?,?,?,?,'ar',1,1)""", (un, ac.hash_password(secrets.token_urlsafe(24)), name, role, title))
    conn.execute("""UPDATE users SET is_active=1 WHERE username IN ('rahaf','rose','daryl','nouf','badruddin','omran','faheem')""")
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('seed_team_20261120', '1')")
    conn.commit()


def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def seed_demo_data(conn):
    """تحميل البيانات الفعلية لأبيلا من جداول Excel (العقود + العملاء)"""
    print("🌱 تحميل البيانات الفعلية لأبيلا...")

    # العملاء الفعليون من جدول العقود في Google Sheets
    customers = [
        ("مصاريف عامة",        "0000000000", None, "company",    "الرياض", "حساب المصاريف العامة - معارض"),
        ("خالد عبدالقادر",      "0500000001", None, "individual", "الرياض", None),
        ("الجوهره البابطين",    "0500000002", None, "vip",        "الرياض", "تفضل الديكور الذهبي الفاخر"),
        ("ريما الحمود",         "0500000003", None, "individual", "الرياض", None),
        ("هيا السبيعي",         "0500000004", None, "individual", "الرياض", None),
        ("لينا الحسن",          "0500000005", None, "individual", "الرياض", None),
        ("الجوهره الناصر",      "0500000006", None, "vip",        "الرياض", None),
        ("الجوهره العمران",     "0500000007", None, "vip",        "الرياض", None),
        ("فلوه اليعيش",         "0500000008", None, "individual", "الرياض", None),
        ("ساره الدهمش",         "0500000009", None, "vip",        "الرياض", "تحب الورد الأبيض والذهبي"),
        ("انجاد القويز",        "0500000010", None, "individual", "الرياض", None),
        ("ذكرى الحمود",         "0500000011", None, "individual", "الرياض", None),
        ("غاده الدريويش",       "0500000012", None, "individual", "الرياض", None),
        ("غاده الحصان",         "0500000013", None, "individual", "الرياض", None),
        ("ناصر المبيريك",       "0500000014", None, "individual", "الرياض", None),
        ("عبدالعزيز الزامل",    "0500000015", None, "individual", "الرياض", None),
    ]
    for c in customers:
        conn.execute("""INSERT INTO customers (full_name, phone, email, customer_type, city, notes)
                       VALUES (?, ?, ?, ?, ?, ?)""", c)

    # المناسبات الفعلية من جدول العقود (ID العميل = ترتيبه + 1)
    # event_code, operation_order, contract_code, customer_id, event_type, title, description,
    # event_date, event_start_time, event_end_time, venue_name, venue_address,
    # guests_count, theme, status, total_price, paid_amount,
    # insurance_amount, insurance_returned, discount, cost_total, profit, created_by
    events = [
        ("EVT-2026-0001", "O1001", "E1001", 1,  "exhibition", "معرض - مصاريف عامة",
         "حساب المصاريف العامة للمعارض", "2027-01-01", None, None, "أخرى", "الرياض",
         None, None, "planning", 0, 0, 0, 0, 0, 0, 0, 1),

        ("EVT-2026-0002", "O1002", "B1001", 2,  "newborn", "استقبال مولود — خالد عبدالقادر",
         "استقبال مولود في الحبيب التخصصي", "2026-05-14", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 30, None, "contracted",
         27933.50, 14829.00, 4170.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0003", "O1003", "W1001", 3,  "special", "مناسبة خاصة — الجوهره البابطين",
         "مناسبة خاصة في منزل العميلة", "2026-05-08", "20:00", "00:00",
         "منزل خاص", "الرياض", None, "ذهبي", "in_progress",
         0, 16790.00, 0, 0, 0, 0, 0, 11),

        ("EVT-2026-0004", "O1004", "W1002", 4,  "special", "مناسبة خاصة — ريما الحمود",
         "مناسبة خاصة في الشاليه", "2026-05-14", None, None,
         "شاليه", "الرياض", None, None, "in_progress",
         0, 20298.00, 0, 0, 0, 0, 0, 11),

        ("EVT-2026-0005", "O1005", "B1002", 5,  "newborn", "استقبال مولود — هيا السبيعي",
         "استقبال مولود في الحبيب التخصصي", "2026-05-15", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 30, None, "contracted",
         30475.00, 0, 5300.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0006", "O1006", "B1003", 6,  "newborn", "استقبال مولود — لينا الحسن",
         "استقبال مولود في الحبيب التخصصي", "2026-06-12", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 30, None, "contracted",
         32775.00, 16388.00, 5700.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0007", "O1007", "B1004", 7,  "newborn", "استقبال مولود — الجوهره الناصر",
         "استقبال مولود فاخر", "2026-06-05", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 40, None, "contracted",
         44275.00, 22200.00, 7700.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0008", "O1008", "B1005", 8,  "newborn", "استقبال مولود — الجوهره العمران",
         "استقبال مولود فاخر", "2026-06-20", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 35, None, "contracted",
         37260.00, 18630.00, 6480.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0009", "O1009", "B1006", 9,  "newborn", "استقبال مولود — فلوه اليعيش",
         "استقبال مولود في الحبيب الريان", "2026-05-09", "17:00", "20:00",
         "الحبيب الريان", "الرياض", 30, None, "ready",
         35535.00, 17768.00, 6180.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0010", "O1010", "B1007", 10, "newborn", "استقبال مولود — ساره الدهمش (مكتمل)",
         "استقبال مولود مع ورد طبيعي وثيم خاص", "2026-05-07", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 40, "أبيض وذهبي", "completed",
         62445.00, 62445.00, 10860.00, 10860.00, 0, 8540.78, 53904.22, 11),

        ("EVT-2026-0011", "O1011", "B1008", 11, "newborn", "استقبال مولود — انجاد القويز",
         "", "2026-06-20", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 30, None, "contracted",
         33120.00, 16560.00, 5760.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0012", "O1012", "B1009", 12, "newborn", "استقبال مولود — ذكرى الحمود",
         "", "2026-06-20", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 30, None, "contracted",
         33925.00, 5000.00, 5900.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0013", "O1013", "B1010", 13, "newborn", "استقبال مولود — غاده الدريويش",
         "", "2026-06-16", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 30, None, "contracted",
         40710.00, 20355.00, 7080.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0014", "O1014", "B1011", 14, "newborn", "استقبال مولود — غاده الحصان",
         "", "2026-06-10", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 30, None, "contracted",
         40940.00, 0, 7120.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0015", "O1015", "W1003", 15, "special", "مناسبة خاصة — ناصر المبيريك",
         "مناسبة خاصة في منزل العميل", "2026-05-09", "20:00", "00:00",
         "منزل خاص", "الرياض", None, None, "ready",
         40250.00, 0, 7000.00, 0, 0, 0, 0, 11),

        ("EVT-2026-0016", "O1016", "B1012", 16, "newborn", "استقبال مولود — عبدالعزيز الزامل",
         "", "2026-07-16", "17:00", "20:00",
         "الحبيب التخصصي", "الرياض", 30, None, "contracted",
         35305.00, 0, 6140.00, 0, 0, 0, 0, 11),
    ]
    for e in events:
        conn.execute("""INSERT INTO events
                       (event_code, operation_order, contract_code, customer_id, event_type, title, description,
                        event_date, event_start_time, event_end_time, venue_name, venue_address,
                        guests_count, theme, status, total_price, paid_amount,
                        insurance_amount, insurance_returned, discount, cost_total, profit, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", e)

    # المصاريف الفعلية لمناسبة ساره الدهمش (O1010) من جدول مصاريف الإشراف
    # event_id=10 (الساره الدهمش)
    payments_for_sara = [
        # المبلغ الكلي: 62,445 ر.س - تم الدفع بالكامل
        (10, 62445.00, 'bank_transfer', 'final', 'TXN-B1007-001', 12, 'دفع كامل قبل المناسبة'),
    ]
    for p in payments_for_sara:
        conn.execute("""INSERT INTO event_payments (event_id, amount, payment_method, payment_type, reference, received_by, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""", p)

    # تكليف الفرق على المناسبات القريبة
    assignments = [
        # مناسبة ساره (مكتملة)
        (10, 2, 'مشرفة رئيسية', '15:00'),    # ميهاف
        (10, 4, 'مشرف تنفيذ',   '14:00'),    # معاذ
        (10, 6, 'أمين مستودع',  '12:00'),    # فهيم
        (10, 7, 'عاملة اكسسوارات', '13:00'), # داريل
        (10, 10, 'الضيافة',     '16:30'),    # رغد
        # مناسبة فلوه (جاهزة - 2026-05-09)
        (9,  3, 'مشرفة رئيسية', '15:00'),    # شريفة
        (9,  5, 'مشرف تنفيذ',   '14:00'),    # فارس
        (9,  6, 'أمين مستودع',  '12:00'),    # فهيم
        # مناسبة ناصر (جاهزة - 2026-05-09)
        (15, 2, 'مشرفة رئيسية', '18:00'),    # ميهاف
        (15, 4, 'مشرف تنفيذ',   '17:00'),    # معاذ
    ]
    for a in assignments:
        conn.execute("""INSERT INTO event_assignments (event_id, user_id, role, arrival_time)
                       VALUES (?, ?, ?, ?)""", a)

    # مهام تنفيذية للمناسبات القريبة
    tasks = [
        (9, 'تجهيز خلفية الورود', 'تركيب خلفية الورود الطبيعية', 5, 'high', 'pending'),
        (9, 'ترتيب طاولات الضيافة', 'ترتيب الطاولات والكاسات', 5, 'normal', 'pending'),
        (9, 'تركيب الإضاءة', 'إضاءة LED ملونة', 5, 'high', 'pending'),
        (15, 'تجهيز المدخل الذهبي', 'تركيب مدخل المناسبة', 4, 'high', 'pending'),
        (15, 'ترتيب الكراسي', 'كراسي شيافاري ذهبية', 4, 'normal', 'pending'),
    ]
    for t in tasks:
        conn.execute("""INSERT INTO event_tasks (event_id, title, description, assigned_to, priority, status)
                       VALUES (?, ?, ?, ?, ?, ?)""", t)

    conn.commit()
    print(f"✓ تم تحميل {len(customers)} عميل، {len(events)} مناسبة، و {len(assignments)} تكليف")

# ============================================================
# المساعدات
# ============================================================
def hash_password(password):
    return ac.hash_password(password)

def verify_password(password, stored):
    return ac.verify_password(password, stored)

def gen_code(conn, prefix, table, field):
    year = datetime.date.today().year
    cur = conn.execute(f"SELECT COUNT(*) c FROM {table} WHERE {field} LIKE ?", (f"{prefix}-{year}-%",))
    return f"{prefix}-{year}-{cur.fetchone()['c']+1:04d}"


# ============================================================
# توليد كود العقد E/B/W حسب نوع المناسبة (مطابق لـ Google Sheets)
# ============================================================
def gen_contract_code(conn, event_type):
    """
    يولّد كود العقد بصيغة Excel:
    - exhibition (معرض)               → E1001, E1002...
    - newborn (استقبال مولود)         → B1001, B1002...
    - special (زواج/خطوبة/مناسبة خاصة) → W1001, W1002...
    """
    prefix_map = {
        'exhibition': 'E',
        'newborn': 'B',
        'special': 'W',
    }
    prefix = prefix_map.get(event_type, 'W')
    # ابحث عن أعلى رقم موجود بهذه البادئة
    rows = conn.execute(
        "SELECT contract_code FROM events WHERE contract_code LIKE ?",
        (f"{prefix}%",)
    ).fetchall()
    max_num = 1000
    for r in rows:
        try:
            n = int(str(r['contract_code'])[1:])  # كل ما بعد الحرف الأول
            if n > max_num:
                max_num = n
        except (ValueError, TypeError):
            pass
    return f"{prefix}{max_num + 1}"

def row_to_dict(row):
    return {k: row[k] for k in row.keys()}

def rows_to_list(rows):
    return [row_to_dict(r) for r in rows]

def parse_multipart(handler):
    """تحليل multipart/form-data لاستقبال الصور"""
    ctype = handler.headers.get('Content-Type', '')
    if 'multipart/form-data' not in ctype:
        return None, None
    boundary = ctype.split('boundary=')[-1].encode()
    length = int(handler.headers.get('Content-Length', 0))
    body = handler.rfile.read(length)
    parts = body.split(b'--' + boundary)
    fields, files = {}, {}
    for part in parts:
        if not part or part == b'--\r\n' or part == b'--':
            continue
        if b'\r\n\r\n' not in part:
            continue
        headers_raw, content = part.split(b'\r\n\r\n', 1)
        content = content.rstrip(b'\r\n--')
        headers_str = headers_raw.decode('utf-8', errors='ignore')
        name_m = re.search(r'name="([^"]+)"', headers_str)
        if not name_m: continue
        name = name_m.group(1)
        filename_m = re.search(r'filename="([^"]+)"', headers_str)
        if filename_m and filename_m.group(1):
            filename = filename_m.group(1)
            files[name] = {'filename': filename, 'content': content}
        else:
            fields[name] = content.decode('utf-8', errors='ignore')
    return fields, files

def save_uploaded_file(file_dict, subfolder=''):
    """حفظ ملف مرفوع وإرجاع المسار النسبي"""
    if not file_dict or 'content' not in file_dict:
        return None
    folder = UPLOADS_DIR / subfolder if subfolder else UPLOADS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    ext = Path(file_dict['filename']).suffix
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    file_path = folder / safe_name
    with open(file_path, 'wb') as f:
        f.write(file_dict['content'])
    rel = f"{subfolder}/{safe_name}" if subfolder else safe_name
    return f"/uploads/{rel}"

def save_data_url_image(data_url, subfolder=''):
    """حفظ صورة base64 من الكاميرا"""
    if not data_url or not data_url.startswith('data:image'):
        return None
    try:
        header, encoded = data_url.split(',', 1)
        ext = '.jpg'
        if 'png' in header: ext = '.png'
        elif 'webp' in header: ext = '.webp'
        folder = UPLOADS_DIR / subfolder if subfolder else UPLOADS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
        file_path = folder / safe_name
        with open(file_path, 'wb') as f:
            f.write(base64.b64decode(encoded))
        rel = f"{subfolder}/{safe_name}" if subfolder else safe_name
        return f"/uploads/{rel}"
    except Exception as e:
        print(f"خطأ في حفظ الصورة: {e}")
        return None

# ============================================================
# معالج HTTP
# ============================================================

def _exp_stats(conn):
    """إحصاءات المصروفات من فواتير المصروفات الأربعة (المصدر الحقيقي) لا من جدول expenses القديم"""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='exp_invoices'").fetchone():
        return {'total_expenses': 0, 'monthly_expenses': [], 'expenses_by_category': [], 'expenses_by_vendor': [], 'expenses_by_user': []}
    W = "COALESCE(is_test,0)=0 AND COALESCE(status,'active') NOT IN ('deleted','cancelled','محذوف','ملغي')"
    lab = {'sup': 'الإشراف', 'hos': 'الضيافة', 'exe': 'التنفيذ', 'pur': 'المشتريات'}
    def q(sql):
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    cats = q(f"SELECT k cat, SUM(total) total, COUNT(*) n FROM exp_invoices WHERE {W} GROUP BY k ORDER BY total DESC")
    for c in cats:
        c['cat'] = lab.get(c['cat'], c['cat'])
    return {
        'total_expenses': conn.execute(f"SELECT COALESCE(SUM(total),0) FROM exp_invoices WHERE {W}").fetchone()[0],
        'total_expenses_net': conn.execute(f"SELECT COALESCE(SUM(net),0) FROM exp_invoices WHERE {W}").fetchone()[0],
        'expenses_unpaid': conn.execute(f"SELECT COALESCE(SUM(remaining),0) FROM exp_invoices WHERE {W} AND remaining>0").fetchone()[0],
        'monthly_expenses': q(f"""SELECT substr(invoice_date,1,7) month, SUM(total) total FROM exp_invoices
                                 WHERE {W} AND invoice_date LIKE '20%' GROUP BY month ORDER BY month DESC LIMIT 6"""),
        'expenses_by_category': cats,
        'expenses_by_vendor': q(f"""SELECT COALESCE(NULLIF(sup_key,''), supplier, item) vendor, SUM(total) total, COUNT(*) n FROM exp_invoices
                                   WHERE {W} GROUP BY vendor HAVING vendor IS NOT NULL AND vendor<>'' ORDER BY total DESC LIMIT 10"""),
        'expenses_by_user': q(f"""SELECT COALESCE(NULLIF(person,''), entered_by) user_name, '' role, SUM(total) total, COUNT(*) n FROM exp_invoices
                                 WHERE {W} GROUP BY user_name HAVING user_name IS NOT NULL AND user_name<>'' ORDER BY total DESC LIMIT 12"""),
    }


class AbelaHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        sys.stdout.write(f"[{ts}] {format % args}\n")

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(body)

    def send_static_file(self, file_path):
        ext_map = {
            '.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8',
            '.js':'application/javascript; charset=utf-8','.json':'application/json; charset=utf-8',
            '.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp',
            '.svg':'image/svg+xml','.ico':'image/x-icon','.woff2':'font/woff2','.woff':'font/woff',
        }
        ext = Path(file_path).suffix.lower()
        fname = str(file_path).lower()
        try:
            with open(file_path, 'rb') as f: body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ext_map.get(ext, 'application/octet-stream'))
            self.send_header('Content-Length', str(len(body)))
            # sw.js لا يُكاش أبداً (المتصفح لازم يفحصه كل مرة عشان يكتشف التحديثات)
            # HTML أيضاً no-store عشان التغييرات تظهر فوراً
            if fname.endswith('.woff2') or fname.endswith('.woff'):
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
            elif fname.endswith('sw.js') or fname.endswith('.html'):
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
            else:
                self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def get_body_json(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0: return {}
        try: return json.loads(self.rfile.read(length).decode('utf-8'))
        except: return {}

    def get_user_id(self):
        if hasattr(self, '_uid_cache'):
            return self._uid_cache
        token = self.headers.get('Authorization', '').replace('Bearer ', '').strip()
        uid = None
        if token:
            c = get_db()
            try:
                uid = ac.user_id_from_token(c, token)
            finally:
                c.close()
        self._uid_cache = uid
        return uid

    def guard(self, conn, method, path, query=None, data=None):
        """تحقق الدخول والصلاحية + أقسام الإصدار 4. يرجع True لو الطلب انتهى (رُفض أو عولج)."""
        ok, status, msg, ctx = ac.check(conn, method, path, self.get_user_id())
        self._ctx = ctx
        if not ok:
            self.send_json({'error': msg, 'code': status}, status)
            return True
        if data is None and method in ('POST', 'PUT'):
            data = {}
        handled = crm_routes.handle(self, conn, method, path, query or {}, data or {}, ctx, self.send_json)
        if not handled and ctx:
            handled = contracts_routes.handle(self, conn, method, path, query or {}, data or {}, ctx, self.send_json)
        if not handled and ctx:
            handled = wpgen_routes.handle(self, conn, method, path, query or {}, data or {}, ctx, self.send_json)
        if not handled and ctx and path.startswith('/api/ops/'):
            handled = ops_routes.handle(self, conn, method, path, query or {}, data or {}, ctx, self.send_json)
        if not handled and ctx:
            handled = today_routes.handle(self, conn, method, path, query or {}, data or {}, ctx, self.send_json)
        if not handled and ctx:
            handled = jard_native.handle(self, conn, method, path, query or {}, data or {}, ctx, self.send_json)
        if not handled and ctx:
            handled = expenses_routes.handle(self, conn, method, path, query or {}, data or {}, ctx, self.send_json)
        if not handled and ctx:
            handled = hr_routes.handle(self, conn, method, path, query or {}, data or {}, ctx, self.send_json)
        return bool(handled)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if path in ('/', '/dashboard', '/dashboard/'):
            return self.send_static_file(DASHBOARD_DIR / 'index.html')
        if path in ('/mobile', '/mobile/'):
            return self.send_static_file(MOBILE_DIR / 'index.html')
        if path in ('/owner', '/owner/'):
            return self.send_static_file(MOBILE_DIR / 'owner.html')
        if path.startswith('/dashboard/'):
            return self.send_static_file(DASHBOARD_DIR / path.replace('/dashboard/', '', 1))
        if path.startswith('/mobile/'):
            return self.send_static_file(MOBILE_DIR / path.replace('/mobile/', '', 1))
        if path.startswith('/assets/'):
            return self.send_static_file(ASSETS_DIR / path.replace('/assets/', '', 1))
        if path.startswith('/uploads/'):
            return self.send_static_file(UPLOADS_DIR / path.replace('/uploads/', '', 1))
        if path in ('/operations', '/operations/'):
            return self.send_static_file(DASHBOARD_DIR / 'operations.html')
        if path in ('/checklist', '/checklist/'):
            return self.send_static_file(DASHBOARD_DIR / 'checklist.html')
        if path in ('/today', '/today/'):
            return self.send_static_file(DASHBOARD_DIR / 'today.html')
        if path in ('/jard', '/jard/'):
            return self.send_static_file(DASHBOARD_DIR / 'jard.html')
        if path in ('/execution', '/execution/'):
            return self.send_static_file(DASHBOARD_DIR / 'execution.html')
        if path in ('/expenses', '/expenses/'):
            return self.send_static_file(DASHBOARD_DIR / 'expenses.html')
        if path in ('/workplans', '/workplans/'):
            return self.send_static_file(DASHBOARD_DIR / 'workplans.html')
        if path.startswith('/wpimg/'):
            c = get_db()
            try:
                r = c.execute("SELECT path FROM wpg_uploads WHERE id=?", (path.split('/')[2],)).fetchone()
            finally:
                c.close()
            if r:
                return self.send_static_file(UPLOADS_DIR / r[0])
            self.send_response(404); self.end_headers(); return
        if path.startswith('/wpdoc/'):
            c = get_db()
            try:
                return wpgen_routes.serve_doc(self, c, path.split('/')[2], (query.get('k') or [''])[0])
            finally:
                c.close()
        if path == '/api/bridge/verify':
            ok = wpgen_routes.verify_nonce((query.get('n') or [''])[0])
            return self.send_json({'ok': ok}, 200 if ok else 403)
        if path.startswith('/api/'):
            return self.handle_api_get(path, query)
        self.send_response(404); self.end_headers()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/api/'):
            return self.handle_api_post(path)
        self.send_response(404); self.end_headers()

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/api/'):
            return self.handle_api_put(path)
        self.send_response(404); self.end_headers()

    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/api/'):
            return self.handle_api_delete(path)
        self.send_response(404); self.end_headers()

    # ============================================================
    # API GET
    # ============================================================
    def handle_api_get(self, path, query):
        conn = get_db()
        try:
            if self.guard(conn, 'GET', path, query):
                return
            # نقاط API الإضافية (تعليقات، موافقات، داش بورد المالكة)
            if comments_routes:
                handled = comments_routes.get_routes(self, conn, path, query,
                    self.get_body_json, self.get_user_id, self.send_json,
                    rows_to_list, row_to_dict)
                if handled: return

            # نقاط API الجديدة (الترجمات، صلاحيات، مواعيد، تقويم، خطط فرعية، إلخ)
            if new_routes:
                handled = new_routes.get_routes(self, conn, path, query,
                    self.get_user_id, self.send_json,
                    rows_to_list, row_to_dict, str(BASE_DIR))
                if handled: return

            # ===== حالة المزامنة =====
            if path == '/api/sync/status' and sync_sheets:
                last = sync_sheets.get_last_sync_status(DB_PATH)
                history = sync_sheets.get_sync_history(DB_PATH, 10)
                return self.send_json({'last': last, 'history': history})

            # ===== المستخدم الحالي (للتحقق من الجلسة وتحديث الواجهة) =====
            if path == '/api/me':
                uid = self.get_user_id()
                if not uid:
                    return self.send_json({'error': 'غير مصرح'}, 401)
                user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
                if not user:
                    return self.send_json({'error': 'المستخدم غير موجود'}, 404)
                user_keys = user.keys()
                lang = user['language'] if 'language' in user_keys and user['language'] else 'ar'
                can_exp = 1 if ('can_record_expenses' in user_keys and user['can_record_expenses']) else 0
                if user['role'] in ('admin','owner','general_manager','finance','project_manager','supervisor'):
                    can_exp = 1
                return self.send_json({'user': {
                    'id': user['id'], 'username': user['username'],
                    'full_name': user['full_name'], 'role': user['role'],
                    'language': lang, 'can_record_expenses': can_exp}})

            # ===== لوحة المعلومات =====
            if path == '/api/dashboard/stats':
                stats = {
                    'total_events': conn.execute("SELECT COUNT(*) c FROM events").fetchone()['c'],
                    'active_events': conn.execute("SELECT COUNT(*) c FROM events WHERE status IN ('contracted','planning','ready','in_progress')").fetchone()['c'],
                    'completed_events': conn.execute("SELECT COUNT(*) c FROM events WHERE status='completed'").fetchone()['c'],
                    'total_customers': conn.execute("SELECT COUNT(*) c FROM customers").fetchone()['c'],
                    'total_inventory': conn.execute("SELECT COUNT(*) c FROM inventory_items").fetchone()['c'],
                    'inventory_in_use': conn.execute("SELECT COUNT(*) c FROM inventory_items WHERE status IN ('reserved','in_event')").fetchone()['c'],
                    'inventory_value': conn.execute("SELECT COALESCE(SUM(unit_cost*quantity_total),0) v FROM inventory_items").fetchone()['v'],
                    'total_revenue': conn.execute("SELECT COALESCE(SUM(total_price),0) v FROM events WHERE status NOT IN ('lead','quoted','cancelled')").fetchone()['v'],
                    'total_collected': conn.execute("SELECT COALESCE(SUM(paid_amount),0) v FROM events").fetchone()['v'],
                    'pending_payments': conn.execute("SELECT COALESCE(SUM(total_price-paid_amount),0) v FROM events WHERE status NOT IN ('lead','quoted','cancelled')").fetchone()['v'],
                    'damaged_items': conn.execute("SELECT COUNT(*) c FROM inventory_items WHERE condition IN ('damaged','lost')").fetchone()['c'],
                    'total_workplans': conn.execute("SELECT COUNT(*) c FROM work_plans").fetchone()['c'],
                    'pending_checklists': conn.execute("SELECT COUNT(*) c FROM warehouse_checklists WHERE status IN ('pending','in_progress')").fetchone()['c'],
                    # === مالية مفصّلة ===
                    **_exp_stats(conn),
                    'monthly_revenue': rows_to_list(conn.execute("""
                        SELECT strftime('%Y-%m', COALESCE(actual_date, event_date)) as month,
                               SUM(total_price) as revenue,
                               SUM(paid_amount) as collected
                        FROM events
                        WHERE status NOT IN ('cancelled','lead')
                        GROUP BY month ORDER BY month DESC LIMIT 6
                    """).fetchall()),
                }
                upcoming = conn.execute("""SELECT e.*, c.full_name as customer_name FROM events e
                                          JOIN customers c ON e.customer_id=c.id
                                          WHERE e.event_date >= date('now') AND e.status NOT IN ('cancelled','closed')
                                          ORDER BY e.event_date LIMIT 5""").fetchall()
                stats['upcoming_events'] = rows_to_list(upcoming)
                _c = getattr(self, '_ctx', None)
                if _c and not (_c['perms'].get('is_super') or _c['user'].get('role') in ('owner', 'general_manager', 'admin')):
                    for _k in list(stats.keys()):
                        if any(w in _k for w in ('revenue','collected','pending_payments','expenses','profit','inventory_value','cost')):
                            stats[_k] = None
                    stats['money_hidden'] = True
                return self.send_json(stats)

            # ===== المناسبات =====
            # ===== المصاريف حسب القسم (للوحة المالية) =====
            if path == '/api/expenses/by-department':
                result = {}
                # المصاريف من Google Sheets (sheet_expenses)
                dept_map = {
                    'execution': 'مصاريف التنفيذ',
                    'supervision': 'مصاريف الإشراف',
                    'hospitality': 'مصاريف الضيافة',
                }
                for key, label in dept_map.items():
                    row = conn.execute("""
                        SELECT
                            COUNT(*) as cnt,
                            COALESCE(SUM(net_cost), 0) as total,
                            COALESCE(SUM(paid), 0) as paid,
                            COALESCE(SUM(remaining), 0) as remaining
                        FROM sheet_expenses WHERE expense_type=?
                    """, (key,)).fetchone()
                    result[key] = {
                        'label': label,
                        'count': row['cnt'] or 0,
                        'total': row['total'] or 0,
                        'paid': row['paid'] or 0,
                        'remaining': row['remaining'] or 0,
                    }
                # المشتريات من sheet_purchases
                row = conn.execute("""
                    SELECT
                        COUNT(*) as cnt,
                        COALESCE(SUM(net_cost), 0) as total,
                        COALESCE(SUM(paid), 0) as paid,
                        COALESCE(SUM(remaining), 0) as remaining
                    FROM sheet_purchases
                """).fetchone()
                result['purchases'] = {
                    'label': 'المشتريات',
                    'count': row['cnt'] or 0,
                    'total': row['total'] or 0,
                    'paid': row['paid'] or 0,
                    'remaining': row['remaining'] or 0,
                }
                return self.send_json(result)

            if path == '/api/events':
                rows = conn.execute("""SELECT e.*,
                                              c.full_name as customer_name,
                                              c.full_name_en as customer_name_en,
                                              c.full_name_ur as customer_name_ur,
                                              c.phone as customer_phone,
                                              c.id_number as customer_id_number,
                                              c.emergency_phone as customer_emergency_phone
                                       FROM events e JOIN customers c ON e.customer_id=c.id
                                       ORDER BY e.event_date DESC""").fetchall()
                return self.send_json(rows_to_list(rows))

            m = re.match(r'^/api/events/(\d+)$', path)
            if m:
                eid = int(m.group(1))
                event = conn.execute("""SELECT e.*, c.full_name as customer_name, c.phone as customer_phone, c.email as customer_email
                                       FROM events e JOIN customers c ON e.customer_id=c.id WHERE e.id=?""", (eid,)).fetchone()
                if not event: return self.send_json({'error': 'غير موجود'}, 404)
                d = row_to_dict(event)
                d['assignments'] = rows_to_list(conn.execute(
                    """SELECT ea.*, u.full_name as user_name FROM event_assignments ea
                       JOIN users u ON ea.user_id=u.id WHERE ea.event_id=?""", (eid,)).fetchall())
                d['inventory'] = rows_to_list(conn.execute(
                    """SELECT ei.*, i.name as item_name, i.item_code, i.warehouse FROM event_inventory ei
                       JOIN inventory_items i ON ei.item_id=i.id WHERE ei.event_id=?""", (eid,)).fetchall())
                d['tasks'] = rows_to_list(conn.execute(
                    """SELECT t.*, u.full_name as assignee_name FROM event_tasks t
                       LEFT JOIN users u ON t.assigned_to=u.id WHERE t.event_id=? ORDER BY t.id""", (eid,)).fetchall())
                d['payments'] = rows_to_list(conn.execute(
                    "SELECT * FROM event_payments WHERE event_id=? ORDER BY payment_date DESC", (eid,)).fetchall())
                d['photos'] = rows_to_list(conn.execute(
                    "SELECT * FROM event_photos WHERE event_id=? ORDER BY uploaded_at DESC", (eid,)).fetchall())
                d['workplans'] = rows_to_list(conn.execute(
                    """SELECT wp.*, u.full_name as planner_name FROM work_plans wp
                       LEFT JOIN users u ON wp.designer_id=u.id WHERE wp.event_id=? ORDER BY wp.id DESC""", (eid,)).fetchall())
                # خطط مولّد الخطط + إدارة العمليات المرتبطة بالمناسبة
                try:
                    d['wpg_plan'] = rows_to_list(conn.execute(
                        "SELECT * FROM wpg_plans WHERE contract_code=? OR (operation_order<>'' AND operation_order=?)",
                        (d.get('contract_code') or '-', d.get('operation_order') or '-')).fetchall())
                    d['ops_tasks'] = rows_to_list(conn.execute(
                        """SELECT t.dept, t.title, t.status, t.assignee FROM ops_tasks t JOIN ops_orders o ON o.quote_code=t.quote_code
                           WHERE o.contract_code=? ORDER BY t.dept""", (d.get('contract_code') or '-',)).fetchall())
                except Exception:
                    pass
                return self.send_json(d)

            # ===== العملاء =====
            if path == '/api/customers':
                return self.send_json(rows_to_list(conn.execute("SELECT * FROM customers ORDER BY full_name").fetchall()))
            m = re.match(r'^/api/customers/(\d+)$', path)
            if m:
                cid = int(m.group(1))
                c = conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
                if not c: return self.send_json({'error':'غير موجود'}, 404)
                d = row_to_dict(c)
                d['events'] = rows_to_list(conn.execute(
                    "SELECT * FROM events WHERE customer_id=? ORDER BY event_date DESC", (cid,)).fetchall())
                return self.send_json(d)

            # ===== المخزون =====
            if path == '/api/inventory':
                warehouse = query.get('warehouse', [None])[0]
                category_id = query.get('category_id', [None])[0]
                sql = """SELECT i.*, c.name as category_name FROM inventory_items i
                         LEFT JOIN inventory_categories c ON i.category_id=c.id WHERE 1=1"""
                params = []
                if warehouse: sql += " AND i.warehouse=?"; params.append(warehouse)
                if category_id: sql += " AND i.category_id=?"; params.append(int(category_id))
                sql += " ORDER BY i.name"
                return self.send_json(rows_to_list(conn.execute(sql, params).fetchall()))

            m = re.match(r'^/api/inventory/code/(.+)$', path)
            if m:
                code = urllib.parse.unquote(m.group(1))
                row = conn.execute("""SELECT i.*, c.name as category_name FROM inventory_items i
                                     LEFT JOIN inventory_categories c ON i.category_id=c.id WHERE i.item_code=?""", (code,)).fetchone()
                return self.send_json(row_to_dict(row) if row else {'error':'غير موجود'}, 200 if row else 404)

            m = re.match(r'^/api/inventory/(\d+)$', path)
            if m:
                iid = int(m.group(1))
                item = conn.execute("""SELECT i.*, c.name as category_name FROM inventory_items i
                                      LEFT JOIN inventory_categories c ON i.category_id=c.id WHERE i.id=?""", (iid,)).fetchone()
                if not item: return self.send_json({'error':'غير موجود'}, 404)
                d = row_to_dict(item)
                d['images'] = rows_to_list(conn.execute(
                    "SELECT * FROM item_images WHERE item_id=? ORDER BY is_main DESC, id", (iid,)).fetchall())
                d['movements'] = rows_to_list(conn.execute(
                    """SELECT m.*, u.full_name as user_name, e.title as event_title FROM inventory_movements m
                       JOIN users u ON m.user_id=u.id LEFT JOIN events e ON m.event_id=e.id
                       WHERE m.item_id=? ORDER BY m.movement_date DESC LIMIT 50""", (iid,)).fetchall())
                return self.send_json(d)

            # ===== التصنيفات =====
            if path == '/api/categories':
                warehouse = query.get('warehouse', [None])[0]
                sql = "SELECT * FROM inventory_categories WHERE is_active=1"
                params = []
                if warehouse: sql += " AND warehouse=?"; params.append(warehouse)
                sql += " ORDER BY warehouse, sort_order, name"
                return self.send_json(rows_to_list(conn.execute(sql, params).fetchall()))

            # ===== الفرق والمستخدمون =====
            if path == '/api/teams':
                return self.send_json(rows_to_list(conn.execute("SELECT * FROM teams ORDER BY id").fetchall()))
            if path == '/api/users':
                return self.send_json(rows_to_list(conn.execute(
                    "SELECT id, username, full_name, role, is_active FROM users WHERE COALESCE(deleted,0)=0 ORDER BY full_name").fetchall()))

            # ===== خطط العمل =====
            if path == '/api/workplans':
                rows = conn.execute("""SELECT wp.*, e.title as event_title, e.event_date, e.event_code,
                                              e.actual_date,
                                              c.full_name as customer_name,
                                              u.full_name as designer_name,
                                              (SELECT COUNT(*) FROM work_plan_items WHERE plan_id=wp.id) as items_count,
                                              (SELECT COUNT(*) FROM warehouse_checklists WHERE plan_id=wp.id) as checklists_count
                                       FROM work_plans wp
                                       JOIN events e ON wp.event_id=e.id
                                       JOIN customers c ON e.customer_id=c.id
                                       LEFT JOIN users u ON wp.designer_id=u.id
                                       ORDER BY wp.created_at DESC""").fetchall()
                return self.send_json(rows_to_list(rows))

            m = re.match(r'^/api/workplans/(\d+)$', path)
            if m:
                pid = int(m.group(1))
                plan = conn.execute("""SELECT wp.*, e.title as event_title, e.event_date, e.event_code,
                                              e.venue_name, e.actual_date,
                                              c.full_name as customer_name,
                                              u.full_name as designer_name
                                       FROM work_plans wp JOIN events e ON wp.event_id=e.id
                                       JOIN customers c ON e.customer_id=c.id
                                       LEFT JOIN users u ON wp.designer_id=u.id
                                       WHERE wp.id=?""", (pid,)).fetchone()
                if not plan: return self.send_json({'error':'غير موجود'}, 404)
                d = row_to_dict(plan)
                d['items'] = rows_to_list(conn.execute(
                    """SELECT wpi.*, c.name as category_name, c.icon as category_icon
                       FROM work_plan_items wpi
                       LEFT JOIN inventory_categories c ON wpi.category_id=c.id
                       WHERE wpi.plan_id=? ORDER BY wpi.target_warehouse, wpi.sort_order, wpi.id""", (pid,)).fetchall())
                d['checklists'] = rows_to_list(conn.execute(
                    """SELECT cl.*, u.full_name as assignee_name,
                              (SELECT COUNT(*) FROM warehouse_checklist_items WHERE checklist_id=cl.id) as total_items,
                              (SELECT COUNT(*) FROM warehouse_checklist_items WHERE checklist_id=cl.id AND is_picked=1) as picked_items
                       FROM warehouse_checklists cl
                       LEFT JOIN users u ON cl.assigned_to=u.id
                       WHERE cl.plan_id=?""", (pid,)).fetchall())
                return self.send_json(d)

            # ===== التشيك ليست =====
            if path == '/api/checklists':
                warehouse = query.get('warehouse', [None])[0]
                status = query.get('status', [None])[0]
                sql = """SELECT cl.*, wp.title as plan_title, wp.plan_code, e.title as event_title,
                                e.event_date, e.event_code, c.full_name as customer_name,
                                u.full_name as assignee_name,
                                (SELECT COUNT(*) FROM warehouse_checklist_items WHERE checklist_id=cl.id) as total_items,
                                (SELECT COUNT(*) FROM warehouse_checklist_items WHERE checklist_id=cl.id AND is_picked=1) as picked_items
                         FROM warehouse_checklists cl
                         JOIN work_plans wp ON cl.plan_id=wp.id
                         JOIN events e ON cl.event_id=e.id
                         JOIN customers c ON e.customer_id=c.id
                         LEFT JOIN users u ON cl.assigned_to=u.id WHERE 1=1"""
                params = []
                if warehouse: sql += " AND cl.warehouse=?"; params.append(warehouse)
                if status: sql += " AND cl.status=?"; params.append(status)
                sql += " ORDER BY e.event_date"
                return self.send_json(rows_to_list(conn.execute(sql, params).fetchall()))

            m = re.match(r'^/api/checklists/(\d+)$', path)
            if m:
                cid = int(m.group(1))
                cl = conn.execute("""SELECT cl.*, wp.title as plan_title, wp.plan_code,
                                            e.title as event_title, e.event_code, e.event_date, e.venue_name,
                                            c.full_name as customer_name, u.full_name as assignee_name
                                     FROM warehouse_checklists cl
                                     JOIN work_plans wp ON cl.plan_id=wp.id
                                     JOIN events e ON cl.event_id=e.id
                                     JOIN customers c ON e.customer_id=c.id
                                     LEFT JOIN users u ON cl.assigned_to=u.id
                                     WHERE cl.id=?""", (cid,)).fetchone()
                if not cl: return self.send_json({'error':'غير موجود'}, 404)
                d = row_to_dict(cl)
                d['items'] = rows_to_list(conn.execute(
                    """SELECT cli.*, wpi.warehouse, wpi.custom_name, wpi.quantity as required_quantity,
                              wpi.sample_image, wpi.sticker_image, wpi.name_image,
                              wpi.color_code, wpi.fabric_code, wpi.notes as item_notes,
                              cat.name as category_name, cat.icon as category_icon,
                              up.full_name as picker_name
                       FROM warehouse_checklist_items cli
                       JOIN work_plan_items wpi ON cli.plan_item_id=wpi.id
                       LEFT JOIN inventory_categories cat ON wpi.category_id=cat.id
                       LEFT JOIN users up ON cli.picked_by=up.id
                       WHERE cli.checklist_id=?""", (cid,)).fetchall())
                return self.send_json(d)

            # ===== مهامي =====
            if path == '/api/my-tasks':
                uid = self.get_user_id() or 4
                return self.send_json(rows_to_list(conn.execute(
                    """SELECT t.*, e.title as event_title, e.event_date, e.venue_name
                       FROM event_tasks t JOIN events e ON t.event_id=e.id
                       WHERE t.assigned_to=? AND t.status IN ('pending','in_progress')
                       ORDER BY e.event_date""", (uid,)).fetchall()))

            if path == '/api/my-events':
                uid = self.get_user_id() or 4
                return self.send_json(rows_to_list(conn.execute(
                    """SELECT DISTINCT e.*, c.full_name as customer_name, ea.role as my_role, ea.arrival_time
                       FROM events e
                       LEFT JOIN event_assignments ea ON ea.event_id=e.id AND ea.user_id=?
                       JOIN customers c ON e.customer_id=c.id
                       WHERE e.event_date >= date('now','-1 day') AND e.status NOT IN ('cancelled','closed')
                       ORDER BY e.event_date""", (uid,)).fetchall()))

            if path == '/api/my-checklists':
                uid = self.get_user_id() or 5
                user_role = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
                role = user_role['role'] if user_role else None
                # تحديد المستودعات حسب دور المستخدم
                warehouses = []
                if role == 'warehouse':
                    user_team = conn.execute("SELECT team_id FROM users WHERE id=?", (uid,)).fetchone()
                    warehouses = ['decorations','accessories']
                elif role == 'factory':
                    warehouses = ['factory']
                else:
                    warehouses = ['decorations','accessories','factory']
                placeholders = ','.join(['?']*len(warehouses))
                rows = conn.execute(f"""SELECT cl.*, wp.title as plan_title, e.title as event_title,
                                              e.event_date, e.event_code, c.full_name as customer_name,
                                              (SELECT COUNT(*) FROM warehouse_checklist_items WHERE checklist_id=cl.id) as total_items,
                                              (SELECT COUNT(*) FROM warehouse_checklist_items WHERE checklist_id=cl.id AND is_picked=1) as picked_items
                                       FROM warehouse_checklists cl
                                       JOIN work_plans wp ON cl.plan_id=wp.id
                                       JOIN events e ON cl.event_id=e.id
                                       JOIN customers c ON e.customer_id=c.id
                                       WHERE cl.warehouse IN ({placeholders})
                                         AND cl.status IN ('pending','in_progress')
                                       ORDER BY e.event_date""", warehouses).fetchall()
                return self.send_json(rows_to_list(rows))

            return self.send_json({'error':'المسار غير موجود'}, 404)
        finally:
            conn.close()

    # ============================================================
    # API POST
    # ============================================================
    def handle_api_post(self, path):
        ctype = self.headers.get('Content-Type', '')
        is_multipart = 'multipart/form-data' in ctype

        _gconn = get_db()
        try:
            ok, status, msg, ctx = ac.check(_gconn, 'POST', path, self.get_user_id())
        finally:
            _gconn.close()
        self._ctx = ctx
        if not ok:
            return self.send_json({'error': msg, 'code': status}, status)

        # ===== رفع ملف =====
        if path == '/api/upload':
            fields, files = parse_multipart(self)
            if not files:
                return self.send_json({'error':'لم يتم رفع ملف'}, 400)
            subfolder = (fields or {}).get('subfolder', 'misc')
            file_key = list(files.keys())[0]
            url = save_uploaded_file(files[file_key], subfolder)
            return self.send_json({'success': True, 'url': url})

        # ===== رفع صورة من الكاميرا (Base64) =====
        if path == '/api/upload-image':
            data = self.get_body_json()
            url = save_data_url_image(data.get('image'), data.get('subfolder', 'photos'))
            if not url:
                return self.send_json({'error':'فشل حفظ الصورة'}, 400)
            return self.send_json({'success': True, 'url': url})

        conn = get_db()
        try:
            data = self.get_body_json()
            if path == '/api/exec/call' and self._ctx:
                import exec_native
                try:
                    return self.send_json(exec_native.call(conn, self._ctx, data or {}))
                except Exception as e:
                    import traceback; traceback.print_exc()
                    return self.send_json({'ok': False, 'error': 'خطأ في الخادم: ' + str(e)})
            if crm_routes.handle(self, conn, 'POST', path, {}, data, self._ctx, self.send_json):
                return
            if contracts_routes.handle(self, conn, 'POST', path, {}, data, self._ctx, self.send_json):
                return
            if wpgen_routes.handle(self, conn, 'POST', path, {}, data, self._ctx, self.send_json):
                return
            if ops_routes.handle(self, conn, 'POST', path, {}, data, self._ctx, self.send_json):
                return
            if self._ctx and expenses_routes.handle(self, conn, 'POST', path, {}, data, self._ctx, self.send_json):
                return
            if self._ctx and jard_native.handle(self, conn, 'POST', path, {}, data, self._ctx, self.send_json):
                return
            if self._ctx and hr_routes.handle(self, conn, 'POST', path, {}, data, self._ctx, self.send_json):
                return

            # نقاط POST الإضافية (تعليقات، موافقات)
            if comments_routes:
                handled = comments_routes.post_routes(self, conn, path, data,
                    self.get_user_id, self.send_json)
                if handled: return

            # نقاط POST الجديدة (مواد خام، مواعيد، صور، خطط فرعية، إلخ)
            if new_routes:
                handled = new_routes.post_routes(self, conn, path, data,
                    self.get_user_id, self.send_json, str(BASE_DIR))
                if handled: return

            # ===== تشغيل المزامنة يدويًا =====
            if path == '/api/sync/run' and sync_sheets:
                logs = []
                results = sync_sheets.run_sync(DB_PATH, log_callback=lambda m: logs.append(m))
                results['logs'] = logs
                # بعد جلب البيانات الجديدة من Google، نصدّرها أيضًا إلى Excel محلي
                if sync_to_excel and results.get('success'):
                    try:
                        sync_to_excel.export_all(DB_PATH, log_callback=lambda m: logs.append(m))
                    except Exception as _ee:
                        logs.append(f"⚠ Excel export skipped: {_ee}")
                return self.send_json(results)

            # ===== تصدير Excel فقط (بدون جلب من Google) =====
            if path == '/api/sync/export-excel' and sync_to_excel:
                logs = []
                results = sync_to_excel.export_all(DB_PATH, log_callback=lambda m: logs.append(m))
                results['logs'] = logs
                return self.send_json(results)

            # ===== تسجيل الدخول =====
            if path == '/api/login':
                user = conn.execute("SELECT * FROM users WHERE username=?", (data.get('username'),)).fetchone()
                if not user or not verify_password(data.get('password',''), user['password_hash']):
                    return self.send_json({'error':'بيانات الدخول غير صحيحة'}, 401)
                token = secrets.token_urlsafe(24)
                SESSIONS[token] = user['id']
                conn.execute("UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=?", (user['id'],))
                conn.commit()
                # نرجع language و can_record_expenses للواجهات
                user_keys = user.keys()
                lang = user['language'] if 'language' in user_keys and user['language'] else 'ar'
                can_exp = 1 if ('can_record_expenses' in user_keys and user['can_record_expenses']) else 0
                # الأدوار اللي تقدر تسجل مصاريف افتراضياً حتى بدون العمود
                if user['role'] in ('admin','owner','general_manager','finance','project_manager','supervisor'):
                    can_exp = 1
                return self.send_json({'token': token, 'user': {
                    'id': user['id'], 'username': user['username'],
                    'full_name': user['full_name'], 'role': user['role'],
                    'language': lang, 'can_record_expenses': can_exp}})

            # ===== العملاء =====
            if path == '/api/customers':
                cur = conn.execute("""INSERT INTO customers
                    (full_name, full_name_en, full_name_ur, id_number,
                     phone, alt_phone, emergency_phone, email,
                     customer_type, city, address, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                  (data.get('full_name'), data.get('full_name_en'), data.get('full_name_ur'),
                                   data.get('id_number'),
                                   data.get('phone'), data.get('alt_phone'), data.get('emergency_phone'),
                                   data.get('email'),
                                   data.get('customer_type','individual'), data.get('city'),
                                   data.get('address'), data.get('notes')))
                conn.commit()
                trigger_excel_export('customers')
                return self.send_json({'id': cur.lastrowid, 'success': True})

            # ===== المناسبات =====
            if path == '/api/events':
                code = gen_code(conn, 'EVT', 'events', 'event_code')
                # توليد كود العقد E/B/W حسب نوع المناسبة
                contract_code = data.get('contract_code') or gen_contract_code(conn, data.get('event_type'))
                # توليد رقم أمر التشغيل لو ما أُعطي
                op_order = data.get('operation_order')
                if not op_order:
                    last = conn.execute("SELECT operation_order FROM events WHERE operation_order LIKE 'O%' ORDER BY id DESC LIMIT 1").fetchone()
                    if last and last['operation_order']:
                        try:
                            op_order = f"O{int(last['operation_order'][1:]) + 1}"
                        except Exception:
                            op_order = "O1001"
                    else:
                        op_order = "O1001"
                cur = conn.execute("""INSERT INTO events
                                     (event_code, contract_code, operation_order,
                                      customer_id, event_type, title, description,
                                      event_date, event_start_time, event_end_time,
                                      venue_name, venue_address, guests_count, theme, status,
                                      total_price, coordinator_id, created_by)
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                  (code, contract_code, op_order,
                                   data.get('customer_id'), data.get('event_type'),
                                   data.get('title'), data.get('description'), data.get('event_date'),
                                   data.get('event_start_time'), data.get('event_end_time'),
                                   data.get('venue_name'), data.get('venue_address'),
                                   data.get('guests_count'), data.get('theme'),
                                   data.get('status','lead'), data.get('total_price',0),
                                   data.get('supervisor_id'), self.get_user_id() or 1))
                conn.commit()
                trigger_excel_export('events')
                return self.send_json({
                    'id': cur.lastrowid,
                    'event_code': code,
                    'contract_code': contract_code,
                    'operation_order': op_order,
                    'success': True
                })

            # ===== المخزون =====
            if path == '/api/inventory':
                cur = conn.execute("""INSERT INTO inventory_items
                                     (item_code, name, description, category_id, warehouse,
                                      sticker_image, main_image, color_code, fabric_code,
                                      unit_cost, rental_price, quantity_total, quantity_available,
                                      condition, status, location_in_warehouse, notes)
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'in_warehouse', ?, ?)""",
                                  (data.get('item_code'), data.get('name'), data.get('description'),
                                   data.get('category_id'), data.get('warehouse'),
                                   data.get('sticker_image'), data.get('main_image'),
                                   data.get('color_code'), data.get('fabric_code'),
                                   data.get('unit_cost',0), data.get('rental_price',0),
                                   data.get('quantity_total',1), data.get('quantity_total',1),
                                   data.get('condition','excellent'),
                                   data.get('location_in_warehouse'), data.get('notes')))
                conn.commit()
                trigger_excel_export('inventory')
                return self.send_json({'id': cur.lastrowid, 'success': True})

            # ===== خروج/إرجاع المخزون =====
            if path == '/api/inventory/checkout':
                item_id, event_id, qty = data.get('item_id'), data.get('event_id'), data.get('quantity',1)
                uid = self.get_user_id() or 4
                conn.execute("""INSERT INTO inventory_movements (item_id, event_id, movement_type, quantity, user_id, notes, photo_path)
                               VALUES (?, ?, 'checkout', ?, ?, ?, ?)""",
                            (item_id, event_id, qty, uid, data.get('notes'), data.get('photo_path')))
                conn.execute("""UPDATE inventory_items SET status='in_event', quantity_available=quantity_available-?,
                               times_used=times_used+1, last_used_date=CURRENT_TIMESTAMP WHERE id=?""", (qty, item_id))
                conn.commit()
                return self.send_json({'success': True})

            if path == '/api/inventory/checkin':
                item_id, event_id, qty = data.get('item_id'), data.get('event_id'), data.get('quantity',1)
                cond = data.get('condition','excellent')
                uid = self.get_user_id() or 4
                conn.execute("""INSERT INTO inventory_movements (item_id, event_id, movement_type, quantity, condition_after, user_id, notes, photo_path)
                               VALUES (?, ?, 'checkin', ?, ?, ?, ?, ?)""",
                            (item_id, event_id, qty, cond, uid, data.get('notes'), data.get('photo_path')))
                if cond == 'lost':
                    conn.execute("UPDATE inventory_items SET status='lost', condition='lost' WHERE id=?", (item_id,))
                else:
                    conn.execute("""UPDATE inventory_items SET status='in_warehouse', condition=?,
                                   quantity_available=quantity_available+? WHERE id=?""", (cond, qty, item_id))
                conn.commit()
                return self.send_json({'success': True})

            # ===== خطط العمل =====
            if path == '/api/workplans':
                code = gen_code(conn, 'WP', 'work_plans', 'plan_code')
                uid = self.get_user_id() or 2
                cur = conn.execute("""INSERT INTO work_plans
                                     (plan_code, event_id, title, description, designer_id, designer_notes, status)
                                     VALUES (?, ?, ?, ?, ?, ?, 'draft')""",
                                  (code, data.get('event_id'), data.get('title'),
                                   data.get('description'), uid, data.get('planner_notes') or data.get('designer_notes')))
                plan_id = cur.lastrowid
                # إضافة العناصر مع كل التفاصيل (CNC، ستيكر، أولوية، ترجمات)
                for idx, item in enumerate(data.get('items', [])):
                    conn.execute("""INSERT INTO work_plan_items
                                   (plan_id, target_warehouse, category_id, item_id,
                                    custom_name, custom_name_en, custom_name_ur,
                                    quantity, sample_image, sticker_image, name_image,
                                    color_code, fabric_code, dimensions,
                                    notes, notes_en, notes_ur, notes_red,
                                    needs_refurb, refurb_notes, sort_order,
                                    cnc_required, sticker_required, priority)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (plan_id,
                                 item.get('target_warehouse') or item.get('warehouse') or 'decorations',
                                 item.get('category_id'), item.get('item_id'),
                                 item.get('custom_name'), item.get('custom_name_en'), item.get('custom_name_ur'),
                                 str(item.get('quantity','1')),
                                 item.get('sample_image'), item.get('sticker_image'), item.get('name_image'),
                                 item.get('color_code'), item.get('fabric_code'), item.get('dimensions'),
                                 item.get('notes'), item.get('notes_en'), item.get('notes_ur'), item.get('notes_red'),
                                 1 if item.get('needs_refurb') else 0, item.get('refurb_notes'), idx,
                                 1 if item.get('cnc_required') else 0,
                                 1 if item.get('sticker_required') else 0,
                                 item.get('priority', 'normal')))
                conn.commit()
                return self.send_json({'id': plan_id, 'plan_code': code, 'success': True})

            if path == '/api/workplans/approve':
                plan_id = data.get('plan_id')
                uid = self.get_user_id() or 1
                plan = conn.execute("SELECT * FROM work_plans WHERE id=?", (plan_id,)).fetchone()
                if not plan: return self.send_json({'error':'غير موجود'}, 404)
                conn.execute("""UPDATE work_plans SET status='approved', approved_by=?, approved_at=CURRENT_TIMESTAMP WHERE id=?""",
                            (uid, plan_id))
                warehouses = conn.execute("SELECT DISTINCT target_warehouse FROM work_plan_items WHERE plan_id=?", (plan_id,)).fetchall()
                for wh in warehouses:
                    wh_name = wh['target_warehouse']
                    cur = conn.execute("""INSERT INTO warehouse_checklists (plan_id, event_id, warehouse, status)
                                         VALUES (?, ?, ?, 'pending')""", (plan_id, plan['event_id'], wh_name))
                    cl_id = cur.lastrowid
                    items = conn.execute("SELECT id FROM work_plan_items WHERE plan_id=? AND target_warehouse=?", (plan_id, wh_name)).fetchall()
                    for it in items:
                        conn.execute("INSERT INTO warehouse_checklist_items (checklist_id, plan_item_id) VALUES (?, ?)",
                                    (cl_id, it['id']))
                conn.commit()
                return self.send_json({'success': True})

            if path == '/api/checklist-items/pick':
                item_id = data.get('item_id')
                uid = self.get_user_id() or 5
                conn.execute("""UPDATE warehouse_checklist_items
                               SET is_picked=1, picked_quantity=?, picked_by=?, picked_at=CURRENT_TIMESTAMP, notes=?
                               WHERE id=?""",
                            (data.get('picked_quantity',1), uid, data.get('notes'), item_id))
                cli = conn.execute("SELECT checklist_id FROM warehouse_checklist_items WHERE id=?", (item_id,)).fetchone()
                if cli:
                    cl_id = cli['checklist_id']
                    rest = conn.execute("SELECT COUNT(*) c FROM warehouse_checklist_items WHERE checklist_id=? AND is_picked=0", (cl_id,)).fetchone()
                    if rest['c'] == 0:
                        conn.execute("UPDATE warehouse_checklists SET status='ready', completed_at=CURRENT_TIMESTAMP WHERE id=?", (cl_id,))
                    else:
                        conn.execute("UPDATE warehouse_checklists SET status='in_progress' WHERE id=? AND status='pending'", (cl_id,))
                conn.commit()
                return self.send_json({'success': True})

            if path == '/api/checklist-items/unpick':
                item_id = data.get('item_id')
                conn.execute("UPDATE warehouse_checklist_items SET is_picked=0, picked_quantity=0, picked_by=NULL, picked_at=NULL WHERE id=?", (item_id,))
                cli = conn.execute("SELECT checklist_id FROM warehouse_checklist_items WHERE id=?", (item_id,)).fetchone()
                if cli:
                    conn.execute("UPDATE warehouse_checklists SET status='in_progress', completed_at=NULL WHERE id=?", (cli['checklist_id'],))
                conn.commit()
                return self.send_json({'success': True})

            if path == '/api/tasks/complete':
                tid = data.get('task_id')
                uid = self.get_user_id() or 4
                conn.execute("UPDATE event_tasks SET status='completed', completed_at=CURRENT_TIMESTAMP, completed_by=?, notes=COALESCE(?, notes) WHERE id=?",
                            (uid, data.get('notes'), tid))
                conn.commit()
                return self.send_json({'success': True})

            if path == '/api/tasks/start':
                conn.execute("UPDATE event_tasks SET status='in_progress' WHERE id=?", (data.get('task_id'),))
                conn.commit()
                return self.send_json({'success': True})

            if path == '/api/payments':
                eid, amount = data.get('event_id'), data.get('amount',0)
                conn.execute("""INSERT INTO event_payments (event_id, amount, payment_method, payment_type, reference, received_by, notes)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (eid, amount, data.get('payment_method'), data.get('payment_type'),
                             data.get('reference'), self.get_user_id() or 1, data.get('notes')))
                conn.execute("UPDATE events SET paid_amount=paid_amount+? WHERE id=?", (amount, eid))
                conn.commit()
                return self.send_json({'success': True})

            if path == '/api/event-photos':
                conn.execute("""INSERT INTO event_photos (event_id, photo_type, photo_path, caption, uploaded_by)
                               VALUES (?, ?, ?, ?, ?)""",
                            (data.get('event_id'), data.get('photo_type','other'),
                             data.get('photo_path'), data.get('caption'), self.get_user_id() or 1))
                conn.commit()
                return self.send_json({'success': True})

            return self.send_json({'error':'المسار غير موجود'}, 404)
        finally:
            conn.close()

    def handle_api_put(self, path):
        conn = get_db()
        try:
            data = self.get_body_json()
            if self.guard(conn, 'PUT', path, {}, data):
                return
            # حقول مسموح بتعديلها لكل جدول (whitelist للأمان)
            ALLOWED = {
                'events': {'event_code','operation_order','contract_code','customer_id','event_type','title','title_en','title_ur','description',
                           'event_date','actual_date','event_start_time','event_end_time','venue_name','venue_name_en','venue_name_ur',
                           'venue_address','venue_address_en','venue_address_ur','venue_map_url','guests_count',
                           'theme','color_palette','status','total_price','paid_amount','insurance_amount','insurance_returned',
                           'discount','coordinator_id','project_manager_id','designer_id'},
                'customers': {'full_name','full_name_en','full_name_ur','id_number','phone','alt_phone','emergency_phone',
                              'email','customer_type','city','city_en','city_ur','address','notes','preferences','rating'},
                'inventory': {'name','name_en','name_ur','description','category_id','warehouse','branch','main_image','sticker_image',
                              'color_code','fabric_code','unit_cost','rental_price','quantity_total','quantity_available',
                              'condition','status','location_in_warehouse','notes'},
                'workplans': {'title','description','designer_notes','status'},
                'appointments': {'customer_id','customer_name','customer_phone','appointment_type','title',
                                  'appointment_date','start_time','end_time','location','assigned_to',
                                  'related_event_id','status','color_label','notes'},
                'raw-materials': {'name','material_type','brand','color_code','size_or_dimensions','unit','branch',
                                  'quantity','min_quantity','unit_cost','image_path','location','supplier','notes'},
            }
            TABLE = {
                'events':'events','customers':'customers','inventory':'inventory_items',
                'workplans':'work_plans','appointments':'appointments','raw-materials':'raw_materials'
            }
            for entity, allowed_fields in ALLOWED.items():
                m = re.match(rf'^/api/{entity}/(\d+)$', path)
                if m:
                    eid = int(m.group(1))
                    table = TABLE[entity]
                    fields, params = [], []
                    for k, v in data.items():
                        if k in allowed_fields:
                            fields.append(f"{k}=?"); params.append(v)
                    if not fields:
                        return self.send_json({'error': 'لا توجد حقول مسموح تعديلها'}, 400)
                    # تحديث updated_at لو موجود في الجدول
                    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                    if 'updated_at' in cols:
                        fields.append("updated_at=CURRENT_TIMESTAMP")
                    params.append(eid)
                    try:
                        conn.execute(f"UPDATE {table} SET {', '.join(fields)} WHERE id=?", params)
                        conn.commit()
                    except sqlite3.OperationalError as e:
                        return self.send_json({'error': str(e)}, 400)
                    # سجل التدقيق
                    try:
                        conn.execute("""INSERT INTO audit_log (user_id, action, entity_type, entity_id, new_value)
                                        VALUES (?, 'UPDATE', ?, ?, ?)""",
                                     (self.get_user_id(), entity, eid, json.dumps(data, ensure_ascii=False)))
                        conn.commit()
                    except Exception:
                        pass
                    # مزامنة تلقائية للـ Excel (ثنائية الاتجاه)
                    trigger_excel_export(entity)
                    return self.send_json({'success': True})
            return self.send_json({'error':'غير موجود'}, 404)
        finally:
            conn.close()

    def handle_api_delete(self, path):
        conn = get_db()
        try:
            if self.guard(conn, 'DELETE', path, {}):
                return
            entity_table = [
                ('events','events'),
                ('inventory','inventory_items'),
                ('workplans','work_plans'),
                ('customers','customers'),
                ('appointments','appointments'),
                ('raw-materials','raw_materials'),
            ]
            for entity, table in entity_table:
                m = re.match(rf'^/api/{entity}/(\d+)$', path)
                if m:
                    eid = int(m.group(1))
                    if entity == 'events':
                        # المناسبات: soft delete (إلغاء بدل حذف)
                        conn.execute("UPDATE events SET status='cancelled' WHERE id=?", (eid,))
                    elif entity == 'customers':
                        # العملاء: تحقق إن مالهم مناسبات أولًا
                        n = conn.execute("SELECT COUNT(*) c FROM events WHERE customer_id=?", (eid,)).fetchone()['c']
                        if n > 0:
                            return self.send_json({'error': f'لا يمكن حذف العميل لأنه مرتبط بـ {n} مناسبة. ألغِ المناسبات أولًا.'}, 400)
                        conn.execute(f"DELETE FROM {table} WHERE id=?", (eid,))
                    else:
                        conn.execute(f"DELETE FROM {table} WHERE id=?", (eid,))
                    conn.commit()
                    # سجل التدقيق
                    try:
                        conn.execute("""INSERT INTO audit_log (user_id, action, entity_type, entity_id)
                                        VALUES (?, 'DELETE', ?, ?)""",
                                     (self.get_user_id(), entity, eid))
                        conn.commit()
                    except Exception:
                        pass
                    return self.send_json({'success': True})
            return self.send_json({'error':'غير موجود'}, 404)
        finally:
            conn.close()


def main():
    init_database()
    print("\n" + "="*60)
    print("  Abela Events System v2.0")
    print("="*60)
    print(f"  Dashboard:   http://localhost:{PORT}/")
    print(f"  Mobile App:  http://localhost:{PORT}/mobile/")
    print(f"  Owner View:  http://localhost:{PORT}/owner/")
    print("="*60)
    if not os.environ.get("ABELLA_HOSTED"):
        print("  Logins: see README")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((HOST, PORT), AbelaHandler) as httpd:
        try: httpd.serve_forever()
        except KeyboardInterrupt: print("\nStopped.")

if __name__ == '__main__':
    main()
