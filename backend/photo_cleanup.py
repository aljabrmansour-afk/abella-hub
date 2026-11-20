"""
وحدة الصيانة الدورية للصور
============================
- حذف الصور بعد 30 يوم من الرفع (إلا المؤرشفة منها)
- إنشاء الخطط الفرعية الست تلقائيًا من خطة العمل
- اكتشاف الديكورات المتشابهة (لخطة المخاطر)
"""

import os
import datetime
from pathlib import Path


# ============================================================
# حذف الصور القديمة (شهري)
# ============================================================

def cleanup_old_photos(conn, uploads_dir, retention_days=30):
    """
    يحذف الصور التي مر عليها أكثر من retention_days
    إلا الصور المُحفوظة بـ is_archived=1
    """
    threshold = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    threshold_str = threshold.isoformat()

    # نختار الصور المنتهية الصلاحية
    rows = conn.execute(
        """SELECT id, photo_path FROM photo_documents
           WHERE is_archived=0 AND deleted_at IS NULL
             AND taken_at < ?""",
        (threshold_str,)
    ).fetchall()

    deleted_count = 0
    failed_count = 0

    for row in rows:
        photo_path = row['photo_path']
        # photo_path يبدأ بـ /uploads/...
        if photo_path and photo_path.startswith('/uploads/'):
            rel_path = photo_path.replace('/uploads/', '', 1)
            full_path = Path(uploads_dir) / rel_path
            try:
                if full_path.exists():
                    full_path.unlink()
                # نُعلّم في قاعدة البيانات
                conn.execute(
                    "UPDATE photo_documents SET deleted_at=CURRENT_TIMESTAMP WHERE id=?",
                    (row['id'],)
                )
                deleted_count += 1
            except Exception as e:
                print(f"  ⚠ فشل حذف {photo_path}: {e}")
                failed_count += 1

    conn.commit()

    return {
        'deleted': deleted_count,
        'failed': failed_count,
        'threshold_days': retention_days,
    }


def archive_photo(conn, photo_id):
    """يحفظ صورة من الحذف التلقائي"""
    conn.execute(
        "UPDATE photo_documents SET is_archived=1 WHERE id=?",
        (photo_id,)
    )
    conn.commit()


# ============================================================
# توليد الخطط الفرعية الست من خطة العمل
# ============================================================

PLAN_TYPE_TARGETS = {
    'warehouse_decor': ['decorations'],
    'warehouse_acc': ['accessories'],
    'factory': ['factory'],
    'purchases': ['purchasing'],
    'risk': ['risk'],
    'hospitality': ['hospitality'],
}

PLAN_TYPE_NAMES = {
    'warehouse_decor': 'خطة مستودع الديكورات',
    'warehouse_acc': 'خطة مستودع الاكسسوارات',
    'factory': 'خطة المصنع',
    'purchases': 'خطة المشتريات',
    'risk': 'خطة إدارة المخاطر',
    'hospitality': 'خطة الضيافة',
}


def generate_sub_plans(conn, work_plan_id):
    """
    عند اعتماد خطة العمل الأساسية، تُولّد ست خطط فرعية تلقائيًا.
    كل خطة فرعية تحتوي على البنود المخصصة لها (حسب target_warehouse).
    """
    plan = conn.execute(
        "SELECT * FROM work_plans WHERE id=?", (work_plan_id,)
    ).fetchone()
    if not plan:
        return None

    event_id = plan['event_id']
    items = conn.execute(
        "SELECT * FROM work_plan_items WHERE plan_id=?", (work_plan_id,)
    ).fetchall()

    created_sub_plans = []
    for plan_type, targets in PLAN_TYPE_TARGETS.items():
        # نختار البنود لهذه الخطة الفرعية
        matching_items = [it for it in items if it['target_warehouse'] in targets]
        if not matching_items and plan_type not in ('risk', 'purchases'):
            continue  # لا داعي لإنشاء خطة فاضية

        title = PLAN_TYPE_NAMES.get(plan_type, plan_type)

        cur = conn.execute(
            """INSERT INTO sub_plans (parent_plan_id, event_id, plan_type, title, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (work_plan_id, event_id, plan_type, title)
        )
        sub_plan_id = cur.lastrowid

        # نضيف البنود
        for item in matching_items:
            conn.execute(
                """INSERT INTO sub_plan_items (sub_plan_id, work_plan_item_id)
                   VALUES (?, ?)""",
                (sub_plan_id, item['id'])
            )

        created_sub_plans.append({
            'id': sub_plan_id,
            'plan_type': plan_type,
            'title': title,
            'items_count': len(matching_items),
        })

    conn.commit()
    return created_sub_plans


# ============================================================
# اكتشاف الديكورات المتشابهة (لخطة المخاطر)
# ============================================================

def detect_similar_decorations(conn, year, month):
    """
    يكتشف المناسبات في نفس الشهر التي تستخدم نفس الألوان أو الأقمشة
    أو تصنيفات الديكور المتشابهة.

    يُنشئ خطة إدارة مخاطر تلقائيًا.
    """
    # نختار كل مناسبات هذا الشهر
    events = conn.execute(
        """SELECT e.id, e.title, e.event_date, e.theme, e.color_palette,
                  c.full_name as customer_name, e.venue_name
           FROM events e JOIN customers c ON e.customer_id=c.id
           WHERE strftime('%Y-%m', e.event_date) = ?""",
        (f"{year:04d}-{month:02d}",)
    ).fetchall()

    if len(events) < 2:
        return None

    # نبحث عن تشابهات
    similar_pairs = []
    for i, ev1 in enumerate(events):
        for ev2 in events[i+1:]:
            similarity = _check_similarity(ev1, ev2, conn)
            if similarity:
                similar_pairs.append({
                    'event1_id': ev1['id'],
                    'event2_id': ev2['id'],
                    'event1_name': ev1['customer_name'],
                    'event2_name': ev2['customer_name'],
                    'reasons': similarity,
                })

    if not similar_pairs:
        return None

    # ننشئ تقييم المخاطر
    risk_code = f"RA-{year:04d}-{month:02d}"

    # نتحقق إن التقييم موجود مسبقًا
    existing = conn.execute(
        "SELECT id FROM risk_assessments WHERE risk_code=?", (risk_code,)
    ).fetchone()

    if existing:
        # نحذف البنود القديمة لإعادة البناء
        conn.execute("DELETE FROM risk_assessment_items WHERE assessment_id=?", (existing['id'],))
        assessment_id = existing['id']
    else:
        cur = conn.execute(
            """INSERT INTO risk_assessments (risk_code, period_year, period_month, title, created_by)
               VALUES (?, ?, ?, ?, 1)""",
            (risk_code, year, month, f"إدارة مخاطر شهر {month} للديكورات المتشابهة")
        )
        assessment_id = cur.lastrowid

    # نضيف البنود
    for pair in similar_pairs:
        priority = 'high' if len(pair['reasons']) > 1 else 'medium'
        conn.execute(
            """INSERT INTO risk_assessment_items
               (assessment_id, event_id, similar_event_id, similarity_type, priority, mitigation_notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (assessment_id, pair['event1_id'], pair['event2_id'],
             ', '.join(pair['reasons']), priority,
             f"تشابه مع مناسبة {pair['event2_name']}: {', '.join(pair['reasons'])}")
        )

    conn.commit()

    return {
        'assessment_id': assessment_id,
        'risk_code': risk_code,
        'similar_pairs': len(similar_pairs),
    }


def _check_similarity(ev1, ev2, conn):
    """يفحص التشابه بين مناسبتين، يُرجع قائمة بأسباب التشابه"""
    reasons = []

    # تشابه الثيم
    if ev1['theme'] and ev2['theme'] and ev1['theme'] == ev2['theme']:
        reasons.append('نفس الثيم')

    # تشابه لوحة الألوان
    if ev1['color_palette'] and ev2['color_palette']:
        colors1 = set(c.strip() for c in (ev1['color_palette'] or '').split(',') if c.strip())
        colors2 = set(c.strip() for c in (ev2['color_palette'] or '').split(',') if c.strip())
        if colors1 & colors2:  # تقاطع
            reasons.append('ألوان متشابهة')

    # تشابه عناصر المخزون المحجوزة
    items1 = set(r['item_id'] for r in conn.execute(
        "SELECT item_id FROM event_inventory WHERE event_id=?", (ev1['id'],)
    ).fetchall())
    items2 = set(r['item_id'] for r in conn.execute(
        "SELECT item_id FROM event_inventory WHERE event_id=?", (ev2['id'],)
    ).fetchall())
    common_items = items1 & items2
    if len(common_items) >= 2:
        reasons.append(f'يستخدمان {len(common_items)} قطعة مخزون مشتركة')

    return reasons if reasons else None
