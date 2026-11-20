"""
نظام الصلاحيات (RBAC) لنظام أبيلا
==================================
يحدد ما يستطيع كل دور رؤيته وتعديله.
"""

# ============================================================
# تعريف الصلاحيات لكل دور
# ============================================================

# الأدوار التي لها صلاحيات مطلقة (ترى كل شي وتعدّل كل شي)
SUPER_ROLES = {'owner', 'general_manager', 'admin'}

# الصلاحيات لكل دور
PERMISSIONS = {
    'owner': {  # نوف
        'menu': '*',  # كل القوائم
        'view': '*',  # ترى كل شي
        'edit': '*',  # تعدّل كل شي
        'approve': True,
        'reject': True,
        'manage_users': True,
        'view_finance': True,
        'view_all_events': True,
    },
    'general_manager': {  # منصور
        'menu': '*', 'view': '*', 'edit': '*',
        'approve': True, 'reject': True,
        'manage_users': True, 'view_finance': True,
        'view_all_events': True,
    },
    'admin': {  # المدير التقني
        'menu': '*', 'view': '*', 'edit': '*',
        'approve': True, 'reject': True,
        'manage_users': True, 'view_finance': True,
        'view_all_events': True,
    },
    'project_manager': {  # مدير المشروع
        'menu': ['dashboard','events','work_plans','checklists','appointments','my_tasks','calendar'],
        'view': ['events','work_plans','checklists','tasks','customers','appointments'],
        'edit': ['tasks','checklists','work_plan_status'],
        'create_tasks': True,
        'create_checklists': True,
        'set_timeline': True,
    },
    'designer': {  # المصمم
        'menu': ['dashboard','events','work_plans','inventory','my_tasks'],
        'view': ['events','work_plans','inventory','customers'],
        'edit': ['work_plans','work_plan_items'],
        'create_work_plans': True,
        'select_inventory': True,
    },
    'inventory_manager': {  # مسؤول المخزون
        'menu': ['dashboard','inventory','raw_materials','my_tasks'],
        'view': ['inventory','raw_materials','movements'],
        'edit': ['inventory','raw_materials','item_images'],
        'add_inventory': True,
        'count_inventory': True,  # جرد
    },
    'supervisor': {  # ميهاف، شريفة
        'menu': ['dashboard','events','my_events','work_plans','my_tasks','calendar'],
        'view': ['events','work_plans','checklists','customers','tasks'],
        'edit': ['event_status','tasks','checklists','expenses'],
        'can_record_expenses': ['supervision'],  # شريفة + ميهاف
    },
    'field': {  # معاذ، فارس
        'menu': ['dashboard','my_events','my_tasks','checklists','inventory'],
        'view': ['my_events','tasks','my_inventory'],
        'edit': ['tasks','checkout_inventory','photos','expenses'],
        'can_record_expenses': ['execution','purchases'],  # حسب المستخدم
    },
    'warehouse_decor': {  # فهيم
        'menu': ['dashboard','inventory','checklists','my_tasks'],
        'view': ['inventory_decorations','checklists_decorations'],
        'edit': ['inventory_decorations','checklist_items','photos'],
        'inventory_filter': 'decorations',
    },
    'warehouse_acc': {  # داريل، روز (إنجليزي)
        'menu': ['dashboard','inventory','checklists','my_tasks'],
        'view': ['inventory_accessories','checklists_accessories'],
        'edit': ['inventory_accessories','checklist_items','photos'],
        'inventory_filter': 'accessories',
    },
    'warehouse': {  # عام
        'menu': ['dashboard','inventory','checklists','my_tasks'],
        'view': ['inventory','checklists'],
        'edit': ['inventory','checklist_items','photos'],
    },
    'factory': {  # عمران (أوردو)
        'menu': ['dashboard','raw_materials','work_plans_factory','my_tasks','checklists'],
        'view': ['raw_materials','work_plans_factory','factory_orders'],
        'edit': ['factory_orders','raw_materials','photos'],
        'inventory_filter': 'factory_raw',
    },
    'hospitality': {  # رغد
        'menu': ['dashboard','my_events','hospitality_plans','my_tasks'],
        'view': ['my_events','hospitality_plans'],
        'edit': ['hospitality_tasks','photos'],
    },
    'customer_service': {  # رهف
        'menu': ['dashboard','customers','events','appointments','calendar'],
        'view': ['customers','events','appointments','contracts'],
        'edit': ['customers','contracts','appointments'],
        'create_appointments': True,
    },
    'finance': {  # بدرالدين
        'menu': ['dashboard','events','finance','reports','sync'],
        'view': ['events','payments','invoices','profitability'],
        'edit': ['payments','invoices'],
        'view_finance': True,
        'view_all_events': True,
    },
    'purchasing': {  # عبدالقيوم
        'menu': ['dashboard','purchases','raw_materials','sync'],
        'view': ['purchases','raw_materials','suppliers'],
        'edit': ['purchases','raw_materials','suppliers'],
    },
    'planner': {  # توافق مع القديم - يكافئ project_manager
        'menu': ['dashboard','events','work_plans','my_tasks'],
        'view': ['events','work_plans'],
        'edit': ['work_plans','tasks'],
    },
}

# ============================================================
# الدوال المساعدة
# ============================================================

def is_super(role):
    """هل الدور له صلاحية مطلقة؟"""
    return role in SUPER_ROLES

def can_view(role, resource):
    """هل يستطيع هذا الدور رؤية المورد؟"""
    if is_super(role):
        return True
    perm = PERMISSIONS.get(role, {})
    view = perm.get('view', [])
    if view == '*':
        return True
    return resource in view

def can_edit(role, resource):
    """هل يستطيع هذا الدور تعديل المورد؟"""
    if is_super(role):
        return True
    perm = PERMISSIONS.get(role, {})
    edit = perm.get('edit', [])
    if edit == '*':
        return True
    return resource in edit

def can_approve(role):
    """هل يستطيع الاعتماد/الرفض؟"""
    return PERMISSIONS.get(role, {}).get('approve', False)

def get_menu_items(role):
    """قائمة عناصر الشريط الجانبي لهذا الدور"""
    perm = PERMISSIONS.get(role, {})
    menu = perm.get('menu', [])
    if menu == '*':
        return ['dashboard','events','customers','inventory','raw_materials',
                'work_plans','checklists','appointments','calendar',
                'teams','finance','reports','sync','users']
    return menu

def get_inventory_filter(role):
    """فلتر المخزون التلقائي حسب الدور"""
    return PERMISSIONS.get(role, {}).get('inventory_filter')

def can_record_expense_type(role, expense_type, can_record_setting=None):
    """
    هل يستطيع هذا المستخدم تسجيل مصاريف من نوع معين؟
    (مثلاً معاذ يسجل execution، فارس purchases، شريفة supervision)
    """
    if is_super(role):
        return True
    # نتحقق من إعداد المستخدم نفسه لأن معاذ وفارس كلاهما 'field'
    if can_record_setting:
        types = [t.strip() for t in can_record_setting.split(',')]
        return expense_type in types
    perm = PERMISSIONS.get(role, {})
    allowed = perm.get('can_record_expenses', [])
    return expense_type in allowed

def filter_events_for_user(role, user_id, all_events_query, conn):
    """
    فلتر المناسبات حسب الدور:
    - super: كل المناسبات
    - field: المناسبات المُكلف بها فقط
    - hospitality: المُكلف بها فقط
    - باقي الأدوار: حسب القاعدة
    """
    if is_super(role) or PERMISSIONS.get(role, {}).get('view_all_events'):
        return all_events_query
    # فلتر للمكلفين فقط
    if role in ('field', 'hospitality', 'warehouse_decor', 'warehouse_acc', 'warehouse', 'factory'):
        return f"""SELECT * FROM ({all_events_query}) WHERE id IN (
            SELECT DISTINCT event_id FROM event_assignments WHERE user_id={user_id}
        )"""
    return all_events_query
