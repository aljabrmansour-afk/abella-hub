-- ============================================================
-- نظام أبيلا للمناسبات - مخطط قاعدة البيانات (الإصدار 3)
-- Abella Events Management - Database Schema v3
-- ============================================================

-- حذف الجداول القديمة بالترتيب الصحيح
DROP TABLE IF EXISTS photo_documents;
DROP TABLE IF EXISTS appointments;
DROP TABLE IF EXISTS sub_plan_items;
DROP TABLE IF EXISTS sub_plans;
DROP TABLE IF EXISTS risk_assessment_items;
DROP TABLE IF EXISTS risk_assessments;
DROP TABLE IF EXISTS raw_material_movements;
DROP TABLE IF EXISTS raw_materials;
DROP TABLE IF EXISTS approvals;
DROP TABLE IF EXISTS comments;
DROP TABLE IF EXISTS sync_log;
DROP TABLE IF EXISTS sheet_purchases;
DROP TABLE IF EXISTS sheet_expenses;
DROP TABLE IF EXISTS sheet_contracts;
DROP TABLE IF EXISTS warehouse_checklist_items;
DROP TABLE IF EXISTS warehouse_checklists;
DROP TABLE IF EXISTS work_plan_items;
DROP TABLE IF EXISTS work_plans;
DROP TABLE IF EXISTS event_assignments;
DROP TABLE IF EXISTS event_inventory;
DROP TABLE IF EXISTS event_tasks;
DROP TABLE IF EXISTS event_photos;
DROP TABLE IF EXISTS event_payments;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS inventory_movements;
DROP TABLE IF EXISTS item_images;
DROP TABLE IF EXISTS inventory_items;
DROP TABLE IF EXISTS inventory_categories;
DROP TABLE IF EXISTS team_members;
DROP TABLE IF EXISTS teams;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS audit_log;

-- ============================================================
-- 1. المستخدمون (مع اللغة والصلاحيات)
-- ============================================================
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT, email TEXT,
    role TEXT NOT NULL CHECK(role IN (
        'owner','general_manager','admin',
        'project_manager','designer','inventory_manager',
        'supervisor','field','warehouse','warehouse_decor','warehouse_acc',
        'customer_service','finance','factory','hospitality','planner','purchasing'
    )),
    language TEXT DEFAULT 'ar' CHECK(language IN ('ar','en','ur')),
    team_id INTEGER,
    can_record_expenses TEXT,                -- supervision/execution/purchases
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_login TEXT
);

-- ============================================================
-- 2. الفرق
-- ============================================================
CREATE TABLE teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    leader_id INTEGER,
    description TEXT,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role_in_team TEXT,
    UNIQUE(team_id, user_id)
);

-- ============================================================
-- 3. العملاء
-- ============================================================
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    alt_phone TEXT, email TEXT,
    customer_type TEXT DEFAULT 'individual' CHECK(customer_type IN ('individual','company','vip')),
    city TEXT, address TEXT,
    notes TEXT, preferences TEXT,
    total_events INTEGER DEFAULT 0,
    total_spent REAL DEFAULT 0,
    rating INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_customers_phone ON customers(phone);

-- ============================================================
-- 4. المناسبات (3 أنواع: B/W/E)
-- ============================================================
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_code TEXT UNIQUE NOT NULL,
    operation_order TEXT,                    -- O1001, O1002...
    contract_code TEXT,                      -- B/W/E + رقم
    customer_id INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('newborn','special','exhibition')),
    title TEXT NOT NULL,
    description TEXT,
    event_date TEXT NOT NULL,
    event_start_time TEXT, event_end_time TEXT,
    venue_name TEXT, venue_address TEXT,
    venue_lat REAL, venue_lng REAL,
    guests_count INTEGER,
    theme TEXT, color_palette TEXT,
    status TEXT NOT NULL DEFAULT 'lead',
    total_price REAL DEFAULT 0,
    paid_amount REAL DEFAULT 0,
    insurance_amount REAL DEFAULT 0,
    insurance_returned REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    cost_total REAL DEFAULT 0,
    profit REAL DEFAULT 0,
    coordinator_id INTEGER,                  -- المنسقة (ميهاف/شريفة)
    project_manager_id INTEGER,              -- مدير المشروع
    designer_id INTEGER,                     -- المصمم
    created_by INTEGER NOT NULL,
    sync_source TEXT DEFAULT 'system',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
CREATE INDEX idx_events_op ON events(operation_order);
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_events_date ON events(event_date);

-- ============================================================
-- 5. تصنيفات المخزون
-- ============================================================
CREATE TABLE inventory_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_en TEXT, name_ur TEXT,
    warehouse TEXT CHECK(warehouse IN ('decorations','accessories','factory','factory_raw')),
    icon TEXT,
    needs_color INTEGER DEFAULT 0,
    needs_fabric INTEGER DEFAULT 0,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
);

-- ============================================================
-- 6. عناصر المخزون (الديكورات والاكسسوارات)
-- ============================================================
CREATE TABLE inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    name_en TEXT, name_ur TEXT,
    description TEXT,
    category_id INTEGER,
    warehouse TEXT CHECK(warehouse IN ('decorations','accessories','factory','factory_raw')),
    sticker_image TEXT,
    main_image TEXT,
    color_code TEXT,
    fabric_code TEXT,
    unit_cost REAL DEFAULT 0,
    rental_price REAL DEFAULT 0,
    quantity_total INTEGER DEFAULT 1,
    quantity_available INTEGER DEFAULT 1,
    condition TEXT DEFAULT 'excellent' CHECK(condition IN ('excellent','good','fair','damaged','lost','needs_refurb')),
    status TEXT DEFAULT 'in_warehouse' CHECK(status IN ('in_warehouse','reserved','in_event','in_repair','retired','lost')),
    location_in_warehouse TEXT,
    notes TEXT,
    times_used INTEGER DEFAULT 0,
    last_used_date TEXT,
    added_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES inventory_categories(id)
);
CREATE INDEX idx_inventory_warehouse ON inventory_items(warehouse);
CREATE INDEX idx_inventory_category ON inventory_items(category_id);

-- ============================================================
-- 7. المواد الخام (مخزون المصنع: بويات، أخشاب، مسامير...)
-- ============================================================
CREATE TABLE raw_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    material_type TEXT NOT NULL CHECK(material_type IN (
        'paint','wood','nail','wire','fabric','flower_artificial',
        'metal','acrylic','adhesive','tool','consumable','other'
    )),
    brand TEXT,                              -- جوتن، دهانات الجزيرة، هافانا، لينوفر...
    color_code TEXT,                         -- 8109، 0125، RAL8003
    size_or_dimensions TEXT,                 -- 10كجم، 145سم، إلخ
    unit TEXT DEFAULT 'piece' CHECK(unit IN ('piece','meter','kg','liter','box','roll','pack')),
    quantity REAL DEFAULT 0,
    min_quantity REAL DEFAULT 1,             -- تنبيه عند النقص
    unit_cost REAL DEFAULT 0,
    image_path TEXT,
    location TEXT,
    supplier TEXT,
    notes TEXT,
    last_purchase_date TEXT,
    added_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_raw_type ON raw_materials(material_type);

CREATE TABLE raw_material_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL,
    movement_type TEXT NOT NULL CHECK(movement_type IN ('in','out','adjustment','damage')),
    quantity REAL NOT NULL,
    event_id INTEGER,
    sub_plan_id INTEGER,
    user_id INTEGER NOT NULL,
    notes TEXT,
    movement_date TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (material_id) REFERENCES raw_materials(id)
);

-- ============================================================
-- 8. صور إضافية لعناصر المخزون
-- ============================================================
CREATE TABLE item_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    caption TEXT,
    is_main INTEGER DEFAULT 0,
    uploaded_by INTEGER,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES inventory_items(id) ON DELETE CASCADE
);

-- ============================================================
-- 9. حركات المخزون
-- ============================================================
CREATE TABLE inventory_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    event_id INTEGER,
    movement_type TEXT NOT NULL,
    quantity INTEGER DEFAULT 1,
    from_location TEXT, to_location TEXT,
    condition_before TEXT, condition_after TEXT,
    user_id INTEGER NOT NULL,
    notes TEXT, photo_path TEXT,
    movement_date TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 10. خطط العمل الرئيسية
-- ============================================================
CREATE TABLE work_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_code TEXT UNIQUE NOT NULL,
    event_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    designer_id INTEGER NOT NULL,
    designer_notes TEXT,
    status TEXT DEFAULT 'draft' CHECK(status IN ('draft','submitted','approved','rejected','executing','completed','closed')),
    approved_by INTEGER,
    approved_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events(id)
);

-- بنود الخطة الأساسية (مع كل التفاصيل من الـ PDF)
CREATE TABLE work_plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    target_warehouse TEXT NOT NULL CHECK(target_warehouse IN (
        'decorations','accessories','factory','hospitality','purchasing','risk'
    )),
    category_id INTEGER,
    item_id INTEGER,                         -- لو من المخزون
    custom_name TEXT,                        -- اسم مخصص (عربي - الافتراضي)
    custom_name_en TEXT,                     -- ترجمة إنجليزية (لمستودع الإكسسوارات)
    custom_name_ur TEXT,                     -- ترجمة أوردو (للمصنع)
    notes_en TEXT,                           -- ملاحظات بالإنجليزي
    notes_ur TEXT,                           -- ملاحظات بالأوردو
    quantity TEXT,                           -- "ALL", "10", "1"...
    sample_image TEXT,
    sticker_image TEXT,
    name_image TEXT,
    color_code TEXT,
    fabric_code TEXT,
    dimensions TEXT,                         -- "ارتفاع 1.30م، عمق 60"
    needs_refurb INTEGER DEFAULT 0,          -- يحتاج إعادة تدوير
    refurb_notes TEXT,
    notes TEXT,
    notes_red TEXT,                          -- النص الأحمر للتنبيهات
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (plan_id) REFERENCES work_plans(id) ON DELETE CASCADE
);
CREATE INDEX idx_wpi_plan ON work_plan_items(plan_id);
CREATE INDEX idx_wpi_target ON work_plan_items(target_warehouse);

-- ============================================================
-- 11. الخطط الفرعية الـ6 (تتولد تلقائيًا)
-- ============================================================
CREATE TABLE sub_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_plan_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    plan_type TEXT NOT NULL CHECK(plan_type IN (
        'warehouse_decor','warehouse_acc','factory','purchases','risk','hospitality'
    )),
    title TEXT NOT NULL,
    assigned_to INTEGER,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','in_progress','ready','dispatched','completed')),
    started_at TEXT,
    completed_at TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_plan_id) REFERENCES work_plans(id) ON DELETE CASCADE
);

CREATE TABLE sub_plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sub_plan_id INTEGER NOT NULL,
    work_plan_item_id INTEGER NOT NULL,
    is_done INTEGER DEFAULT 0,
    done_quantity REAL DEFAULT 0,
    done_by INTEGER,
    done_at TEXT,
    photo_proof TEXT,
    notes TEXT,
    FOREIGN KEY (sub_plan_id) REFERENCES sub_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (work_plan_item_id) REFERENCES work_plan_items(id)
);

-- ============================================================
-- 12. التشيك ليست (للتوافق مع الكود القديم - نفس هيكل sub_plans)
-- ============================================================
CREATE TABLE warehouse_checklists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    warehouse TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    assigned_to INTEGER,
    started_at TEXT, completed_at TEXT,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE warehouse_checklist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checklist_id INTEGER NOT NULL,
    plan_item_id INTEGER NOT NULL,
    is_picked INTEGER DEFAULT 0,
    picked_quantity INTEGER DEFAULT 0,
    picked_by INTEGER, picked_at TEXT,
    notes TEXT
);

-- ============================================================
-- 13. خطة إدارة المخاطر (الديكورات المتشابهة)
-- ============================================================
CREATE TABLE risk_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_code TEXT UNIQUE NOT NULL,          -- RA-2026-05
    period_year INTEGER NOT NULL,
    period_month INTEGER NOT NULL,
    title TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(period_year, period_month)
);

CREATE TABLE risk_assessment_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    similar_event_id INTEGER,                -- مناسبة مشابهة
    similarity_type TEXT,                    -- color/decor/fabric
    priority TEXT DEFAULT 'medium' CHECK(priority IN ('high','medium','low')),
    images TEXT,                             -- JSON array of image paths
    mitigation_notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (assessment_id) REFERENCES risk_assessments(id) ON DELETE CASCADE
);

-- ============================================================
-- 14. تكليفات وتنفيذ المناسبات
-- ============================================================
CREATE TABLE event_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    arrival_time TEXT,
    actual_arrival TEXT,
    status TEXT DEFAULT 'assigned',
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE event_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantity INTEGER DEFAULT 1,
    status TEXT DEFAULT 'reserved',
    checkout_date TEXT, return_date TEXT,
    return_condition TEXT, notes TEXT,
    UNIQUE(event_id, item_id)
);

CREATE TABLE event_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    title TEXT NOT NULL, description TEXT,
    assigned_to INTEGER, priority TEXT DEFAULT 'normal',
    status TEXT DEFAULT 'pending',
    due_time TEXT, completed_at TEXT, completed_by INTEGER,
    notes TEXT,
    created_by INTEGER,                      -- مدير المشروع
    task_phase TEXT,                         -- factory/execution/handover
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE event_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    payment_method TEXT, payment_type TEXT,
    reference TEXT,
    payment_date TEXT DEFAULT CURRENT_TIMESTAMP,
    received_by INTEGER, notes TEXT
);

-- ============================================================
-- 15. صور المناسبة (القديمة - للاحتفاظ بالتوافق)
-- ============================================================
CREATE TABLE event_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    photo_type TEXT, photo_path TEXT NOT NULL,
    caption TEXT, uploaded_by INTEGER,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 16. التوثيق الصوري الجديد (مع التصنيف والحذف الشهري)
-- ============================================================
CREATE TABLE photo_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    sub_plan_id INTEGER,
    item_id INTEGER,                         -- لو الصورة لقطعة مخزون
    photo_path TEXT NOT NULL,
    photo_phase TEXT NOT NULL CHECK(photo_phase IN (
        'warehouse_loading_start',           -- وصول السيارة للتحميل
        'warehouse_loading_done',            -- بعد التحميل
        'warehouse_return',                  -- رجوع السيارة
        'warehouse_unload',                  -- بعد التفريغ
        'execution_arrival',                 -- وصول التنفيذ للموقع
        'execution_stage',                   -- مرحلة من التنفيذ
        'execution_done',                    -- نهاية التنفيذ
        'supervision_review',                -- مراجعة الإشراف
        'supervision_handover',              -- تسليم العميل
        'damage_report',                     -- توثيق ضرر
        'inventory_item',                    -- صورة لقطعة مخزون
        'other'
    )),
    caption TEXT,
    taken_by INTEGER NOT NULL,
    taken_at TEXT DEFAULT CURRENT_TIMESTAMP,
    is_archived INTEGER DEFAULT 0,           -- محفوظ يدويًا (لا يُحذف)
    expires_at TEXT,                         -- موعد الحذف (شهر من الرفع)
    deleted_at TEXT
);
CREATE INDEX idx_photo_event ON photo_documents(event_id);
CREATE INDEX idx_photo_phase ON photo_documents(photo_phase);
CREATE INDEX idx_photo_expires ON photo_documents(expires_at);

-- ============================================================
-- 17. حجوزات المواعيد (لخدمة العملاء)
-- ============================================================
CREATE TABLE appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_code TEXT UNIQUE NOT NULL,   -- APT-2026-001
    customer_id INTEGER,
    customer_name TEXT,                      -- لو عميل جديد
    customer_phone TEXT,
    appointment_type TEXT NOT NULL CHECK(appointment_type IN (
        'consultation',                      -- استشارة أولية
        'design_review',                     -- مراجعة تصميم
        'contract_signing',                  -- توقيع عقد
        'site_visit',                        -- معاينة موقع
        'event_day',                         -- يوم المناسبة
        'meeting_internal',                  -- اجتماع داخلي
        'other'
    )),
    title TEXT NOT NULL,
    appointment_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    location TEXT,
    assigned_to INTEGER,                     -- الموظف المسؤول
    related_event_id INTEGER,                -- لو مرتبط بمناسبة
    status TEXT DEFAULT 'scheduled' CHECK(status IN ('scheduled','confirmed','done','cancelled','no_show')),
    color_label TEXT,                        -- ذهبي/أزرق/أخضر للتقويم
    notes TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_appt_date ON appointments(appointment_date);
CREATE INDEX idx_appt_assigned ON appointments(assigned_to);

-- ============================================================
-- 18. التعليقات والموافقات
-- ============================================================
CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    comment_text TEXT NOT NULL,
    is_owner_note INTEGER DEFAULT 0,
    target_team TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_comments_entity ON comments(entity_type, entity_id);

CREATE TABLE approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    decision TEXT CHECK(decision IN ('approved','rejected','pending')),
    decided_by INTEGER,
    decision_notes TEXT,
    decided_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(entity_type, entity_id)
);

-- ============================================================
-- 19. جداول مزامنة Google Sheets (موجودة مسبقًا)
-- ============================================================
CREATE TABLE sheet_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_code TEXT, operation_order TEXT,
    event_type TEXT, customer_name TEXT, venue TEXT,
    contract_date TEXT, expected_date TEXT, actual_date TEXT,
    contract_value REAL, additional REAL, contract_value_with_vat REAL,
    insurance REAL, insurance_returned REAL, discount REAL,
    total_revenue REAL, received REAL, remaining REAL,
    notes TEXT, status TEXT,
    last_synced TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sheet_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_type TEXT, operation_order TEXT,
    event_type TEXT, customer_name TEXT, venue TEXT,
    expected_date TEXT, actual_date TEXT,
    project_status TEXT, responsible TEXT,
    item_or_supplier TEXT, invoice_number TEXT, invoice_date TEXT,
    description TEXT, quantity REAL,
    total_amount REAL, recoverable_vat REAL, net_cost REAL,
    payment_method TEXT, paid REAL, remaining REAL, notes TEXT,
    last_synced TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sheet_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_order TEXT, event_type TEXT, customer_name TEXT, venue TEXT,
    expected_date TEXT, actual_date TEXT,
    project_status TEXT, responsible TEXT,
    item TEXT, invoice_number TEXT, invoice_date TEXT,
    description TEXT, quantity REAL,
    total_amount REAL, recoverable_vat REAL, net_cost REAL,
    payment_method TEXT, paid REAL, remaining REAL, notes TEXT,
    last_synced TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL, status TEXT NOT NULL,
    rows_imported INTEGER DEFAULT 0,
    error_message TEXT, duration_ms INTEGER,
    sync_date TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 20. سجل التدقيق
-- ============================================================
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, action TEXT NOT NULL,
    entity_type TEXT, entity_id INTEGER,
    old_value TEXT, new_value TEXT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 21. المصاريف اليدوية (تُسجّل من الجوال — مختلفة عن sheet_expenses المُزامنة)
-- ============================================================
CREATE TABLE expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_code TEXT UNIQUE NOT NULL,           -- EXP-2026-0001
    event_id INTEGER,                            -- لو مرتبط بمناسبة
    expense_category TEXT NOT NULL CHECK(expense_category IN (
        'materials',         -- خامات
        'transport',         -- نقل/مواصلات
        'food',              -- ضيافة/طعام
        'rental',            -- إيجارات
        'salaries',          -- أجور يومية
        'utilities',         -- خدمات (كهرباء/ماء/إنترنت)
        'maintenance',       -- صيانة
        'office',            -- مكتبية
        'misc'               -- متنوعة
    )),
    description TEXT NOT NULL,                   -- وصف المصروف
    amount REAL NOT NULL,                        -- المبلغ
    payment_method TEXT CHECK(payment_method IN ('cash','card','bank_transfer','other')) DEFAULT 'cash',
    receipt_photo TEXT,                          -- صورة الفاتورة (base64 أو path)
    vendor_name TEXT,                            -- اسم المورد/المحل
    invoice_number TEXT,                         -- رقم الفاتورة لو موجود
    expense_date TEXT NOT NULL,                  -- تاريخ المصروف
    notes TEXT,
    recorded_by INTEGER NOT NULL,                -- المستخدم اللي سجّله
    approved_by INTEGER,                         -- معتمد من
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES events(id),
    FOREIGN KEY (recorded_by) REFERENCES users(id),
    FOREIGN KEY (approved_by) REFERENCES users(id)
);
CREATE INDEX idx_expenses_event ON expenses(event_id);
CREATE INDEX idx_expenses_date ON expenses(expense_date);
CREATE INDEX idx_expenses_recorder ON expenses(recorded_by);

-- ============================================================
-- البيانات الأولية: الفرق
-- ============================================================
INSERT INTO teams (name, type, description) VALUES
('الإدارة العليا',          'executive',           'المالكة والمدير العام'),
('إدارة المشاريع',          'project_management',  'مدير المشروع والمصممين'),
('الإشراف العام',           'supervision',         'مشرفات المناسبات'),
('التنفيذ الميداني',        'field',               'فريق التركيب والتنفيذ'),
('مستودع الديكورات',        'warehouse_decor',     'إدارة مخزون الديكورات الكبيرة'),
('مستودع الاكسسوارات',      'warehouse_acc',       'إدارة مخزون الاكسسوارات'),
('المصنع',                  'factory',             'تصنيع الديكورات والمواد الخام'),
('الضيافة',                 'hospitality',         'خدمة الضيوف والمأكولات'),
('التعاقد وخدمة العملاء',   'customer_service',    'العقود والمواعيد والعملاء'),
('المالية',                 'finance',             'الفواتير والربحية'),
('المشتريات',               'purchasing',          'المشتريات والموردين');

-- ============================================================
-- تصنيفات مستودع الديكورات (17)
-- ============================================================
INSERT INTO inventory_categories (name, name_en, name_ur, warehouse, icon, needs_color, needs_fabric, sort_order) VALUES
('مدخل',                'Entrance',          'داخلہ',       'decorations', '🚪', 1, 1, 1),
('خلفيات',              'Backgrounds',       'پس منظر',     'decorations', '🖼️', 1, 1, 2),
('كونسول',              'Console',           'کونسول',      'decorations', '🪑', 1, 0, 3),
('دولاب عبايات',        'Abaya Closet',      'عبایہ کلوزٹ', 'decorations', '👗', 0, 1, 4),
('صوفات',               'Sofas',             'صوفے',        'decorations', '🛋️', 1, 1, 5),
('كراسي',               'Chairs',            'کرسیاں',      'decorations', '💺', 1, 1, 6),
('كوشنز',               'Cushions',          'تکیے',        'decorations', '🛌', 1, 1, 7),
('إضاءة',               'Lighting',          'لائٹنگ',      'decorations', '💡', 0, 0, 8),
('خلفية سرير',          'Bed Background',    'بیڈ پس منظر', 'decorations', '🛏️', 1, 1, 9),
('خلفية ضيافة',         'Reception BG',      'ریسپشن پس',   'decorations', '🍽️', 1, 1, 10),
('خلفية توزيعات',       'Gifts BG',          'تحفے پس',     'decorations', '🎁', 1, 1, 11),
('طاولات خدمة',         'Service Tables',    'سروس میز',    'decorations', '🪑', 1, 0, 12),
('طاولات وسط',          'Center Tables',     'سینٹر میز',   'decorations', '🟫', 1, 0, 13),
('بوكسات جانبية',       'Side Boxes',        'سائیڈ بکس',   'decorations', '📦', 1, 0, 14),
('ستائر',               'Curtains',          'پردے',        'decorations', '🪟', 1, 1, 15),
('ستاندات مدخل',        'Entrance Stands',   'انٹرنس اسٹینڈ','decorations', '🎯', 1, 0, 16),
('أرضيات',              'Floors',            'فرش',         'decorations', '🟨', 1, 1, 17);

-- تصنيفات الاكسسوارات (4)
INSERT INTO inventory_categories (name, name_en, name_ur, warehouse, icon, needs_color, needs_fabric, sort_order) VALUES
('علب فاين',            'Fine Boxes',        'فائن باکس',   'accessories', '🎁', 1, 0, 1),
('طفايات',              'Ashtrays',          'ایش ٹرے',     'accessories', '🚬', 0, 0, 2),
('دفيوزر',              'Diffusers',         'ڈفیوزر',      'accessories', '💨', 0, 0, 3),
('فازة',                'Vases',             'گلدان',       'accessories', '🏺', 1, 0, 4);

-- تصنيفات المصنع (المواد الخام)
INSERT INTO inventory_categories (name, name_en, name_ur, warehouse, icon, needs_color, needs_fabric, sort_order) VALUES
('بويات',               'Paints',            'پینٹس',       'factory_raw', '🎨', 1, 0, 1),
('أخشاب',               'Wood',              'لکڑی',        'factory_raw', '🪵', 0, 0, 2),
('أقمشة',               'Fabrics',           'کپڑے',        'factory_raw', '🧵', 0, 1, 3),
('مسامير وبراغي',       'Nails & Screws',    'کیلیں',       'factory_raw', '🔩', 0, 0, 4),
('أسلاك LED',           'LED Wires',         'ایل ای ڈی',   'factory_raw', '💡', 0, 0, 5),
('ورد صناعي',           'Artificial Flowers','مصنوعی پھول', 'factory_raw', '🌸', 1, 0, 6),
('استانلس وحديد',       'Steel & Iron',      'اسٹینلیس',    'factory_raw', '⚙️', 0, 0, 7),
('أكريلك',              'Acrylic',           'ایکریلک',     'factory_raw', '🪟', 1, 0, 8),
('أدوات ومستهلكات',     'Tools',             'ٹولز',        'factory_raw', '🛠️', 0, 0, 9);

-- ============================================================
-- المستخدمون الفعليون لأبيلا (مع اللغة)
-- ============================================================
INSERT INTO users (username, password_hash, full_name, role, language, can_record_expenses, phone) VALUES
-- الإدارة العليا
('nouf',         '$2b$default', 'نوف بنت سعد بن كليب — مالكة أبيلا', 'owner',           'ar', NULL, NULL),
('mansour',      '$2b$default', 'منصور — المدير العام',              'general_manager', 'ar', NULL, NULL),
-- إدارة المشاريع (placeholders)
('pm1',          '$2b$default', 'مدير المشروع — لم يُحدد بعد',       'project_manager', 'ar', NULL, NULL),
('designer1',    '$2b$default', 'المصمم — لم يُحدد بعد',             'designer',        'ar', NULL, NULL),
-- مسؤول المخزون
('inventory_mgr','$2b$default', 'مسؤول المخزون — لم يُحدد بعد',      'inventory_manager','ar', NULL, NULL),
-- مشرفات الإشراف
('mihaf',        '$2b$default', 'ميهاف — مشرفة',                    'supervisor',      'ar', 'supervision', NULL),
('shareefa',     '$2b$default', 'شريفة — مشرفة',                    'supervisor',      'ar', 'supervision', NULL),
-- مشرفي التنفيذ + المشتريات
('moaaz',        '$2b$default', 'معاذ — مشرف تنفيذ',                'field',           'ar', 'execution', NULL),
('faris',        '$2b$default', 'فارس — مشرف تنفيذ',                'field',           'ar', 'purchases', NULL),
-- مستودع الديكورات
('faheem',       '$2b$default', 'فهيم — مسؤول مستودع الديكورات',    'warehouse_decor', 'ar', NULL, NULL),
-- مستودع الاكسسوارات (إنجليزي)
('daryl',        '$2b$default', 'Daryl — Accessories Warehouse',    'warehouse_acc',   'en', NULL, NULL),
('rose',         '$2b$default', 'Rose — Accessories Warehouse',     'warehouse_acc',   'en', NULL, NULL),
-- المصنع (أوردو)
('omran',        '$2b$default', 'عمران — مدير المصنع',              'factory',         'ur', NULL, NULL),
-- الضيافة
('raghad',       '$2b$default', 'رغد — مسؤولة الضيافة',             'hospitality',     'ar', NULL, NULL),
-- التعاقد وخدمة العملاء
('rahaf',        '$2b$default', 'رهف — مسؤولة التعاقد',             'customer_service','ar', NULL, NULL),
-- المالية
('badruddin',    '$2b$default', 'بدرالدين — المدير المالي',         'finance',         'ar', NULL, NULL),
-- المشتريات
('abdulqayum',   '$2b$default', 'عبدالقيوم — مسؤول المشتريات',      'purchasing',      'ar', NULL, NULL),
-- مدير النظام التقني
('admin',        '$2b$default', 'مدير النظام التقني',                'admin',           'ar', NULL, NULL);

