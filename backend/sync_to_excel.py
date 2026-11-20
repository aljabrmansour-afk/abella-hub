"""
وحدة التصدير إلى Excel لنظام أبيلا
====================================
تصدّر البيانات من قاعدة البيانات إلى ملفات Excel محلية بنفس
هيكل Google Sheets الأصلية، ليتم فتحها مباشرة في Excel.

تنشئ الملفات في مجلد: D:\\Abela\\abela_system\\exports\\
- contracts.xlsx        — العقود
- supervision.xlsx      — مصاريف الإشراف
- execution.xlsx        — مصاريف التنفيذ
- hospitality.xlsx      — مصاريف الضيافة
- purchases.xlsx        — المشتريات
- events.xlsx           — المناسبات (مصدر أبيلا - أحدث البيانات)
- inventory.xlsx        — المخزون

تُستدعى هذه الوحدة:
1. تلقائيًا عند حفظ/تعديل أي عقد أو مناسبة أو مصروف
2. يدويًا عبر API: POST /api/sync/export-excel
3. عبر زر "تصدير Excel" في لوحة التحكم
"""

import sqlite3
import datetime
import time
from pathlib import Path

def _try_import_openpyxl():
    """يحاول استيراد openpyxl، ولو غير موجود يثبّتها تلقائيًا"""
    try:
        from openpyxl import Workbook
        return True
    except ImportError:
        # محاولة تثبيت تلقائي
        import subprocess, sys
        try:
            print("⏳ تثبيت openpyxl تلقائيًا...")
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install', 'openpyxl', '--quiet'],
                timeout=180
            )
            print("✓ تم التثبيت")
            return True
        except Exception as e:
            print(f"✗ فشل التثبيت التلقائي: {e}")
            return False

HAS_OPENPYXL = _try_import_openpyxl()
if HAS_OPENPYXL:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter


# ============================================================
# إعدادات التنسيق
# ============================================================

HEADER_FILL = None
HEADER_FONT = None
BORDER = None

def _init_styles():
    """تهيئة الأنماط مرة واحدة"""
    global HEADER_FILL, HEADER_FONT, BORDER
    if HEADER_FILL is None and HAS_OPENPYXL:
        HEADER_FILL = PatternFill(start_color="C9A227", end_color="C9A227", fill_type="solid")
        HEADER_FONT = Font(name='Arial', size=11, bold=True, color="FFFFFF")
        thin = Side(border_style="thin", color="888888")
        BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)


def _write_sheet(ws, headers, rows, col_widths=None):
    """كتابة ورقة بنفس النمط: عنوان ذهبي + حدود"""
    _init_styles()

    # كتابة العناوين
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = BORDER

    # كتابة الصفوف
    for row_idx, row in enumerate(rows, 2):
        for col_idx, value in enumerate(row, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(horizontal='right', vertical='center', wrap_text=False)
            cell.border = BORDER
            cell.font = Font(name='Arial', size=10)

    # عرض الأعمدة
    if col_widths:
        for col_idx, width in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width

    # تجميد الصف الأول
    ws.freeze_panes = 'A2'

    # اتجاه RTL
    ws.sheet_view.rightToLeft = True


# ============================================================
# مصدّرات الجداول الفردية
# ============================================================

def export_contracts(conn, exports_dir):
    """تصدير العقود (مدمج events + sheet_contracts)"""
    if not HAS_OPENPYXL:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = "العقود"

    headers = [
        'نوع المناسبة', 'رقم العقد', 'تاريخ العقد', 'اسم العميل', 'الموقع',
        'رقم أمر التشغيل', 'متوقع', 'فعلي', 'الحالة',
        'قيمة العقد', 'إضافية', 'بعد الضريبة',
        'تأمين', 'مسترد', 'خصم',
        'إجمالي الإيراد', 'مستلم', 'متبقي', 'ملاحظات'
    ]

    # أحدث البيانات من events (المصدر الموثوق)
    rows = conn.execute("""
        SELECT
            CASE e.event_type
                WHEN 'newborn' THEN 'استقبال مولود'
                WHEN 'special' THEN 'مناسبة خاصة'
                WHEN 'exhibition' THEN 'معرض'
                ELSE e.event_type
            END as event_type_ar,
            e.contract_code, e.created_at, c.full_name, e.venue_name,
            e.operation_order, e.event_date,
            (SELECT actual_date FROM sheet_contracts WHERE contract_code=e.contract_code LIMIT 1) as actual_date,
            e.status,
            e.total_price,
            COALESCE((SELECT additional FROM sheet_contracts WHERE contract_code=e.contract_code LIMIT 1), 0),
            e.total_price * 1.15,
            e.insurance_amount, e.insurance_returned, e.discount,
            e.total_price + COALESCE((SELECT additional FROM sheet_contracts WHERE contract_code=e.contract_code LIMIT 1), 0),
            e.paid_amount,
            (e.total_price - e.paid_amount),
            e.description
        FROM events e
        LEFT JOIN customers c ON c.id=e.customer_id
        ORDER BY e.event_date DESC
    """).fetchall()

    data_rows = [list(r) for r in rows]
    col_widths = [16, 12, 12, 22, 18, 14, 12, 12, 12,
                  12, 10, 12, 10, 10, 10, 14, 12, 12, 28]
    _write_sheet(ws, headers, data_rows, col_widths)

    out = exports_dir / 'contracts.xlsx'
    wb.save(out)
    return str(out), len(data_rows)


def export_expenses(conn, exports_dir, expense_type, filename, sheet_name):
    """تصدير ورقة مصاريف من sheet_expenses + جدول expenses المحلي"""
    if not HAS_OPENPYXL:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    headers = [
        'رقم أمر التشغيل', 'نوع المناسبة', 'اسم العميل', 'الموقع',
        'متوقع', 'مؤكد', '', 'حالة المشروع', 'المسؤول',
        'البند/المورد', 'رقم الفاتورة', 'تاريخ الفاتورة',
        'البيان', 'الكمية', 'المبلغ الإجمالي',
        'ضريبة قابلة للاسترداد', 'صافي التكلفة',
        'طريقة السداد', 'المسدد', 'المتبقي', 'ملاحظات'
    ]

    rows = conn.execute("""
        SELECT operation_order, event_type, customer_name, venue,
               expected_date, actual_date, '', project_status, responsible,
               item_or_supplier, invoice_number, invoice_date,
               description, quantity, total_amount,
               recoverable_vat, net_cost,
               payment_method, paid, remaining, notes
        FROM sheet_expenses WHERE expense_type=?
        ORDER BY id DESC
    """, (expense_type,)).fetchall()

    data_rows = [list(r) for r in rows]

    # إضافة المصاريف اليدوية من جدول expenses
    try:
        local = conn.execute("""
            SELECT ex.operation_order, '', '', '',
                   ex.expense_date, ex.expense_date, '', 'مسجّل', u.full_name,
                   ex.supplier, ex.invoice_number, ex.expense_date,
                   ex.description, ex.quantity, ex.total_amount,
                   ex.recoverable_vat, ex.net_cost,
                   ex.payment_method, ex.paid_amount,
                   (ex.total_amount - COALESCE(ex.paid_amount, 0)),
                   ex.notes
            FROM expenses ex
            LEFT JOIN users u ON u.id=ex.created_by
            WHERE ex.expense_type=?
            ORDER BY ex.id DESC
        """, (expense_type,)).fetchall()
        data_rows.extend([list(r) for r in local])
    except Exception:
        pass  # جدول expenses قد لا يحتوي بيانات

    col_widths = [14, 14, 20, 16, 12, 12, 4, 14, 14,
                  18, 14, 12, 24, 8, 12, 14, 12, 14, 10, 10, 24]
    _write_sheet(ws, headers, data_rows, col_widths)

    out = exports_dir / filename
    wb.save(out)
    return str(out), len(data_rows)


def export_purchases(conn, exports_dir):
    """تصدير المشتريات"""
    if not HAS_OPENPYXL:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = "المشتريات"

    headers = [
        'رقم أمر التشغيل', 'نوع المناسبة', 'اسم العميل', 'الموقع',
        'متوقع', 'مؤكد', '', 'حالة المشروع', 'المسؤول',
        'البند', 'رقم الفاتورة', 'تاريخ الفاتورة',
        'البيان', 'الكمية', 'المبلغ الإجمالي',
        'ضريبة قابلة للاسترداد', 'صافي التكلفة',
        'طريقة السداد', 'المسدد', 'المتبقي', 'ملاحظات'
    ]

    rows = conn.execute("""
        SELECT operation_order, event_type, customer_name, venue,
               expected_date, actual_date, '', project_status, responsible,
               item, invoice_number, invoice_date,
               description, quantity, total_amount,
               recoverable_vat, net_cost,
               payment_method, paid, remaining, notes
        FROM sheet_purchases ORDER BY id DESC
    """).fetchall()

    data_rows = [list(r) for r in rows]
    col_widths = [14, 14, 20, 16, 12, 12, 4, 14, 14,
                  18, 14, 12, 24, 8, 12, 14, 12, 14, 10, 10, 24]
    _write_sheet(ws, headers, data_rows, col_widths)

    out = exports_dir / 'purchases.xlsx'
    wb.save(out)
    return str(out), len(data_rows)


def export_events(conn, exports_dir):
    """تصدير المناسبات بكامل التفاصيل (يشمل ترجمات الأسماء والمواقع)"""
    if not HAS_OPENPYXL:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = "المناسبات"

    headers = [
        'كود المناسبة', 'رقم أمر التشغيل', 'رقم العقد',
        'العميل (عربي)', 'العميل (إنجليزي)', 'العميل (أردو)',
        'رقم الهوية', 'الجوال', 'جوال طوارئ', 'البريد',
        'المدينة (عربي)', 'المدينة (إنجليزي)',
        'النوع', 'العنوان (عربي)', 'العنوان (إنجليزي)', 'العنوان (أردو)',
        'تاريخ المناسبة', 'الموقع (عربي)', 'الموقع (إنجليزي)', 'الموقع (أردو)',
        'العنوان التفصيلي (عربي)', 'العنوان التفصيلي (إنجليزي)',
        'عدد الضيوف', 'الحالة',
        'القيمة الإجمالية', 'المسدد', 'المتبقي',
        'تأمين', 'مسترد', 'خصم',
        'إجمالي التكلفة', 'الربح',
        'المنسقة', 'مدير المشروع', 'المصمم',
        'تاريخ الإنشاء'
    ]

    # تحقق من الأعمدة الموجودة (بعض الترجمات أُضيفت عبر migration)
    ev_cols = {c[1] for c in conn.execute("PRAGMA table_info(events)").fetchall()}
    cu_cols = {c[1] for c in conn.execute("PRAGMA table_info(customers)").fetchall()}

    def col(table_cols, name, prefix=''):
        return f"{prefix}{name}" if name in table_cols else "''"

    rows = conn.execute(f"""
        SELECT
            e.event_code, e.operation_order, e.contract_code,
            c.full_name, {col(cu_cols,'full_name_en','c.')}, {col(cu_cols,'full_name_ur','c.')},
            {col(cu_cols,'id_number','c.')}, c.phone, {col(cu_cols,'emergency_phone','c.')}, c.email,
            c.city, {col(cu_cols,'city_en','c.')},
            CASE e.event_type
                WHEN 'newborn' THEN 'استقبال مولود'
                WHEN 'special' THEN 'مناسبة خاصة'
                WHEN 'exhibition' THEN 'معرض'
                ELSE e.event_type
            END,
            e.title, {col(ev_cols,'title_en','e.')}, {col(ev_cols,'title_ur','e.')},
            e.event_date, e.venue_name, {col(ev_cols,'venue_name_en','e.')}, {col(ev_cols,'venue_name_ur','e.')},
            e.venue_address, {col(ev_cols,'venue_address_en','e.')},
            e.guests_count, e.status,
            e.total_price, e.paid_amount, (e.total_price - e.paid_amount),
            e.insurance_amount, e.insurance_returned, e.discount,
            e.cost_total, e.profit,
            (SELECT full_name FROM users WHERE id=e.coordinator_id),
            (SELECT full_name FROM users WHERE id=e.project_manager_id),
            (SELECT full_name FROM users WHERE id=e.designer_id),
            e.created_at
        FROM events e
        LEFT JOIN customers c ON c.id=e.customer_id
        ORDER BY e.event_date DESC
    """).fetchall()

    data_rows = [list(r) for r in rows]
    col_widths = [14, 14, 12,
                  20, 20, 20, 14, 14, 14, 22, 12, 12,
                  14, 22, 22, 22, 12, 18, 18, 18, 22, 22,
                  10, 12, 12, 12, 12, 10, 10, 10, 12, 12, 16, 16, 16, 16]
    _write_sheet(ws, headers, data_rows, col_widths)

    out = exports_dir / 'events.xlsx'
    wb.save(out)
    return str(out), len(data_rows)


def export_inventory(conn, exports_dir):
    """تصدير المخزون مع كل الترجمات والمعلومات"""
    if not HAS_OPENPYXL:
        return None

    wb = Workbook()

    # ورقة العناصر
    ws1 = wb.active
    ws1.title = "العناصر"

    headers1 = [
        'الكود', 'الاسم (عربي)', 'الاسم (إنجليزي)', 'الاسم (أردو)',
        'التصنيف', 'المستودع', 'الفرع',
        'الكمية الكلية', 'المتوفرة',
        'الحالة', 'سعر التكلفة', 'سعر الإيجار',
        'الموقع في المستودع', 'تاريخ الإضافة', 'الصورة'
    ]

    # نتحقق من وجود عمود branch (أُضيف عبر migration)
    inv_cols = [c[1] for c in conn.execute("PRAGMA table_info(inventory_items)").fetchall()]
    branch_col = "i.branch" if 'branch' in inv_cols else "''"

    rows1 = conn.execute(f"""
        SELECT i.item_code, i.name, i.name_en, i.name_ur,
               cat.name, i.warehouse, {branch_col},
               i.quantity_total, i.quantity_available,
               i.condition, i.unit_cost, i.rental_price,
               i.location_in_warehouse, i.created_at, i.main_image
        FROM inventory_items i
        LEFT JOIN inventory_categories cat ON cat.id=i.category_id
        ORDER BY i.item_code
    """).fetchall()

    data1 = [list(r) for r in rows1]
    col_widths1 = [12, 22, 22, 22, 18, 14, 10, 10, 10, 12, 12, 12, 16, 14, 30]
    _write_sheet(ws1, headers1, data1, col_widths1)

    # ورقة الخامات
    ws2 = wb.create_sheet("الخامات")
    headers2 = [
        'الكود', 'الاسم', 'الفئة', 'الفرع',
        'الكمية', 'الوحدة', 'الحد الأدنى', 'سعر الوحدة',
        'الموقع', 'تاريخ الإضافة'
    ]

    try:
        rm_cols = [c[1] for c in conn.execute("PRAGMA table_info(raw_materials)").fetchall()]
        branch_col2 = "branch" if 'branch' in rm_cols else "''"
        rows2 = conn.execute(f"""
            SELECT material_code, name, material_type, {branch_col2},
                   quantity, unit, min_quantity, unit_cost,
                   location, created_at
            FROM raw_materials
            ORDER BY material_code
        """).fetchall()
        data2 = [list(r) for r in rows2]
    except Exception:
        data2 = []

    _write_sheet(ws2, headers2, data2, [12, 22, 16, 10, 10, 10, 10, 12, 14, 14])

    out = exports_dir / 'inventory.xlsx'
    wb.save(out)
    return str(out), len(data1) + len(data2)


def export_workplans(conn, exports_dir):
    """تصدير خطط العمل (يعتمد على رقم أمر التشغيل)"""
    if not HAS_OPENPYXL:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = "خطط العمل"

    headers = [
        'رقم الخطة', 'كود الخطة', 'رقم أمر التشغيل', 'كود المناسبة',
        'العميل', 'تاريخ المناسبة',
        'العنوان', 'المصمم',
        'الحالة', 'عدد البنود',
        'مستودعات مستهدفة', 'تاريخ الإنشاء'
    ]

    try:
        rows = conn.execute("""
            SELECT wp.id, wp.plan_code, e.operation_order, e.event_code,
                   c.full_name, e.event_date,
                   wp.title,
                   (SELECT full_name FROM users WHERE id=wp.designer_id),
                   wp.status,
                   (SELECT COUNT(*) FROM work_plan_items WHERE plan_id=wp.id),
                   (SELECT GROUP_CONCAT(DISTINCT target_warehouse) FROM work_plan_items WHERE plan_id=wp.id),
                   wp.created_at
            FROM work_plans wp
            LEFT JOIN events e ON e.id=wp.event_id
            LEFT JOIN customers c ON c.id=e.customer_id
            ORDER BY wp.created_at DESC
        """).fetchall()
        data = [list(r) for r in rows]
    except Exception:
        data = []

    _write_sheet(ws, headers, data, [8, 14, 14, 14, 20, 12, 22, 16, 12, 10, 22, 14])

    out = exports_dir / 'workplans.xlsx'
    wb.save(out)
    return str(out), len(data)


# ============================================================
# الواجهة الرئيسية
# ============================================================

def export_all(db_path, exports_dir=None, log_callback=None):
    """تصدير شامل لكل ملفات Excel"""
    if log_callback is None:
        log_callback = print

    if not HAS_OPENPYXL:
        log_callback("✗ openpyxl غير مثبّت — يجب تشغيل: pip install openpyxl")
        return {'success': False, 'error': 'openpyxl not installed'}

    if exports_dir is None:
        exports_dir = Path(db_path).parent.parent / 'exports'
    else:
        exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)

    start = time.time()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    results = {
        'started_at': datetime.datetime.now().isoformat(),
        'files': {},
        'success': False,
        'exports_dir': str(exports_dir),
    }

    try:
        log_callback(f"📂 مجلد التصدير: {exports_dir}")

        log_callback("  → العقود...")
        path, n = export_contracts(conn, exports_dir)
        results['files']['contracts'] = {'path': path, 'rows': n}
        log_callback(f"    ✓ {n} عقد → {Path(path).name}")

        log_callback("  → مصاريف الإشراف...")
        path, n = export_expenses(conn, exports_dir, 'supervision', 'supervision.xlsx', "مصاريف الإشراف")
        results['files']['supervision'] = {'path': path, 'rows': n}
        log_callback(f"    ✓ {n} صف")

        log_callback("  → مصاريف التنفيذ...")
        path, n = export_expenses(conn, exports_dir, 'execution', 'execution.xlsx', "مصاريف التنفيذ")
        results['files']['execution'] = {'path': path, 'rows': n}
        log_callback(f"    ✓ {n} صف")

        log_callback("  → مصاريف الضيافة...")
        path, n = export_expenses(conn, exports_dir, 'hospitality', 'hospitality.xlsx', "مصاريف الضيافة")
        results['files']['hospitality'] = {'path': path, 'rows': n}
        log_callback(f"    ✓ {n} صف")

        log_callback("  → المشتريات...")
        path, n = export_purchases(conn, exports_dir)
        results['files']['purchases'] = {'path': path, 'rows': n}
        log_callback(f"    ✓ {n} صف")

        log_callback("  → المناسبات (تفصيلية)...")
        path, n = export_events(conn, exports_dir)
        results['files']['events'] = {'path': path, 'rows': n}
        log_callback(f"    ✓ {n} مناسبة")

        log_callback("  → المخزون...")
        path, n = export_inventory(conn, exports_dir)
        results['files']['inventory'] = {'path': path, 'rows': n}
        log_callback(f"    ✓ {n} عنصر")

        log_callback("  → خطط العمل...")
        path, n = export_workplans(conn, exports_dir)
        results['files']['workplans'] = {'path': path, 'rows': n}
        log_callback(f"    ✓ {n} خطة")

        # تسجيل في sync_log
        duration = int((time.time() - start) * 1000)
        total_rows = sum(f['rows'] for f in results['files'].values())
        try:
            conn.execute("""INSERT INTO sync_log (source, status, rows_imported, duration_ms)
                           VALUES ('excel_export', 'success', ?, ?)""", (total_rows, duration))
            conn.commit()
        except Exception:
            pass

        results['success'] = True
        results['duration_ms'] = duration
        log_callback(f"\n✓ تم التصدير في {duration/1000:.2f} ثانية")
        log_callback(f"  مجموع الصفوف: {total_rows}")

    except Exception as e:
        results['error'] = str(e)
        log_callback(f"\n✗ خطأ: {e}")
        try:
            conn.execute("""INSERT INTO sync_log (source, status, error_message)
                           VALUES ('excel_export', 'error', ?)""", (str(e),))
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()

    return results


def export_quick(db_path, what='events'):
    """تصدير سريع لجزء واحد فقط - يستخدم بعد كل حفظ"""
    if not HAS_OPENPYXL:
        return None
    try:
        exports_dir = Path(db_path).parent.parent / 'exports'
        exports_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            if what == 'events':
                export_events(conn, exports_dir)
                export_contracts(conn, exports_dir)
            elif what == 'inventory':
                export_inventory(conn, exports_dir)
            elif what == 'workplans':
                export_workplans(conn, exports_dir)
            elif what == 'expenses':
                for t in ('supervision', 'execution', 'hospitality'):
                    export_expenses(conn, exports_dir, t, f'{t}.xlsx',
                                    {'supervision': 'مصاريف الإشراف',
                                     'execution': 'مصاريف التنفيذ',
                                     'hospitality': 'مصاريف الضيافة'}[t])
                export_purchases(conn, exports_dir)
        finally:
            conn.close()
        return True
    except Exception as e:
        print(f"  ⚠ Excel quick export failed: {e}")
        return False


if __name__ == '__main__':
    db = Path(__file__).parent / 'db' / 'abela.db'
    print(f"Database: {db}")
    if not HAS_OPENPYXL:
        print("⚠ openpyxl not installed. Run:")
        print("  pip install openpyxl")
        import sys; sys.exit(1)
    results = export_all(db)
    print("\n" + "="*60)
    print(f"النتائج: success={results.get('success')}, files={len(results.get('files', {}))}")
