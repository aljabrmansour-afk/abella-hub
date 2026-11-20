import os
"""
نقاط API الجديدة (الدفعة الأولى من إعادة البناء)
================================================
- /api/i18n/<lang>           - الترجمات
- /api/permissions/me        - صلاحيات المستخدم الحالي
- /api/menu                  - قائمة الشريط الجانبي حسب الدور
- /api/raw-materials         - المواد الخام
- /api/appointments          - المواعيد
- /api/calendar              - التقويم البصري
- /api/photo-documents       - التوثيق الصوري
- /api/sub-plans             - الخطط الفرعية الست
- /api/risk-assessments      - إدارة المخاطر
- /api/code-generator        - توليد الأكواد
- /api/maintenance/cleanup-photos - الصيانة الدورية
"""

import json
from pathlib import Path

# سيتم الاستيراد عند التشغيل
permissions = None
code_generator = None
photo_cleanup = None
I18N_DATA = None


def _lazy_init(base_dir):
    """تحميل التبعيات والترجمات عند الحاجة"""
    global permissions, code_generator, photo_cleanup, I18N_DATA
    if permissions is None:
        try:
            import permissions as _perm
            permissions = _perm
        except ImportError:
            pass
    if code_generator is None:
        try:
            import code_generator as _cg
            code_generator = _cg
        except ImportError:
            pass
    if photo_cleanup is None:
        try:
            import photo_cleanup as _pc
            photo_cleanup = _pc
        except ImportError:
            pass
    if I18N_DATA is None:
        i18n_path = Path(base_dir) / 'assets' / 'i18n.json'
        if i18n_path.exists():
            with open(i18n_path, 'r', encoding='utf-8') as f:
                I18N_DATA = json.load(f)


def get_routes(handler, conn, path, query, get_user_id, send_json, rows_to_list, row_to_dict, base_dir):
    """نقاط GET الجديدة"""
    import re
    _lazy_init(base_dir)

    # ===== الترجمات =====
    m = re.match(r'^/api/i18n/(ar|en|ur)$', path)
    if m:
        lang = m.group(1)
        if I18N_DATA and lang in I18N_DATA:
            return send_json(I18N_DATA[lang]), True
        return send_json({'error': 'lang not found'}, 404), True

    # ===== صلاحياتي =====
    if path == '/api/permissions/me':
        uid = get_user_id() or 1
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return send_json({'error': 'unauthenticated'}, 401), True
        role = user['role']
        if permissions:
            send_json({
                'user': {
                    'id': user['id'], 'username': user['username'],
                    'full_name': user['full_name'], 'role': role,
                    'language': user['language'] or 'ar',
                    'can_record_expenses': user['can_record_expenses'],
                },
                'is_super': permissions.is_super(role),
                'can_approve': permissions.can_approve(role),
                'menu': permissions.get_menu_items(role),
                'inventory_filter': permissions.get_inventory_filter(role),
            })
            return True
        return send_json({'role': role}), True

    # ===== قائمة الشريط الجانبي =====
    if path == '/api/menu':
        uid = get_user_id() or 1
        user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        role = user['role'] if user else 'admin'
        if permissions:
            send_json({'role': role, 'menu': permissions.get_menu_items(role)})
            return True
        return send_json({'menu': []}), True

    # ===== المواد الخام =====
    if path == '/api/raw-materials':
        material_type = query.get('type', [None])[0]
        sql = "SELECT * FROM raw_materials WHERE 1=1"
        params = []
        if material_type:
            sql += " AND material_type=?"
            params.append(material_type)
        sql += " ORDER BY name"
        send_json(rows_to_list(conn.execute(sql, params).fetchall()))
        return True

    m = re.match(r'^/api/raw-materials/(\d+)$', path)
    if m:
        mid = int(m.group(1))
        item = conn.execute("SELECT * FROM raw_materials WHERE id=?", (mid,)).fetchone()
        if not item:
            return send_json({'error': 'not found'}, 404), True
        d = row_to_dict(item)
        d['movements'] = rows_to_list(conn.execute(
            """SELECT m.*, u.full_name as user_name
               FROM raw_material_movements m
               LEFT JOIN users u ON m.user_id=u.id
               WHERE m.material_id=? ORDER BY m.movement_date DESC LIMIT 50""",
            (mid,)
        ).fetchall())
        send_json(d)
        return True

    # ===== المواعيد =====
    if path == '/api/appointments':
        date_from = query.get('from', [None])[0]
        date_to = query.get('to', [None])[0]
        sql = """SELECT a.*, u.full_name as assigned_name, c.full_name as customer_full_name
                 FROM appointments a
                 LEFT JOIN users u ON a.assigned_to=u.id
                 LEFT JOIN customers c ON a.customer_id=c.id WHERE 1=1"""
        params = []
        if date_from:
            sql += " AND a.appointment_date >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND a.appointment_date <= ?"
            params.append(date_to)
        sql += " ORDER BY a.appointment_date, a.start_time"
        send_json(rows_to_list(conn.execute(sql, params).fetchall()))
        return True

    # ===== التقويم البصري =====
    if path == '/api/calendar':
        year = int(query.get('year', [2026])[0])
        month = int(query.get('month', [5])[0])
        period = f"{year:04d}-{month:02d}"

        appts = rows_to_list(conn.execute(
            """SELECT id, title, appointment_date as date, start_time as time,
                      appointment_type as type, color_label, status,
                      'appointment' as item_type
               FROM appointments
               WHERE strftime('%Y-%m', appointment_date) = ?""",
            (period,)
        ).fetchall())

        # نستخدم actual_date إن وُجد، وإلا event_date (المتوقع)
        events = rows_to_list(conn.execute(
            """SELECT e.id, e.title, e.event_type, e.status,
                      COALESCE(e.actual_date, e.event_date) as date,
                      e.event_start_time as time,
                      e.event_type as type,
                      e.venue_name, e.venue_address as location,
                      c.full_name as customer_name,
                      'event' as item_type,
                      CASE WHEN e.actual_date IS NOT NULL AND e.actual_date != ''
                           THEN 'actual' ELSE 'expected' END as date_kind
               FROM events e JOIN customers c ON e.customer_id=c.id
               WHERE strftime('%Y-%m', COALESCE(e.actual_date, e.event_date)) = ?""",
            (period,)
        ).fetchall())

        send_json({
            'year': year, 'month': month,
            'appointments': appts, 'events': events,
            'all_items': appts + events,
        })
        return True

    # ===== التوثيق الصوري =====
    if path == '/api/photo-documents':
        event_id = query.get('event_id', [None])[0]
        phase = query.get('phase', [None])[0]
        sql = """SELECT pd.*, u.full_name as taken_by_name
                 FROM photo_documents pd
                 LEFT JOIN users u ON pd.taken_by=u.id
                 WHERE pd.deleted_at IS NULL"""
        params = []
        if event_id:
            sql += " AND pd.event_id=?"
            params.append(event_id)
        if phase:
            sql += " AND pd.photo_phase=?"
            params.append(phase)
        sql += " ORDER BY pd.taken_at DESC"
        send_json(rows_to_list(conn.execute(sql, params).fetchall()))
        return True

    # ===== الخطط الفرعية =====
    if path == '/api/sub-plans':
        event_id = query.get('event_id', [None])[0]
        plan_type = query.get('type', [None])[0]
        sql = """SELECT sp.*, e.title as event_title, e.event_date,
                        u.full_name as assigned_name,
                        (SELECT COUNT(*) FROM sub_plan_items WHERE sub_plan_id=sp.id) as total_items,
                        (SELECT COUNT(*) FROM sub_plan_items WHERE sub_plan_id=sp.id AND is_done=1) as done_items
                 FROM sub_plans sp
                 LEFT JOIN events e ON sp.event_id=e.id
                 LEFT JOIN users u ON sp.assigned_to=u.id WHERE 1=1"""
        params = []
        if event_id:
            sql += " AND sp.event_id=?"
            params.append(event_id)
        if plan_type:
            sql += " AND sp.plan_type=?"
            params.append(plan_type)
        sql += " ORDER BY e.event_date, sp.plan_type"
        send_json(rows_to_list(conn.execute(sql, params).fetchall()))
        return True

    m = re.match(r'^/api/sub-plans/(\d+)$', path)
    if m:
        spid = int(m.group(1))
        sp = conn.execute(
            """SELECT sp.*, e.title as event_title, e.event_date, e.venue_name,
                      c.full_name as customer_name, u.full_name as assigned_name
               FROM sub_plans sp JOIN events e ON sp.event_id=e.id
               JOIN customers c ON e.customer_id=c.id
               LEFT JOIN users u ON sp.assigned_to=u.id
               WHERE sp.id=?""", (spid,)
        ).fetchone()
        if not sp:
            return send_json({'error': 'not found'}, 404), True
        d = row_to_dict(sp)

        # تحديد لغة المستخدم — أولوية ?lang=xx ثم لغة المستخدم في DB ثم 'ar'
        lang = (query.get('lang', [None])[0] or '').lower()
        if lang not in ('ar', 'en', 'ur'):
            uid = get_user_id()
            if uid:
                u = conn.execute("SELECT language FROM users WHERE id=?", (uid,)).fetchone()
                lang = u['language'] if u and u['language'] in ('ar','en','ur') else 'ar'
            else:
                lang = 'ar'

        # نختار العمود المناسب للغة، ولو الترجمة فاضية نرجع للعربي (fallback)
        name_col = {
            'ar': 'wpi.custom_name',
            'en': 'COALESCE(NULLIF(wpi.custom_name_en, ""), wpi.custom_name)',
            'ur': 'COALESCE(NULLIF(wpi.custom_name_ur, ""), wpi.custom_name)',
        }[lang]
        notes_col = {
            'ar': 'wpi.notes',
            'en': 'COALESCE(NULLIF(wpi.notes_en, ""), wpi.notes)',
            'ur': 'COALESCE(NULLIF(wpi.notes_ur, ""), wpi.notes)',
        }[lang]

        d['lang'] = lang
        d['items'] = rows_to_list(conn.execute(
            f"""SELECT spi.*, {name_col} as custom_name,
                      wpi.custom_name as custom_name_ar,
                      wpi.custom_name_en, wpi.custom_name_ur,
                      wpi.quantity, wpi.sample_image,
                      wpi.sticker_image, wpi.color_code, wpi.fabric_code,
                      wpi.dimensions, {notes_col} as item_notes, wpi.notes_red,
                      wpi.needs_refurb, cat.name as category_name, cat.icon as category_icon,
                      u.full_name as done_by_name
               FROM sub_plan_items spi
               LEFT JOIN work_plan_items wpi ON spi.work_plan_item_id=wpi.id
               LEFT JOIN inventory_categories cat ON wpi.category_id=cat.id
               LEFT JOIN users u ON spi.done_by=u.id
               WHERE spi.sub_plan_id=?""", (spid,)
        ).fetchall())
        send_json(d)
        return True

    # ===== المصاريف اليدوية =====
    if path == '/api/expenses':
        event_id = query.get('event_id', [None])[0]
        date_from = query.get('from', [None])[0]
        date_to = query.get('to', [None])[0]
        recorded_by = query.get('recorded_by', [None])[0]
        sql = """SELECT ex.*, e.title as event_title, e.event_code,
                        u1.full_name as recorded_by_name, u2.full_name as approved_by_name
                 FROM expenses ex
                 LEFT JOIN events e ON ex.event_id=e.id
                 LEFT JOIN users u1 ON ex.recorded_by=u1.id
                 LEFT JOIN users u2 ON ex.approved_by=u2.id WHERE 1=1"""
        params = []
        if event_id:
            sql += " AND ex.event_id=?"; params.append(event_id)
        if date_from:
            sql += " AND ex.expense_date >= ?"; params.append(date_from)
        if date_to:
            sql += " AND ex.expense_date <= ?"; params.append(date_to)
        if recorded_by:
            sql += " AND ex.recorded_by=?"; params.append(recorded_by)
        sql += " ORDER BY ex.expense_date DESC, ex.id DESC LIMIT 200"
        send_json(rows_to_list(conn.execute(sql, params).fetchall()))
        return True

    if path == '/api/expenses/summary':
        # ملخص للمالكة/المدير: إجمالي اليوم/الشهر/السنة + توزيع حسب الفئة
        today = conn.execute(
            "SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE expense_date=date('now')"
        ).fetchone()['v']
        month = conn.execute(
            "SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE strftime('%Y-%m', expense_date)=strftime('%Y-%m','now')"
        ).fetchone()['v']
        year = conn.execute(
            "SELECT COALESCE(SUM(amount),0) v FROM expenses WHERE strftime('%Y', expense_date)=strftime('%Y','now')"
        ).fetchone()['v']
        by_cat = rows_to_list(conn.execute(
            """SELECT expense_category, COUNT(*) c, COALESCE(SUM(amount),0) total
               FROM expenses WHERE strftime('%Y-%m', expense_date)=strftime('%Y-%m','now')
               GROUP BY expense_category ORDER BY total DESC"""
        ).fetchall())
        recent = rows_to_list(conn.execute(
            """SELECT ex.*, u.full_name as recorded_by_name
               FROM expenses ex LEFT JOIN users u ON ex.recorded_by=u.id
               ORDER BY ex.created_at DESC LIMIT 10"""
        ).fetchall())
        send_json({'today': today, 'month': month, 'year': year, 'by_category': by_cat, 'recent': recent})
        return True

    # ===== خطط إدارة المخاطر =====
    if path == '/api/risk-assessments':
        send_json(rows_to_list(conn.execute(
            """SELECT * FROM risk_assessments ORDER BY period_year DESC, period_month DESC"""
        ).fetchall()))
        return True

    m = re.match(r'^/api/risk-assessments/(\d+)$', path)
    if m:
        rid = int(m.group(1))
        ra = conn.execute("SELECT * FROM risk_assessments WHERE id=?", (rid,)).fetchone()
        if not ra:
            return send_json({'error': 'not found'}, 404), True
        d = row_to_dict(ra)
        d['items'] = rows_to_list(conn.execute(
            """SELECT rai.*, e1.title as event_title, c1.full_name as customer_name,
                      e2.title as similar_title, c2.full_name as similar_customer
               FROM risk_assessment_items rai
               JOIN events e1 ON rai.event_id=e1.id
               JOIN customers c1 ON e1.customer_id=c1.id
               LEFT JOIN events e2 ON rai.similar_event_id=e2.id
               LEFT JOIN customers c2 ON e2.customer_id=c2.id
               WHERE rai.assessment_id=?""", (rid,)
        ).fetchall())
        send_json(d)
        return True

    return False


def post_routes(handler, conn, path, data, get_user_id, send_json, base_dir):
    """نقاط POST الجديدة"""
    _lazy_init(base_dir)
    import re

    # ===== إضافة سريعة لعنصر مخزون من الموبايل (مع صورة + كود تلقائي) =====
    if path == '/api/inventory/quick-add':
        warehouse = data.get('warehouse', 'accessories')
        category_id = data.get('category_id')

        prefix_map = {
            'accessories': 'ACC', 'decorations': 'DEC',
            'factory': 'FAC', 'factory_raw': 'RAW',
        }
        prefix = prefix_map.get(warehouse, 'INV')
        row = conn.execute(
            "SELECT item_code FROM inventory_items WHERE item_code LIKE ? ORDER BY item_code DESC LIMIT 1",
            (f"{prefix}-%",)
        ).fetchone()
        if row:
            try: last_n = int(row['item_code'].split('-')[1])
            except: last_n = 0
        else:
            last_n = 0
        new_code = f"{prefix}-{last_n+1:04d}"

        # احفظ الصورة لو موجودة (base64)
        img_path = None
        img_data = data.get('image_base64')
        if img_data:
            import base64, time as _time, os as _os
            try:
                if ',' in img_data: img_data = img_data.split(',', 1)[1]
                img_bytes = base64.b64decode(img_data)
                fname = f"{new_code}_{int(_time.time())}.jpg"
                rel_dir = f"assets/inventory/{warehouse}"
                abs_dir = _os.path.join(base_dir, 'assets', 'inventory', warehouse)
                _os.makedirs(abs_dir, exist_ok=True)
                abs_path = _os.path.join(abs_dir, fname)
                with open(abs_path, 'wb') as f:
                    f.write(img_bytes)
                img_path = f"{rel_dir}/{fname}"
            except Exception:
                pass

        cur = conn.execute("""INSERT INTO inventory_items
            (item_code, name, name_en, name_ur, category_id, warehouse,
             main_image, quantity_total, quantity_available,
             condition, status, location_in_warehouse, branch, added_by, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'good', 'in_warehouse', ?, ?, ?, ?)""",
            (new_code, data.get('name'), data.get('name_en'), data.get('name_ur'),
             category_id, warehouse, img_path,
             int(data.get('quantity', 1)), int(data.get('quantity', 1)),
             data.get('shelf') or data.get('location'),
             data.get('branch', 'riyadh'),
             get_user_id() or 1,
             'أُضيف من الموبايل'))
        conn.commit()
        send_json({
            'id': cur.lastrowid, 'item_code': new_code,
            'image_path': img_path, 'success': True
        })
        return True

    # ===== إضافة مادة خام =====
    if path == '/api/raw-materials':
        if not code_generator:
            return send_json({'error': 'code_generator not loaded'}, 500), True
        code = code_generator.generate_raw_material_code(conn, data.get('material_type', 'other'))
        cur = conn.execute(
            """INSERT INTO raw_materials
               (material_code, name, material_type, brand, color_code, size_or_dimensions,
                unit, quantity, min_quantity, unit_cost, image_path, location, supplier, notes, added_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, data.get('name'), data.get('material_type'), data.get('brand'),
             data.get('color_code'), data.get('size_or_dimensions'),
             data.get('unit', 'piece'), data.get('quantity', 0), data.get('min_quantity', 1),
             data.get('unit_cost', 0), data.get('image_path'), data.get('location'),
             data.get('supplier'), data.get('notes'), get_user_id() or 1)
        )
        conn.commit()
        send_json({'id': cur.lastrowid, 'material_code': code, 'success': True})
        return True

    # ===== حركة مادة خام (دخول/خروج) =====
    if path == '/api/raw-materials/movement':
        material_id = data.get('material_id')
        movement_type = data.get('movement_type', 'in')  # in/out/adjustment/damage
        qty = float(data.get('quantity', 0))

        cur = conn.execute(
            """INSERT INTO raw_material_movements
               (material_id, movement_type, quantity, event_id, sub_plan_id, user_id, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (material_id, movement_type, qty, data.get('event_id'),
             data.get('sub_plan_id'), get_user_id() or 1, data.get('notes'))
        )

        # تحديث الكمية
        if movement_type == 'in':
            conn.execute("UPDATE raw_materials SET quantity=quantity+? WHERE id=?", (qty, material_id))
        elif movement_type in ('out', 'damage'):
            conn.execute("UPDATE raw_materials SET quantity=quantity-? WHERE id=?", (qty, material_id))
        elif movement_type == 'adjustment':
            conn.execute("UPDATE raw_materials SET quantity=? WHERE id=?", (qty, material_id))

        conn.commit()
        send_json({'id': cur.lastrowid, 'success': True})
        return True

    # ===== تسجيل مصروف يدوي (من الجوال) =====
    if path == '/api/expenses':
        uid = get_user_id() or 1
        # تحقق من الصلاحية
        u = conn.execute("SELECT can_record_expenses, role FROM users WHERE id=?", (uid,)).fetchone()
        if u and u['can_record_expenses'] is None and u['role'] not in (
            'admin','owner','general_manager','finance','project_manager','supervisor'):
            send_json({'error': 'لا تملك صلاحية تسجيل المصاريف'}, 403)
            return True
        # توليد كود EXP-YYYY-NNNN
        import datetime
        year = datetime.date.today().year
        cnt = conn.execute(
            "SELECT COUNT(*) c FROM expenses WHERE expense_code LIKE ?",
            (f"EXP-{year}-%",)
        ).fetchone()['c'] + 1
        code = f"EXP-{year}-{cnt:04d}"

        amount = float(data.get('amount', 0) or 0)
        if amount <= 0:
            send_json({'error': 'المبلغ مطلوب'}, 400)
            return True
        if not data.get('description'):
            send_json({'error': 'الوصف مطلوب'}, 400)
            return True
        if not data.get('expense_category'):
            send_json({'error': 'الفئة مطلوبة'}, 400)
            return True

        cur = conn.execute(
            """INSERT INTO expenses
               (expense_code, event_id, expense_category, description, amount,
                payment_method, receipt_photo, vendor_name, invoice_number,
                expense_date, notes, recorded_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, data.get('event_id'), data.get('expense_category'),
             data.get('description'), amount,
             data.get('payment_method', 'cash'),
             data.get('receipt_photo'), data.get('vendor_name'),
             data.get('invoice_number'),
             data.get('expense_date') or datetime.date.today().isoformat(),
             data.get('notes'), uid)
        )
        conn.commit()
        send_json({'id': cur.lastrowid, 'expense_code': code, 'success': True})
        return True

    # ===== ترجمة بند خطة عمل (للمشرف/المدير) =====
    if path == '/api/work-plan-items/translate':
        item_id = data.get('item_id')
        if not item_id:
            send_json({'error': 'item_id مطلوب'}, 400); return True
        fields, params = [], []
        for k in ('custom_name_en','custom_name_ur','notes_en','notes_ur'):
            if k in data:
                fields.append(f"{k}=?"); params.append(data[k])
        if not fields:
            send_json({'error': 'لا يوجد ما يُحدَّث'}, 400); return True
        params.append(item_id)
        conn.execute(f"UPDATE work_plan_items SET {', '.join(fields)} WHERE id=?", params)
        conn.commit()
        send_json({'success': True})
        return True

    # ===== إنشاء موعد =====
    if path == '/api/appointments':
        if not code_generator:
            return send_json({'error': 'code_generator not loaded'}, 500), True
        code = code_generator.generate_appointment_code(conn)
        cur = conn.execute(
            """INSERT INTO appointments
               (appointment_code, customer_id, customer_name, customer_phone,
                appointment_type, title, appointment_date, start_time, end_time,
                location, assigned_to, related_event_id, notes, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, data.get('customer_id'), data.get('customer_name'),
             data.get('customer_phone'), data.get('appointment_type'),
             data.get('title'), data.get('appointment_date'),
             data.get('start_time'), data.get('end_time'),
             data.get('location'), data.get('assigned_to'),
             data.get('related_event_id'), data.get('notes'),
             get_user_id() or 1)
        )
        conn.commit()
        send_json({'id': cur.lastrowid, 'appointment_code': code, 'success': True})
        return True

    # ===== إضافة صورة توثيقية =====
    if path == '/api/photo-documents':
        # نحسب موعد الانتهاء (شهر من الآن)
        import datetime
        expires = (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()

        cur = conn.execute(
            """INSERT INTO photo_documents
               (event_id, sub_plan_id, item_id, photo_path, photo_phase,
                caption, taken_by, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (data.get('event_id'), data.get('sub_plan_id'), data.get('item_id'),
             data.get('photo_path'), data.get('photo_phase'),
             data.get('caption'), get_user_id() or 1, expires)
        )
        conn.commit()
        send_json({'id': cur.lastrowid, 'success': True, 'expires_at': expires})
        return True

    # ===== أرشفة صورة (حماية من الحذف) =====
    if path == '/api/photo-documents/archive':
        photo_id = data.get('photo_id')
        if photo_cleanup:
            photo_cleanup.archive_photo(conn, photo_id)
        else:
            conn.execute("UPDATE photo_documents SET is_archived=1 WHERE id=?", (photo_id,))
            conn.commit()
        send_json({'success': True})
        return True

    # ===== توليد الخطط الفرعية الست =====
    if path == '/api/work-plans/generate-sub-plans':
        plan_id = data.get('plan_id')
        if not photo_cleanup:
            return send_json({'error': 'module not loaded'}, 500), True
        sub_plans = photo_cleanup.generate_sub_plans(conn, plan_id)
        send_json({
            'success': True,
            'generated_sub_plans': sub_plans,
            'count': len(sub_plans) if sub_plans else 0,
        })
        return True

    # ===== تحديد عنصر تشيك ليست كمنجز =====
    if path == '/api/sub-plans/items/done':
        item_id = data.get('item_id')
        conn.execute(
            """UPDATE sub_plan_items
               SET is_done=1, done_quantity=?, done_by=?, done_at=CURRENT_TIMESTAMP, photo_proof=?, notes=?
               WHERE id=?""",
            (data.get('done_quantity', 1), get_user_id() or 1,
             data.get('photo_proof'), data.get('notes'), item_id)
        )
        conn.commit()
        send_json({'success': True})
        return True

    # ===== كشف الديكورات المتشابهة (إنشاء خطة مخاطر) =====
    if path == '/api/risk-assessments/detect':
        year = int(data.get('year', 2026))
        month = int(data.get('month', 5))
        if photo_cleanup:
            result = photo_cleanup.detect_similar_decorations(conn, year, month)
            send_json({'success': True, 'result': result})
        else:
            send_json({'error': 'module not loaded'}, 500)
        return True

    # ===== الصيانة الدورية: حذف الصور القديمة =====
    if path == '/api/maintenance/cleanup-photos':
        retention = int(data.get('retention_days', 30))
        if photo_cleanup:
            uploads_dir = (Path(os.environ['DATA_DIR']) / 'uploads') if os.environ.get('DATA_DIR') else (Path(base_dir) / 'backend' / 'uploads')
            result = photo_cleanup.cleanup_old_photos(conn, str(uploads_dir), retention)
            send_json({'success': True, 'result': result})
        else:
            send_json({'error': 'module not loaded'}, 500)
        return True

    return False
