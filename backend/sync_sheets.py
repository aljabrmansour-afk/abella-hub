"""
وحدة مزامنة Google Sheets لنظام أبيلا
====================================
تجلب البيانات من 5 جداول Google Sheets وتحفظها في قاعدة البيانات:
1. العقود
2. مصاريف الإشراف
3. مصاريف التنفيذ
4. مصاريف الضيافة
5. المشتريات

ثم تربط كل المصاريف بالمناسبات (events) عن طريق رقم أمر التشغيل (operation_order)
وتحسب صافي الربح لكل مناسبة.
"""

import urllib.request
import csv
import io
import re
import sqlite3
import datetime
import time
from pathlib import Path

# روابط Google Sheets الفعلية لأبيلا
SHEETS = {
    'contracts': {
        'id': '1yd4YQwjV-kDkqqu4iwFmGAlQmwhGWOYrP-x2w5r4_kg',
        'name': 'العقود',
        'gid': '0',
    },
    'supervision_expenses': {
        'id': '110xUWBb4FdnYwIOg47RiFyqoyKKEW7bX40PlIKWGs90',
        'name': 'مصاريف الإشراف',
        'gid': '0',
    },
    'execution_expenses': {
        'id': '1jMWAK4sdkwwXJGArZQ3D8E3POM_82Nxzct5jrrRR-T4',
        'name': 'مصاريف التنفيذ',
        'gid': '0',
    },
    'hospitality_expenses': {
        'id': '1s9n9Y7PVArzLOrKlDQChMPd-anfApTaqmunj8EptsIY',
        'name': 'مصاريف الضيافة',
        'gid': '0',
    },
    'purchases': {
        'id': '1xvG_sfIddU7Poo5J54yVb4FjSckDX1pCrrE7Rd3Dd9g',
        'name': 'المشتريات',
        'gid': '0',
    },
}


def fetch_csv(sheet_id, gid='0'):
    """جلب الجدول كـ CSV من Google Sheets"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; AbelaSync/1.0)'
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        content = response.read().decode('utf-8')
    return list(csv.reader(io.StringIO(content)))


def to_number(val):
    """تحويل نص لرقم - يتعامل مع الأرقام العربية والفواصل"""
    if val is None or val == '' or val == '​':  # zero-width space
        return 0
    s = str(val).strip().replace(',', '').replace('٬', '').replace('٫', '.')
    s = s.replace('ر.س', '').replace('SAR', '').strip()
    # تحويل الأرقام العربية إلى لاتينية
    arabic_to_english = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    s = s.translate(arabic_to_english)
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0


def to_date(val):
    """تحويل تاريخ من صيغة 2026/05/07 إلى 2026-05-07"""
    if not val or val == '​':
        return None
    s = str(val).strip().replace('/', '-')
    # تحويل الأرقام العربية
    arabic_to_english = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    s = s.translate(arabic_to_english)
    # التحقق من الصيغة
    if re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', s):
        parts = s.split('-')
        return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    m = re.match(r'^(\d{1,2})-(\d{1,2})-(\d{4})', s)   # 19/10/2026
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    m = re.match(r'^(\d{4}-\d{2}-\d{2})[T ]', s)
    if m:
        return m.group(1)
    return None


def clean_text(val):
    """تنظيف النص - إزالة المسافات والرموز الخاصة"""
    if val is None:
        return None
    s = str(val).strip().replace('​', '')  # zero-width space
    return s if s else None


# ============================================================
# المزامنة
# ============================================================

def sync_contracts(conn, rows):
    """مزامنة جدول العقود"""
    if len(rows) < 2:
        return 0

    # حذف البيانات القديمة وإعادة التعبئة
    conn.execute("DELETE FROM sheet_contracts")

    count = 0
    # تخطي صفوف الترويسة (عادة الصف الأول والثاني)
    for row in rows[2:]:
        if len(row) < 5 or not clean_text(row[1]):  # رقم العقد فاضي = صف فاضي
            continue
        try:
            conn.execute("""INSERT INTO sheet_contracts
                (contract_code, operation_order, event_type, customer_name, venue,
                 contract_date, expected_date, actual_date,
                 contract_value, additional, contract_value_with_vat,
                 insurance, insurance_returned, discount, total_revenue,
                 received, remaining, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (clean_text(row[1]),                      # B: رقم العقد
                 clean_text(row[5]) if len(row) > 5 else None,   # F: رقم أمر التشغيل
                 clean_text(row[0]),                      # A: نوع المناسبة
                 clean_text(row[3]),                      # D: اسم العميل
                 clean_text(row[4]),                      # E: موقع
                 to_date(row[2]) if len(row) > 2 else None,       # C: تاريخ العقد
                 to_date(row[6]) if len(row) > 6 else None,       # G: متوقع
                 to_date(row[7]) if len(row) > 7 else None,       # H: فعلي
                 to_number(row[9]) if len(row) > 9 else 0,        # J: قيمة
                 to_number(row[10]) if len(row) > 10 else 0,      # K: إضافية
                 to_number(row[11]) if len(row) > 11 else 0,      # L: بعد الضريبة
                 to_number(row[12]) if len(row) > 12 else 0,      # M: تأمين
                 to_number(row[13]) if len(row) > 13 else 0,      # N: مسترد
                 to_number(row[14]) if len(row) > 14 else 0,      # O: خصم
                 to_number(row[15]) if len(row) > 15 else 0,      # P: إجمالي إيراد
                 to_number(row[16]) if len(row) > 16 else 0,      # Q: مستلم
                 to_number(row[17]) if len(row) > 17 else 0,      # R: متبقي
                 clean_text(row[18]) if len(row) > 18 else None,  # S: ملاحظات
                 clean_text(row[19]) if len(row) > 19 else None,  # T: حالة العقد
                ))
            count += 1
        except Exception as e:
            print(f"  ⚠ خطأ في صف عقد: {e}")
    return count


def sync_expenses(conn, rows, expense_type):
    """مزامنة جدول مصاريف (إشراف/تنفيذ/ضيافة)"""
    if len(rows) < 2:
        return 0

    # حذف البيانات القديمة لهذا النوع
    conn.execute("DELETE FROM sheet_expenses WHERE expense_type=?", (expense_type,))

    count = 0
    for row in rows[1:]:
        # رقم أمر التشغيل في العمود A (O####) — غير ذلك ترويسة/صف فاضي
        if len(row) < 5 or not re.match(r'^O\d+', clean_text(row[0]) or ''):
            continue
        try:
            # تحديد ترتيب الأعمدة (مصاريف التنفيذ مختلف قليلاً)
            if expense_type == 'execution':
                # رقم الفاتورة في الموقع 12، تاريخ في 13
                invoice_num = clean_text(row[12]) if len(row) > 12 else None
                invoice_date = to_date(row[13]) if len(row) > 13 else None
                quantity = to_number(row[10]) if len(row) > 10 else 0
                description = clean_text(row[11]) if len(row) > 11 else None
            else:
                # عام: رقم الفاتورة 10، تاريخ 11، البيان 12، الكمية 13
                invoice_num = clean_text(row[10]) if len(row) > 10 else None
                invoice_date = to_date(row[11]) if len(row) > 11 else None
                description = clean_text(row[12]) if len(row) > 12 else None
                quantity = to_number(row[13]) if len(row) > 13 else 0

            conn.execute("""INSERT INTO sheet_expenses
                (expense_type, operation_order, event_type, customer_name, venue,
                 expected_date, actual_date, project_status, responsible,
                 item_or_supplier, invoice_number, invoice_date, description, quantity,
                 total_amount, recoverable_vat, net_cost, payment_method,
                 paid, remaining, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (expense_type,
                 clean_text(row[0]),                       # A: أمر التشغيل
                 clean_text(row[1]) if len(row) > 1 else None,    # B: نوع
                 clean_text(row[2]) if len(row) > 2 else None,    # C: عميل
                 clean_text(row[3]) if len(row) > 3 else None,    # D: موقع
                 to_date(row[4]) if len(row) > 4 else None,       # E: متوقع
                 to_date(row[5]) if len(row) > 5 else None,       # F: مؤكد
                 clean_text(row[7]) if len(row) > 7 else None,    # H: حالة المشروع
                 clean_text(row[8]) if len(row) > 8 else None,    # I: المسؤول
                 clean_text(row[9]) if len(row) > 9 else None,    # J: البند/المورد
                 invoice_num, invoice_date, description, quantity,
                 to_number(row[14]) if len(row) > 14 else 0,      # المبلغ الإجمالي
                 to_number(row[15]) if len(row) > 15 else 0,      # ضريبة
                 to_number(row[16]) if len(row) > 16 else 0,      # صافي
                 clean_text(row[17]) if len(row) > 17 else None,  # طريقة السداد
                 to_number(row[18]) if len(row) > 18 else 0,      # المسدد
                 to_number(row[19]) if len(row) > 19 else 0,      # المتبقي
                 clean_text(row[20]) if len(row) > 20 else None,  # ملاحظات
                ))
            count += 1
        except Exception as e:
            print(f"  ⚠ خطأ في صف {expense_type}: {e}")
    return count


def sync_purchases(conn, rows):
    """مزامنة جدول المشتريات"""
    if len(rows) < 2:
        return 0
    conn.execute("DELETE FROM sheet_purchases")

    count = 0
    for row in rows[1:]:
        if len(row) < 5 or not re.match(r'^O\d+', clean_text(row[0]) or ''):
            continue
        try:
            conn.execute("""INSERT INTO sheet_purchases
                (operation_order, event_type, customer_name, venue,
                 expected_date, actual_date, project_status, responsible,
                 item, invoice_number, invoice_date, description, quantity,
                 total_amount, recoverable_vat, net_cost, payment_method,
                 paid, remaining, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (clean_text(row[0]),
                 clean_text(row[1]) if len(row) > 1 else None,
                 clean_text(row[2]) if len(row) > 2 else None,
                 clean_text(row[3]) if len(row) > 3 else None,
                 to_date(row[4]) if len(row) > 4 else None,
                 to_date(row[5]) if len(row) > 5 else None,
                 clean_text(row[7]) if len(row) > 7 else None,
                 clean_text(row[8]) if len(row) > 8 else None,
                 clean_text(row[9]) if len(row) > 9 else None,
                 clean_text(row[10]) if len(row) > 10 else None,
                 to_date(row[11]) if len(row) > 11 else None,
                 clean_text(row[12]) if len(row) > 12 else None,
                 to_number(row[13]) if len(row) > 13 else 0,
                 to_number(row[14]) if len(row) > 14 else 0,
                 to_number(row[15]) if len(row) > 15 else 0,
                 to_number(row[16]) if len(row) > 16 else 0,
                 clean_text(row[17]) if len(row) > 17 else None,
                 to_number(row[18]) if len(row) > 18 else 0,
                 to_number(row[19]) if len(row) > 19 else 0,
                 clean_text(row[20]) if len(row) > 20 else None,
                ))
            count += 1
        except Exception as e:
            print(f"  ⚠ خطأ في صف مشتريات: {e}")
    return count



# ============================================================
# قواعد الحالة والتكلفة (مصدر واحد للحقيقة)
# ============================================================
DONE_WORDS = ('منتهي', 'منتهية', 'مكتمل', 'مكتملة', 'منفذ', 'منفذة', 'تم التنفيذ', 'مغلق')
CANCEL_WORDS = ('ملغي', 'ملغى', 'ملغية', 'إلغاء', 'الغاء')
SYSTEM_PROGRESS = ('planning', 'ready')


def riyadh_today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).date().isoformat()


def derive_status(sheet_status, expected, current=None, confirmed=None):
    """الحالة حسب التاريخ المؤكد فقط:
    مؤكد ومضى = منتهية، مؤكد واليوم = قيد التنفيذ، غير مؤكد = لا تنتهي مهما مضى المتوقع (تبقى بانتظار التأكيد)."""
    st = (sheet_status or '').strip()
    if any(w in st for w in CANCEL_WORDS):
        return 'cancelled'
    if any(w in st for w in DONE_WORDS):
        return 'completed'
    today = riyadh_today()
    if confirmed:
        if confirmed < today:
            return 'completed'
        if confirmed == today:
            return 'in_progress'
    # غير مؤكد أو مؤكد لتاريخ قادم: نحافظ على تقدم داخل المنصة (تخطيط/جاهزة)
    if current in SYSTEM_PROGRESS:
        return current
    return 'contracted'


def revenue_ex_vat(c):
    """الإيراد قبل الضريبة (الربح يُحسب عليه لا على المبلغ شامل الضريبة)"""
    base = (c['contract_value'] or 0) + (c['additional'] or 0)
    if base:
        return base - (c['discount'] or 0)
    return round((c['contract_value_with_vat'] or 0) / 1.15, 2)


def _has_table(conn, name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def event_cost(conn, op):
    """صافي تكلفة المناسبة من فواتير المصروفات الأربعة (إشراف/تنفيذ/ضيافة/مشتريات)"""
    if _has_table(conn, 'exp_invoices') and conn.execute("SELECT 1 FROM exp_invoices WHERE source='sheet' LIMIT 1").fetchone():
        r = conn.execute("""SELECT COALESCE(SUM(CASE WHEN COALESCE(net,0)<>0 THEN net ELSE COALESCE(total,0)-COALESCE(vat,0) END),0)
                            FROM exp_invoices WHERE operation_order=? AND COALESCE(is_test,0)=0
                            AND COALESCE(status,'active') NOT IN ('deleted','cancelled','محذوف','ملغي')""", (op,)).fetchone()
        return round(r[0] or 0, 2)
    a = conn.execute("SELECT COALESCE(SUM(net_cost),0) FROM sheet_expenses WHERE operation_order=?", (op,)).fetchone()[0]
    b = conn.execute("SELECT COALESCE(SUM(net_cost),0) FROM sheet_purchases WHERE operation_order=?", (op,)).fetchone()[0]
    return round((a or 0) + (b or 0), 2)


def refresh_events(conn):
    """إعادة حساب الحالة والتكلفة والربح لكل المناسبات (تُستدعى بعد استيراد المصروفات وكل يوم)"""
    _rf = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        return _refresh(conn)
    finally:
        conn.row_factory = _rf


def _refresh(conn):
    confirmed = {}   # تواريخ مؤكدة من إدارة العمليات/تأكيد المناسبات
    if _has_table(conn, 'opn_orders'):
        for r in conn.execute("SELECT O, C FROM opn_orders WHERE COALESCE(O,'')<>'' AND COALESCE(C,'')<>''"):
            confirmed[r['O']] = r['C']
    sc = {r['operation_order']: r for r in conn.execute("SELECT * FROM sheet_contracts WHERE operation_order IS NOT NULL")} \
        if _has_table(conn, 'sheet_contracts') else {}
    n = 0
    for e in conn.execute("SELECT id, operation_order, status, event_date, actual_date, total_price, sync_source FROM events").fetchall():
        op = e['operation_order']
        cost = event_cost(conn, op) if op else 0
        c = sc.get(op)
        if c is not None and (e['sync_source'] or '') == 'google_sheets':
            st = derive_status(c['status'], c['expected_date'] or e['event_date'], e['status'],
                               c['actual_date'] or e['actual_date'] or confirmed.get(op))
            rev = revenue_ex_vat(c)
        else:
            st = e['status']
            if st not in ('cancelled', 'lead', 'quoted', 'completed', 'closed'):
                d = e['actual_date'] or confirmed.get(op)   # المؤكد فقط
                if d and d < riyadh_today():
                    st = 'completed'
            rev = round((e['total_price'] or 0) / 1.15, 2)
        conn.execute("UPDATE events SET status=?, cost_total=?, profit=? WHERE id=?", (st, cost, round(rev - cost, 2), e['id']))
        n += 1
    conn.commit()
    return n

# ============================================================
# دمج البيانات في events و customers
# ============================================================

def merge_into_events(conn):
    """
    دمج بيانات Google Sheets في جدول events:
    - إنشاء/تحديث customers من جدول العقود
    - إنشاء/تحديث events بربط رقم أمر التشغيل
    - تجميع المصاريف وحساب صافي الربح
    """
    contracts = conn.execute("SELECT * FROM sheet_contracts WHERE operation_order IS NOT NULL").fetchall()

    customers_added = 0
    events_added = 0
    events_updated = 0

    for c in contracts:
        op_order = c['operation_order']
        customer_name = c['customer_name']
        if not op_order or not customer_name:
            continue

        # 1. التحقق من وجود العميل، إن لم يوجد ننشئه
        cust = conn.execute("SELECT id FROM customers WHERE full_name=?", (customer_name,)).fetchone()
        if not cust:
            cur = conn.execute("""INSERT INTO customers (full_name, phone, customer_type, city)
                                 VALUES (?, '0500000000', 'individual', 'الرياض')""", (customer_name,))
            customer_id = cur.lastrowid
            customers_added += 1
        else:
            customer_id = cust['id']

        total_cost = event_cost(conn, op_order)

        # 3. التحقق من وجود المناسبة بنفس رقم أمر التشغيل
        existing = conn.execute("SELECT id, sync_source FROM events WHERE operation_order=?", (op_order,)).fetchone()
        # حماية: عقد أُنشئ داخل النظام بنفس رقم التشغيل → لا نكتب فوقه (تعارض يحتاج مراجعة)
        if existing and (existing['sync_source'] or '') == 'system':
            print(f"  ⚠ تعارض رقم تشغيل {op_order}: موجود في النظام وفي جدول Google — تم تجاهل صف الجدول")
            continue

        # تحديد نوع المناسبة (يجب أن يكون من القيم المسموحة في CHECK constraint)
        event_type_map = {
            'استقبال مولود': 'newborn',
            'مناسبة خاصة': 'special',
            'معرض': 'exhibition',
            'زفاف': 'special',
            'خطوبة': 'special',
        }
        event_type = event_type_map.get(c['event_type'], 'special')

        revenue = c['contract_value_with_vat'] or c['contract_value'] or 0
        paid = c['received'] or 0
        if _has_table(conn, 'gen_payments'):   # دفعات مسجلة في المولد/المنصة بعد آخر تحديث للجدول
            gp = conn.execute("SELECT COALESCE(SUM(amount),0) FROM gen_payments WHERE contract_code=?", (c['contract_code'],)).fetchone()[0]
            paid = max(paid, gp or 0)
        profit = round(revenue_ex_vat(c) - total_cost, 2)
        exp_d = c['expected_date']
        act_d = c['actual_date']
        cur_status = None
        if existing:
            r0 = conn.execute("SELECT status FROM events WHERE id=?", (existing['id'],)).fetchone()
            cur_status = r0['status'] if r0 else None
        status = derive_status(c['status'], exp_d, cur_status, act_d)

        if existing:
            # تحديث
            conn.execute("""UPDATE events SET
                customer_id=?, event_type=?, contract_code=?, total_price=?, paid_amount=?,
                insurance_amount=?, insurance_returned=?, discount=?,
                cost_total=?, profit=?, venue_name=?, sync_source='google_sheets',
                event_date=COALESCE(?, event_date), actual_date=COALESCE(?, actual_date),
                status=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (customer_id, event_type, c['contract_code'], revenue, paid,
                 c['insurance'] or 0, c['insurance_returned'] or 0, c['discount'] or 0,
                 total_cost, profit, c['venue'],
                 exp_d or act_d, act_d, status, existing['id']))
            events_updated += 1
        else:
            # إنشاء
            year = datetime.date.today().year
            cnt = conn.execute("SELECT COUNT(*) c FROM events WHERE event_code LIKE ?",
                              (f"EVT-{year}-%",)).fetchone()['c'] + 1
            event_code = f"EVT-{year}-{cnt:04d}"

            event_date = exp_d or act_d or datetime.date.today().isoformat()
            title = f"{c['event_type'] or 'مناسبة'} — {customer_name}"

            conn.execute("""INSERT INTO events
                (event_code, operation_order, contract_code, customer_id, event_type, title,
                 event_date, venue_name, status, total_price, paid_amount,
                 insurance_amount, insurance_returned, discount,
                 cost_total, profit, sync_source, created_by, actual_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'google_sheets', 1, ?)""",
                (event_code, op_order, c['contract_code'], customer_id, event_type, title,
                 event_date, c['venue'], status, revenue, paid,
                 c['insurance'] or 0, c['insurance_returned'] or 0, c['discount'] or 0,
                 total_cost, profit, act_d))
            events_added += 1

    return customers_added, events_added, events_updated


# ============================================================
# الواجهة الرئيسية
# ============================================================

def run_sync(db_path, log_callback=None):
    """تشغيل المزامنة الكاملة. يُرجع قاموس بالنتائج."""
    if log_callback is None:
        log_callback = print

    start = time.time()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    results = {
        'started_at': datetime.datetime.now().isoformat(),
        'sheets': {},
        'merged': {},
        'success': False,
        'error': None,
    }

    try:
        # 1. جلب ومزامنة كل جدول
        log_callback("📡 بدء المزامنة من Google Sheets...")

        # العقود
        log_callback(f"  ⬇ جلب العقود...")
        rows = fetch_csv(SHEETS['contracts']['id'], SHEETS['contracts']['gid'])
        cnt = sync_contracts(conn, rows)
        results['sheets']['contracts'] = cnt
        log_callback(f"    ✓ {cnt} عقد")

        # مصاريف الإشراف
        log_callback(f"  ⬇ جلب مصاريف الإشراف...")
        rows = fetch_csv(SHEETS['supervision_expenses']['id'], SHEETS['supervision_expenses']['gid'])
        cnt = sync_expenses(conn, rows, 'supervision')
        results['sheets']['supervision_expenses'] = cnt
        log_callback(f"    ✓ {cnt} صف")

        # مصاريف التنفيذ
        log_callback(f"  ⬇ جلب مصاريف التنفيذ...")
        rows = fetch_csv(SHEETS['execution_expenses']['id'], SHEETS['execution_expenses']['gid'])
        cnt = sync_expenses(conn, rows, 'execution')
        results['sheets']['execution_expenses'] = cnt
        log_callback(f"    ✓ {cnt} صف")

        # مصاريف الضيافة
        log_callback(f"  ⬇ جلب مصاريف الضيافة...")
        rows = fetch_csv(SHEETS['hospitality_expenses']['id'], SHEETS['hospitality_expenses']['gid'])
        cnt = sync_expenses(conn, rows, 'hospitality')
        results['sheets']['hospitality_expenses'] = cnt
        log_callback(f"    ✓ {cnt} صف")

        # المشتريات
        log_callback(f"  ⬇ جلب المشتريات...")
        rows = fetch_csv(SHEETS['purchases']['id'], SHEETS['purchases']['gid'])
        cnt = sync_purchases(conn, rows)
        results['sheets']['purchases'] = cnt
        log_callback(f"    ✓ {cnt} صف")

        # 2. دمج البيانات في events و customers
        log_callback(f"\n🔄 دمج البيانات في النظام...")
        customers_added, events_added, events_updated = merge_into_events(conn)
        refresh_events(conn)
        results['merged'] = {
            'customers_added': customers_added,
            'events_added': events_added,
            'events_updated': events_updated,
        }
        log_callback(f"  ✓ {customers_added} عميل جديد")
        log_callback(f"  ✓ {events_added} مناسبة جديدة")
        log_callback(f"  ✓ {events_updated} مناسبة محدثة")

        # 3. تسجيل في sync_log
        duration = int((time.time() - start) * 1000)
        total_rows = sum(results['sheets'].values())
        conn.execute("""INSERT INTO sync_log (source, status, rows_imported, duration_ms)
                       VALUES ('google_sheets_full', 'success', ?, ?)""", (total_rows, duration))
        conn.commit()

        results['success'] = True
        results['duration_ms'] = duration
        log_callback(f"\n✓ المزامنة اكتملت بنجاح في {duration/1000:.2f} ثانية")

    except Exception as e:
        results['error'] = str(e)
        log_callback(f"\n✗ خطأ في المزامنة: {e}")
        try:
            conn.execute("""INSERT INTO sync_log (source, status, error_message)
                           VALUES ('google_sheets_full', 'error', ?)""", (str(e),))
            conn.commit()
        except:
            pass
    finally:
        conn.close()

    return results


def get_last_sync_status(db_path):
    """الحصول على آخر حالة مزامنة"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("""SELECT * FROM sync_log
                             WHERE source='google_sheets_full'
                             ORDER BY id DESC LIMIT 1""").fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_sync_history(db_path, limit=10):
    """سجل المزامنات الأخيرة"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"""SELECT * FROM sync_log
                               ORDER BY id DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


if __name__ == '__main__':
    # تشغيل مباشر للاختبار
    import sys
    db = Path(__file__).parent / 'db' / 'abela.db'
    print(f"Database: {db}")
    results = run_sync(db)
    print("\n" + "="*60)
    print(f"النتائج: {results}")
