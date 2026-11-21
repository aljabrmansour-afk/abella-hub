"""
نقاط API للتعليقات والموافقات والمتابعة اللحظية
يُستدعى من server.py
"""

def get_routes(handler, conn, path, query, get_body_json, get_user_id, send_json, rows_to_list, row_to_dict):
    """نقاط GET الإضافية - يُرجع True إذا تم التعامل"""
    import re

    # ===== التعليقات على كيان معين =====
    if path == '/api/comments':
        entity_type = query.get('entity_type', [None])[0]
        entity_id = query.get('entity_id', [None])[0]
        if not entity_type or not entity_id:
            send_json({'error':'يلزم entity_type و entity_id'}, 400)
            return True
        rows = conn.execute("""SELECT c.*, u.full_name as user_name, u.role as user_role
                              FROM comments c JOIN users u ON c.user_id=u.id
                              WHERE c.entity_type=? AND c.entity_id=? ORDER BY c.created_at DESC""",
                           (entity_type, int(entity_id))).fetchall()
        send_json(rows_to_list(rows))
        return True

    # ===== الموافقة على كيان =====
    if path == '/api/approval':
        entity_type = query.get('entity_type', [None])[0]
        entity_id = query.get('entity_id', [None])[0]
        if not entity_type or not entity_id:
            send_json({}, 200)
            return True
        row = conn.execute("""SELECT a.*, u.full_name as decider_name FROM approvals a
                             LEFT JOIN users u ON a.decided_by=u.id
                             WHERE a.entity_type=? AND a.entity_id=?""",
                          (entity_type, int(entity_id))).fetchone()
        send_json(row_to_dict(row) if row else {'decision':'pending'})
        return True

    # ===== الداش بورد اللحظي للمالكة =====
    if path == '/api/owner/live':
        today = conn.execute("SELECT date('now','+3 hours') as d").fetchone()['d']
        live = {
            'timestamp': conn.execute("SELECT datetime('now') as t").fetchone()['t'],
            'today_events': rows_to_list(conn.execute("""
                SELECT e.*, c.full_name as customer_name
                FROM events e JOIN customers c ON e.customer_id=c.id
                WHERE date(COALESCE(e.actual_date,e.event_date))=? AND e.status<>'cancelled' ORDER BY e.event_start_time""", (today,)).fetchall()),
            'tomorrow_events': rows_to_list(conn.execute("""
                SELECT e.*, c.full_name as customer_name
                FROM events e JOIN customers c ON e.customer_id=c.id
                WHERE date(COALESCE(e.actual_date,e.event_date))=date('now','+3 hours','+1 day') AND e.status<>'cancelled'""").fetchall()),
            'active_workplans': rows_to_list(conn.execute("""
                SELECT wp.*, e.title as event_title, e.event_date,
                       u.full_name as planner_name,
                       (SELECT COUNT(*) FROM work_plan_items WHERE plan_id=wp.id) as items_count
                FROM work_plans wp JOIN events e ON wp.event_id=e.id LEFT JOIN users u ON wp.designer_id=u.id
                WHERE wp.status IN ('draft','approved') ORDER BY e.event_date""").fetchall()),
            'active_checklists': rows_to_list(conn.execute("""
                SELECT cl.*, wp.title as plan_title, e.title as event_title, e.event_date,
                       (SELECT COUNT(*) FROM warehouse_checklist_items WHERE checklist_id=cl.id) total,
                       (SELECT COUNT(*) FROM warehouse_checklist_items WHERE checklist_id=cl.id AND is_picked=1) done
                FROM warehouse_checklists cl
                JOIN work_plans wp ON cl.plan_id=wp.id
                JOIN events e ON cl.event_id=e.id
                WHERE cl.status IN ('pending','in_progress','ready') ORDER BY e.event_date""").fetchall()),
            'pending_approvals': rows_to_list(conn.execute("""
                SELECT wp.id as entity_id, 'workplan' as entity_type, wp.title, wp.plan_code,
                       e.title as event_title, e.event_date, u.full_name as planner_name,
                       wp.created_at
                FROM work_plans wp
                JOIN events e ON wp.event_id=e.id
                LEFT JOIN users u ON wp.designer_id=u.id
                LEFT JOIN approvals a ON a.entity_type='workplan' AND a.entity_id=wp.id
                WHERE wp.status='draft' AND (a.decision IS NULL OR a.decision='pending')
                ORDER BY wp.created_at DESC""").fetchall()),
            'recent_activity': rows_to_list(conn.execute("""
                SELECT 'task_completed' as type, t.title as text, t.completed_at as time,
                       u.full_name as user_name, e.title as context
                FROM event_tasks t LEFT JOIN users u ON t.completed_by=u.id
                JOIN events e ON t.event_id=e.id
                WHERE t.completed_at IS NOT NULL
                UNION ALL
                SELECT 'item_picked' as type, ('تم تجهيز عنصر') as text, cli.picked_at as time,
                       u.full_name as user_name, e.title as context
                FROM warehouse_checklist_items cli
                LEFT JOIN users u ON cli.picked_by=u.id
                JOIN warehouse_checklists wc ON cli.checklist_id=wc.id
                JOIN events e ON wc.event_id=e.id
                WHERE cli.picked_at IS NOT NULL
                UNION ALL
                SELECT 'payment' as type, ('استلام دفعة: ' || amount || ' ر.س') as text,
                       payment_date as time, u.full_name as user_name, e.title as context
                FROM event_payments p JOIN events e ON p.event_id=e.id
                LEFT JOIN users u ON p.received_by=u.id
                ORDER BY time DESC LIMIT 20""").fetchall()),
            'unread_owner_notes': conn.execute("SELECT COUNT(*) c FROM comments WHERE is_owner_note=1 AND is_read=0").fetchone()['c'],
            'totals': {
                'total_events': conn.execute("SELECT COUNT(*) c FROM events").fetchone()['c'],
                'active_events': conn.execute("SELECT COUNT(*) c FROM events WHERE status IN ('contracted','planning','ready','in_progress')").fetchone()['c'],
                'today_revenue': conn.execute("SELECT COALESCE(SUM(amount),0) v FROM event_payments WHERE date(payment_date)=date('now')").fetchone()['v'],
                'this_month_revenue': conn.execute("SELECT COALESCE(SUM(amount),0) v FROM event_payments WHERE strftime('%Y-%m', payment_date)=strftime('%Y-%m','now')").fetchone()['v'],
                'pending_payments': conn.execute("SELECT COALESCE(SUM(total_price-paid_amount),0) v FROM events WHERE status NOT IN ('lead','quoted','cancelled')").fetchone()['v'],
                'total_workplans': conn.execute("SELECT COUNT(*) c FROM work_plans").fetchone()['c'],
                'pending_workplans': conn.execute("SELECT COUNT(*) c FROM work_plans WHERE status='draft'").fetchone()['c'],
            }
        }
        send_json(live)
        return True

    return False


def post_routes(handler, conn, path, data, get_user_id, send_json):
    """نقاط POST الإضافية - يُرجع True إذا تم التعامل"""

    # ===== إضافة تعليق =====
    if path == '/api/comments':
        uid = get_user_id() or 11  # نوف الافتراضية
        user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        is_owner = 1 if (user and user['role']=='admin' and uid==11) else 0
        cur = conn.execute("""INSERT INTO comments
                             (entity_type, entity_id, user_id, comment_text, is_owner_note, target_team)
                             VALUES (?, ?, ?, ?, ?, ?)""",
                          (data.get('entity_type'), data.get('entity_id'), uid,
                           data.get('comment_text'), is_owner, data.get('target_team')))
        conn.commit()
        send_json({'id': cur.lastrowid, 'success': True})
        return True

    # ===== تأشير تعليق كمقروء =====
    if path == '/api/comments/mark-read':
        cid = data.get('comment_id')
        if cid:
            conn.execute("UPDATE comments SET is_read=1 WHERE id=?", (cid,))
        elif data.get('entity_type') and data.get('entity_id'):
            conn.execute("UPDATE comments SET is_read=1 WHERE entity_type=? AND entity_id=?",
                        (data['entity_type'], data['entity_id']))
        conn.commit()
        send_json({'success': True})
        return True

    # ===== الموافقة/الرفض =====
    if path == '/api/approve':
        uid = get_user_id() or 11
        entity_type = data.get('entity_type')
        entity_id = data.get('entity_id')
        decision = data.get('decision')  # approved/rejected
        notes = data.get('notes')
        # upsert approval
        existing = conn.execute("SELECT id FROM approvals WHERE entity_type=? AND entity_id=?",
                              (entity_type, entity_id)).fetchone()
        if existing:
            conn.execute("""UPDATE approvals SET decision=?, decided_by=?, decision_notes=?, decided_at=CURRENT_TIMESTAMP
                           WHERE id=?""", (decision, uid, notes, existing['id']))
        else:
            conn.execute("""INSERT INTO approvals (entity_type, entity_id, decision, decided_by, decision_notes, decided_at)
                           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                        (entity_type, entity_id, decision, uid, notes))
        # تحديث حالة الكيان لو خطة عمل
        if entity_type == 'workplan' and decision == 'approved':
            conn.execute("UPDATE work_plans SET status='approved', approved_by=?, approved_at=CURRENT_TIMESTAMP WHERE id=?",
                        (uid, entity_id))
            # توليد التشيك ليست تلقائيًا
            plan = conn.execute("SELECT * FROM work_plans WHERE id=?", (entity_id,)).fetchone()
            if plan:
                warehouses = conn.execute("SELECT DISTINCT warehouse FROM work_plan_items WHERE plan_id=?",
                                         (entity_id,)).fetchall()
                for wh in warehouses:
                    cur = conn.execute("""INSERT INTO warehouse_checklists (plan_id, event_id, warehouse, status)
                                         VALUES (?, ?, ?, 'pending')""",
                                      (entity_id, plan['event_id'], wh['warehouse']))
                    cl_id = cur.lastrowid
                    items = conn.execute("SELECT id FROM work_plan_items WHERE plan_id=? AND warehouse=?",
                                        (entity_id, wh['warehouse'])).fetchall()
                    for it in items:
                        conn.execute("INSERT INTO warehouse_checklist_items (checklist_id, plan_item_id) VALUES (?, ?)",
                                    (cl_id, it['id']))
        conn.commit()
        send_json({'success': True, 'decision': decision})
        return True

    return False
