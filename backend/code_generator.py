"""
وحدة توليد الأكواد التلقائية
=================================
تولّد أكواد العقود (B/W/E) وأوامر التشغيل (O) ورموز خطط العمل (WP)
بنفس النمط المعتمد في جداول Excel لأبيلا.
"""

import datetime

# ============================================================
# أكواد العقود حسب نوع المناسبة
# ============================================================

CONTRACT_PREFIX = {
    'newborn': 'B',      # استقبال مولود
    'special': 'W',      # مناسبة خاصة (Wedding/etc)
    'exhibition': 'E',   # معرض
}


def generate_contract_code(conn, event_type):
    """
    توليد كود عقد جديد.
    مثال: B1013, W1004, E1002

    يبدأ من 1001 (مثل الإكسل) ويزيد تسلسليًا.
    """
    prefix = CONTRACT_PREFIX.get(event_type)
    if not prefix:
        raise ValueError(f"نوع مناسبة غير معروف: {event_type}")

    # نبحث عن آخر رقم استُخدم لهذا النوع
    rows = conn.execute(
        "SELECT contract_code FROM events WHERE contract_code LIKE ? ORDER BY id DESC",
        (f"{prefix}%",)
    ).fetchall()

    max_num = 1000  # نبدأ من 1001
    for r in rows:
        code = r['contract_code']
        try:
            num = int(code[len(prefix):])
            if num > max_num:
                max_num = num
        except (ValueError, IndexError):
            continue

    # نتحقق أيضًا من جدول sheet_contracts (المزامنة)
    try:
        sheet_rows = conn.execute(
            "SELECT contract_code FROM sheet_contracts WHERE contract_code LIKE ?",
            (f"{prefix}%",)
        ).fetchall()
        for r in sheet_rows:
            code = r['contract_code']
            try:
                num = int(code[len(prefix):])
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                continue
    except Exception:
        pass

    return f"{prefix}{max_num + 1}"


def generate_operation_order(conn):
    """
    توليد رقم أمر تشغيل جديد.
    مثال: O1017, O1018...

    يبدأ من 1001 ويزيد تسلسليًا.
    """
    rows = conn.execute(
        "SELECT operation_order FROM events WHERE operation_order LIKE 'O%' ORDER BY id DESC"
    ).fetchall()

    max_num = 1000
    for r in rows:
        op = r['operation_order']
        if not op:
            continue
        try:
            num = int(op[1:])
            if num > max_num:
                max_num = num
        except (ValueError, IndexError):
            continue

    # نتحقق من sheet_contracts
    try:
        sheet_rows = conn.execute(
            "SELECT operation_order FROM sheet_contracts WHERE operation_order LIKE 'O%'"
        ).fetchall()
        for r in sheet_rows:
            op = r['operation_order']
            if not op:
                continue
            try:
                num = int(op[1:])
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                continue
    except Exception:
        pass

    return f"O{max_num + 1}"


def generate_event_code(conn):
    """
    توليد كود نظام داخلي للمناسبة.
    مثال: EVT-2026-0017
    """
    year = datetime.date.today().year
    cnt = conn.execute(
        "SELECT COUNT(*) c FROM events WHERE event_code LIKE ?",
        (f"EVT-{year}-%",)
    ).fetchone()['c']
    return f"EVT-{year}-{cnt + 1:04d}"


def generate_work_plan_code(conn):
    """
    توليد كود خطة عمل.
    مثال: WP-2026-0042
    """
    year = datetime.date.today().year
    cnt = conn.execute(
        "SELECT COUNT(*) c FROM work_plans WHERE plan_code LIKE ?",
        (f"WP-{year}-%",)
    ).fetchone()['c']
    return f"WP-{year}-{cnt + 1:04d}"


def generate_appointment_code(conn):
    """
    توليد كود موعد.
    مثال: APT-2026-0123
    """
    year = datetime.date.today().year
    cnt = conn.execute(
        "SELECT COUNT(*) c FROM appointments WHERE appointment_code LIKE ?",
        (f"APT-{year}-%",)
    ).fetchone()['c']
    return f"APT-{year}-{cnt + 1:04d}"


def generate_risk_code(year, month):
    """
    توليد كود خطة إدارة مخاطر شهرية.
    مثال: RA-2026-05
    """
    return f"RA-{year}-{month:02d}"


def generate_inventory_code(conn, warehouse, category_id=None):
    """
    توليد كود قطعة مخزون جديد.
    أمثلة: DEC-T-001 (decorations - tables - 001)
           ACC-V-005 (accessories - vases - 005)
           RAW-PAINT-012 (factory raw - paint - 012)
    """
    warehouse_prefix = {
        'decorations': 'DEC',
        'accessories': 'ACC',
        'factory': 'FAC',
        'factory_raw': 'RAW',
    }
    prefix = warehouse_prefix.get(warehouse, 'INV')

    # نشتق حرف من اسم التصنيف
    cat_letter = 'X'
    if category_id:
        cat_row = conn.execute(
            "SELECT name FROM inventory_categories WHERE id=?", (category_id,)
        ).fetchone()
        if cat_row and cat_row['name']:
            # نأخذ أول حرف من الاسم (لاتيني أو عربي)
            name = cat_row['name'].strip()
            cat_letter = name[0].upper() if name else 'X'

    full_prefix = f"{prefix}-{cat_letter}-"
    cnt = conn.execute(
        "SELECT COUNT(*) c FROM inventory_items WHERE item_code LIKE ?",
        (f"{full_prefix}%",)
    ).fetchone()['c']
    return f"{full_prefix}{cnt + 1:03d}"


def generate_raw_material_code(conn, material_type):
    """
    توليد كود مادة خام.
    أمثلة: RAW-PAINT-001, RAW-WOOD-005, RAW-NAIL-012
    """
    type_codes = {
        'paint': 'PAINT', 'wood': 'WOOD', 'nail': 'NAIL',
        'wire': 'WIRE', 'fabric': 'FAB', 'flower_artificial': 'FLW',
        'metal': 'METAL', 'acrylic': 'ACR', 'adhesive': 'ADH',
        'tool': 'TOOL', 'consumable': 'CONS', 'other': 'OTH',
    }
    code = type_codes.get(material_type, 'MAT')
    full_prefix = f"RAW-{code}-"
    cnt = conn.execute(
        "SELECT COUNT(*) c FROM raw_materials WHERE material_code LIKE ?",
        (f"{full_prefix}%",)
    ).fetchone()['c']
    return f"{full_prefix}{cnt + 1:03d}"
