// ============================================================
// وحدات الشاشات الجديدة لنظام أبيلا (الدفعة 2)
// ============================================================
// - المواد الخام (raw materials)
// - المواعيد (appointments)
// - التقويم البصري (calendar)
// - الخطط الفرعية (sub plans)
// - دعم اللغات (i18n)
// ============================================================

// ============ متغيرات عامة ============
let CURRENT_USER = null;
let CURRENT_PERMS = null;
let I18N = {};
let CURRENT_LANG = 'ar';

// أسماء الأدوار بالعربي
const ROLE_LABELS = {
  owner: '👑 المالكة',
  general_manager: '🎖 المدير العام',
  admin: '🔧 مدير النظام',
  project_manager: '📋 مدير المشروع',
  designer: '🎨 المصمم',
  inventory_manager: '📦 مسؤول المخزون',
  supervisor: '👁 مشرفة',
  field: '⚙ تنفيذ ميداني',
  warehouse_decor: '📦 مستودع الديكورات',
  warehouse_acc: '✨ مستودع الاكسسوارات',
  warehouse: '📦 مستودع',
  factory: '🛠 المصنع',
  hospitality: '🍽 الضيافة',
  customer_service: '📝 خدمة العملاء',
  finance: '💰 المالية',
  purchasing: '🛒 المشتريات',
  planner: '📋 مخطط'
};

// تسميات نقاط القائمة
const MENU_LABELS = {
  dashboard: { ar: 'لوحة المعلومات', en: 'Dashboard', ur: 'ڈیش بورڈ', icon: '📊' },
  events: { ar: 'المناسبات', en: 'Events', ur: 'تقریبات', icon: '🎉' },
  customers: { ar: 'العملاء', en: 'Customers', ur: 'گاہک', icon: '👥' },
  inventory: { ar: 'المخزون', en: 'Inventory', ur: 'انوینٹری', icon: '📦' },
  raw_materials: { ar: 'المواد الخام', en: 'Raw Materials', ur: 'خام مواد', icon: '🎨' },
  work_plans: { ar: 'خطط العمل', en: 'Work Plans', ur: 'منصوبے', icon: '📋' },
  checklists: { ar: 'التشيك ليست', en: 'Checklists', ur: 'چیک لسٹ', icon: '✅' },
  appointments: { ar: 'المواعيد', en: 'Appointments', ur: 'ملاقاتیں', icon: '📅' },
  calendar: { ar: 'التقويم', en: 'Calendar', ur: 'کیلنڈر', icon: '🗓' },
  teams: { ar: 'الفرق', en: 'Teams', ur: 'ٹیمیں', icon: '👷' },
  finance: { ar: 'المالية', en: 'Finance', ur: 'مالیات', icon: '💰' },
  reports: { ar: 'التقارير', en: 'Reports', ur: 'رپورٹس', icon: '📈' },
  sync: { ar: 'مزامنة Excel', en: 'Excel Sync', ur: 'ایکسل سنک', icon: '🔄' },
  users: { ar: 'المستخدمون', en: 'Users', ur: 'صارفین', icon: '👤' },
  my_tasks: { ar: 'مهامي', en: 'My Tasks', ur: 'میرے کام', icon: '✓' },
  my_events: { ar: 'مناسباتي', en: 'My Events', ur: 'میری تقریبات', icon: '🎯' },
  hospitality_plans: { ar: 'خطط الضيافة', en: 'Hospitality', ur: 'مہمان نوازی', icon: '🍽' },
  factory_orders: { ar: 'أوامر المصنع', en: 'Factory Orders', ur: 'فیکٹری آرڈر', icon: '🛠' },
  purchases: { ar: 'المشتريات', en: 'Purchases', ur: 'خریداری', icon: '🛒' }
};

// ============ تحميل الترجمات ============
async function loadI18n(lang) {
  try {
    const res = await fetch(`/api/i18n/${lang}`);
    I18N = await res.json();
    CURRENT_LANG = lang;
    document.documentElement.lang = lang;
    document.documentElement.dir = I18N.dir || 'rtl';
  } catch(e) {
    console.error('Failed to load i18n', e);
  }
}

function t(key, fallback) {
  // مفتاح بالنقاط: common.welcome → I18N.common.welcome
  const parts = key.split('.');
  let val = I18N;
  for (const p of parts) {
    val = val && val[p];
  }
  return val || fallback || key;
}

// ============ تحميل صلاحيات المستخدم ============
async function loadMyPermissions() {
  try {
    const res = await fetch('/api/permissions/me', {
      headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('abela_token') || '') }
    });
    const data = await res.json();
    CURRENT_USER = data.user;
    CURRENT_PERMS = data;
    if (data.user && data.user.language) {
      await loadI18n(data.user.language);
    }
    return data;
  } catch(e) {
    console.error('Failed to load permissions', e);
    return null;
  }
}

// ============ توليد الشريط الجانبي ديناميكيًا ============
function renderDynamicSidebar(menuItems) {
  const items = menuItems || (CURRENT_PERMS && CURRENT_PERMS.menu) || ['dashboard'];
  const lang = CURRENT_LANG || 'ar';
  const html = items.map(key => {
    const meta = MENU_LABELS[key] || { ar: key, en: key, ur: key, icon: '•' };
    const label = meta[lang] || meta.ar;
    return `<a class="nav-item" data-page="${key}"><span class="nav-icon">${meta.icon}</span><span>${label}</span></a>`;
  }).join('');
  return html;
}

// ============ شاشة المواد الخام ============
async function renderRawMaterials() {
  try {
    const items = await fetch('/api/raw-materials').then(r => r.json());
    const types = {
      paint: 'بويات', wood: 'أخشاب', nail: 'مسامير وبراغي',
      wire: 'أسلاك LED', fabric: 'أقمشة', flower_artificial: 'ورد صناعي',
      metal: 'استانلس وحديد', acrylic: 'أكريلك', tool: 'أدوات',
      adhesive: 'لواصق', consumable: 'مستهلكات', other: 'أخرى'
    };
    const html = `
      <div class="page-header">
        <h2 class="page-title">🎨 المواد الخام (مخزون المصنع)</h2>
        <button class="btn" onclick="showNewRawMaterial()">+ إضافة مادة</button>
      </div>
      <div class="card">
        <div class="search-bar">
          <input class="search-input" placeholder="بحث..." oninput="filterRawMaterials(this.value)">
          <select class="form-select" style="width:200px" onchange="filterRawType(this.value)">
            <option value="">كل الأنواع</option>
            ${Object.entries(types).map(([k,v]) => `<option value="${k}">${v}</option>`).join('')}
          </select>
        </div>
        <table id="raw-table">
          <thead><tr>
            <th>الكود</th><th>الاسم</th><th>النوع</th><th>المُصنّع</th>
            <th>كود اللون</th><th>الكمية</th><th>الحد الأدنى</th><th>التكلفة</th><th>الموقع</th>
            <th class="actions-col">الإجراءات</th>
          </tr></thead>
          <tbody>
            ${items.length ? items.map(i => {
              const low = (i.quantity || 0) <= (i.min_quantity || 1);
              return `<tr style="${low ? 'background:#FFF3CD' : ''}" onclick="showRawMaterialDetails(${i.id})">
                <td><strong>${i.material_code}</strong></td>
                <td>${i.name}</td>
                <td>${types[i.material_type] || i.material_type}</td>
                <td>${i.brand || '-'}</td>
                <td>${i.color_code || '-'}</td>
                <td><strong>${i.quantity || 0} ${i.unit}</strong>${low ? ' ⚠️' : ''}</td>
                <td>${i.min_quantity || 0}</td>
                <td>${(i.unit_cost || 0).toLocaleString('ar-SA')} ر.س</td>
                <td>${i.location || '-'}</td>
                <td class="actions-cell">${typeof rowActions==='function' ? rowActions('raw_materials', i.id, i.name) : ''}</td>
              </tr>`;
            }).join('') : '<tr><td colspan="10" class="empty">لا توجد مواد خام مسجلة</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
    document.getElementById('page-content').innerHTML = html;
    window._rawCache = items;
  } catch(e) {
    document.getElementById('page-content').innerHTML = '<div class="empty">خطأ: ' + e.message + '</div>';
  }
}

function filterRawMaterials(q) {
  if (!window._rawCache) return;
  const filtered = window._rawCache.filter(i =>
    !q || i.name.toLowerCase().includes(q.toLowerCase()) || i.material_code.toLowerCase().includes(q.toLowerCase())
  );
  // إعادة الرسم - مبسط
  renderRawMaterialsRows(filtered);
}

function filterRawType(type) {
  if (!window._rawCache) return;
  const filtered = type ? window._rawCache.filter(i => i.material_type === type) : window._rawCache;
  renderRawMaterialsRows(filtered);
}

function renderRawMaterialsRows(items) {
  const tbody = document.querySelector('#raw-table tbody');
  if (!tbody) return;
  tbody.innerHTML = items.map(i => {
    const low = (i.quantity || 0) <= (i.min_quantity || 1);
    return `<tr style="${low ? 'background:#FFF3CD' : ''}" onclick="showRawMaterialDetails(${i.id})">
      <td><strong>${i.material_code}</strong></td>
      <td>${i.name}</td>
      <td>${i.material_type}</td>
      <td>${i.brand || '-'}</td>
      <td>${i.color_code || '-'}</td>
      <td><strong>${i.quantity || 0} ${i.unit}</strong>${low ? ' ⚠️' : ''}</td>
      <td>${i.min_quantity || 0}</td>
      <td>${(i.unit_cost || 0).toLocaleString('ar-SA')} ر.س</td>
      <td>${i.location || '-'}</td>
      <td class="actions-cell">${typeof rowActions==='function' ? rowActions('raw_materials', i.id, i.name) : ''}</td>
    </tr>`;
  }).join('');
}

async function showNewRawMaterial() {
  const body = `
    <form id="raw-form">
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">اسم المادة *</label>
          <input class="form-input" name="name" required placeholder="مثل: بوية جوتن أخضر 8109">
        </div>
        <div class="form-group">
          <label class="form-label">النوع *</label>
          <select class="form-select" name="material_type" required>
            <option value="paint">بويات</option>
            <option value="wood">أخشاب</option>
            <option value="fabric">أقمشة</option>
            <option value="nail">مسامير وبراغي</option>
            <option value="wire">أسلاك LED</option>
            <option value="flower_artificial">ورد صناعي</option>
            <option value="metal">استانلس وحديد</option>
            <option value="acrylic">أكريلك</option>
            <option value="tool">أدوات</option>
            <option value="other">أخرى</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">المُصنّع</label>
          <input class="form-input" name="brand" placeholder="جوتن، دهانات الجزيرة، هافانا...">
        </div>
        <div class="form-group">
          <label class="form-label">كود اللون / المرجع</label>
          <input class="form-input" name="color_code" placeholder="8109، 0125، RAL8003...">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">الحجم/الأبعاد</label>
          <input class="form-input" name="size_or_dimensions" placeholder="10كجم، 145سم...">
        </div>
        <div class="form-group">
          <label class="form-label">الوحدة</label>
          <select class="form-select" name="unit">
            <option value="piece">قطعة</option>
            <option value="meter">متر</option>
            <option value="kg">كجم</option>
            <option value="liter">لتر</option>
            <option value="box">صندوق</option>
            <option value="roll">رول</option>
            <option value="pack">باكيت</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">الكمية الحالية</label>
          <input class="form-input" type="number" name="quantity" step="0.01" value="0">
        </div>
        <div class="form-group">
          <label class="form-label">الحد الأدنى للتنبيه</label>
          <input class="form-input" type="number" name="min_quantity" step="0.01" value="1">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">تكلفة الوحدة (ر.س)</label>
          <input class="form-input" type="number" name="unit_cost" step="0.01" value="0">
        </div>
        <div class="form-group">
          <label class="form-label">الموقع في المخزن</label>
          <input class="form-input" name="location" placeholder="رف A1">
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">المورّد</label>
        <input class="form-input" name="supplier">
      </div>
      <div class="form-group">
        <label class="form-label">ملاحظات</label>
        <textarea class="form-textarea" name="notes" rows="2"></textarea>
      </div>
    </form>
  `;
  openModal('إضافة مادة خام', body, `
    <button class="btn btn-success" onclick="saveRawMaterial()">حفظ</button>
    <button class="btn btn-outline" onclick="closeModal()">إلغاء</button>
  `);
}

async function saveRawMaterial() {
  const data = Object.fromEntries(new FormData(document.getElementById('raw-form')));
  if (!data.name) return toast('الاسم مطلوب', 'error');
  ['quantity','min_quantity','unit_cost'].forEach(k => data[k] = Number(data[k]) || 0);
  try {
    await api('/raw-materials', { method:'POST', body: JSON.stringify(data) });
    closeModal();
    toast('تم الحفظ بنجاح', 'success');
    renderRawMaterials();
  } catch(e) { toast(e.message, 'error'); }
}

async function showRawMaterialDetails(id) {
  try {
    const m = await api('/raw-materials/' + id);
    const body = `
      <div class="detail-grid">
        <div class="detail-item"><strong>الكود</strong>${m.material_code}</div>
        <div class="detail-item"><strong>النوع</strong>${m.material_type}</div>
        <div class="detail-item"><strong>المُصنّع</strong>${m.brand || '-'}</div>
        <div class="detail-item"><strong>كود اللون</strong>${m.color_code || '-'}</div>
        <div class="detail-item"><strong>الكمية</strong>${m.quantity || 0} ${m.unit}</div>
        <div class="detail-item"><strong>الحد الأدنى</strong>${m.min_quantity || 0}</div>
        <div class="detail-item"><strong>التكلفة</strong>${(m.unit_cost || 0).toLocaleString('ar-SA')} ر.س</div>
        <div class="detail-item"><strong>الموقع</strong>${m.location || '-'}</div>
        <div class="detail-item"><strong>المورّد</strong>${m.supplier || '-'}</div>
        <div class="detail-item"><strong>آخر شراء</strong>${m.last_purchase_date || '-'}</div>
      </div>
      ${m.notes ? `<p style="margin-bottom:16px">${m.notes}</p>` : ''}
      <h4 style="margin:16px 0 8px;color:var(--primary)">📋 الحركات</h4>
      ${m.movements && m.movements.length ? `<table>
        <thead><tr><th>التاريخ</th><th>النوع</th><th>الكمية</th><th>الموظف</th><th>ملاحظات</th></tr></thead>
        <tbody>${m.movements.map(mv => `
          <tr><td>${mv.movement_date}</td><td>${mv.movement_type}</td><td>${mv.quantity}</td><td>${mv.user_name || '-'}</td><td>${mv.notes || '-'}</td></tr>
        `).join('')}</tbody>
      </table>` : '<p class="empty">لا توجد حركات</p>'}
    `;
    openModal(`${m.name} — ${m.material_code}`, body, '<button class="btn btn-outline" onclick="closeModal()">إغلاق</button>');
  } catch(err) { toast(err.message, 'error'); }
}

// ============ شاشة المواعيد ============
async function renderAppointments() {
  try {
    const appts = await api('/appointments');
    const types = {
      consultation:'استشارة', design_review:'مراجعة تصميم',
      contract_signing:'توقيع عقد', site_visit:'معاينة موقع',
      event_day:'يوم المناسبة', meeting_internal:'اجتماع داخلي', other:'أخرى'
    };
    const html = `
      <div class="page-header">
        <h2 class="page-title">📅 المواعيد (${appts.length})</h2>
        <button class="btn" onclick="showNewAppointment()">+ موعد جديد</button>
      </div>
      <div class="card">
        <table>
          <thead><tr><th>الكود</th><th>العميل</th><th>النوع</th><th>التاريخ</th><th>الوقت</th><th>الموقع</th><th>المسؤول</th><th>الحالة</th><th class="actions-col">الإجراءات</th></tr></thead>
          <tbody>
            ${appts.length ? appts.map(a => `
              <tr>
                <td><strong>${a.appointment_code}</strong></td>
                <td>${a.customer_name || a.customer_full_name || '-'}<br><small>${a.customer_phone || ''}</small></td>
                <td>${types[a.appointment_type] || a.appointment_type}</td>
                <td>${a.appointment_date}</td>
                <td>${a.start_time || ''}${a.end_time ? ' - ' + a.end_time : ''}</td>
                <td>${a.location || '-'}</td>
                <td>${a.assigned_name || '-'}</td>
                <td><span class="badge badge-${a.status === 'done' ? 'completed' : 'pending'}">${a.status}</span></td>
                <td class="actions-cell">${typeof rowActions==='function' ? rowActions('appointment', a.id, a.title || a.appointment_code) : ''}</td>
              </tr>
            `).join('') : '<tr><td colspan="9" class="empty">لا توجد مواعيد</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
    document.getElementById('page-content').innerHTML = html;
  } catch(e) {
    document.getElementById('page-content').innerHTML = '<div class="empty">' + e.message + '</div>';
  }
}

async function showNewAppointment() {
  const customers = await api('/customers');
  const users = await api('/users');
  const today = new Date().toISOString().split('T')[0];
  const body = `
    <form id="appt-form">
      <div class="form-group">
        <label class="form-label">العميل (اختر من الموجود أو أدخل اسم جديد)</label>
        <select class="form-select" name="customer_id">
          <option value="">عميل جديد...</option>
          ${customers.map(c => `<option value="${c.id}">${c.full_name} - ${c.phone}</option>`).join('')}
        </select>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">اسم عميل جديد</label>
          <input class="form-input" name="customer_name" placeholder="إذا غير مسجّل">
        </div>
        <div class="form-group">
          <label class="form-label">جوال</label>
          <input class="form-input" name="customer_phone" dir="ltr">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">نوع الموعد *</label>
          <select class="form-select" name="appointment_type" required>
            <option value="consultation">استشارة أولية</option>
            <option value="design_review">مراجعة تصميم</option>
            <option value="contract_signing">توقيع عقد</option>
            <option value="site_visit">معاينة موقع</option>
            <option value="meeting_internal">اجتماع داخلي</option>
            <option value="other">أخرى</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">عنوان الموعد *</label>
          <input class="form-input" name="title" required placeholder="مثل: استشارة عرس...">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">التاريخ *</label>
          <input class="form-input" type="date" name="appointment_date" required value="${today}">
        </div>
        <div class="form-group">
          <label class="form-label">الوقت *</label>
          <input class="form-input" type="time" name="start_time" required>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">المسؤول</label>
        <select class="form-select" name="assigned_to">
          <option value="">بدون</option>
          ${users.map(u => `<option value="${u.id}">${u.full_name}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">الموقع</label>
        <input class="form-input" name="location" placeholder="مكتب أبيلا، أو الموقع...">
      </div>
      <div class="form-group">
        <label class="form-label">ملاحظات</label>
        <textarea class="form-textarea" name="notes" rows="2"></textarea>
      </div>
    </form>
  `;
  openModal('إضافة موعد جديد', body, `
    <button class="btn btn-success" onclick="saveAppointment()">حفظ</button>
    <button class="btn btn-outline" onclick="closeModal()">إلغاء</button>
  `);
}

async function saveAppointment() {
  const data = Object.fromEntries(new FormData(document.getElementById('appt-form')));
  if (!data.title || !data.appointment_date || !data.start_time) return toast('املأ الحقول المطلوبة', 'error');
  data.customer_id = Number(data.customer_id) || null;
  data.assigned_to = Number(data.assigned_to) || null;
  try {
    const r = await api('/appointments', { method:'POST', body: JSON.stringify(data) });
    closeModal();
    toast(`تم حفظ الموعد: ${r.appointment_code}`, 'success');
    renderAppointments();
  } catch(e) { toast(e.message, 'error'); }
}

// ============ التقويم البصري ============
async function renderCalendar() {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  await renderCalendarMonth(year, month);
}

async function renderCalendarMonth(year, month) {
  try {
    const data = await api(`/calendar?year=${year}&month=${month}`);
    const monthName = new Date(year, month-1, 1).toLocaleDateString('ar-SA', { month: 'long', year: 'numeric' });

    // بناء شبكة التقويم
    const firstDay = new Date(year, month-1, 1).getDay();
    const daysInMonth = new Date(year, month, 0).getDate();
    const items = data.all_items;
    const itemsByDate = {};
    items.forEach(i => {
      const d = i.date;
      if (!itemsByDate[d]) itemsByDate[d] = [];
      itemsByDate[d].push(i);
    });

    // ألوان حسب نوع المناسبة + حساب القرب من اليوم
    function eventColorClass(item) {
      if (item.item_type !== 'event') return 'cal-item-appointment';
      const dDays = Math.round((new Date(item.date) - new Date()) / (1000*60*60*24));
      if (dDays < 0) return 'cal-evt-past';        // مرّت
      if (dDays === 0) return 'cal-evt-today';     // اليوم - أحمر
      if (dDays <= 5) return 'cal-evt-soon';        // قريبة - برتقالي
      if (dDays <= 12) return 'cal-evt-near';       // متوسطة - أصفر
      const t = (item.event_type || 'newborn');
      return `cal-evt-${t}`;                         // حسب النوع
    }
    function eventIcon(item) {
      if (item.item_type === 'appointment') return '📅';
      const t = item.event_type;
      if (t === 'newborn') return '👶';
      if (t === 'special') return '💍';
      if (t === 'exhibition') return '🎪';
      return '🎉';
    }

    let cells = [];
    for (let i = 0; i < firstDay; i++) cells.push('<div></div>');
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${year}-${String(month).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const dayItems = itemsByDate[dateStr] || [];
      const isToday = new Date().toISOString().split('T')[0] === dateStr;
      cells.push(`
        <div class="cal-day ${isToday ? 'today' : ''}" data-date="${dateStr}">
          <div class="cal-day-num">${d}</div>
          ${dayItems.slice(0,3).map(it => `
            <div class="cal-item ${eventColorClass(it)}" title="${it.title}"
                 onclick="showCalendarItem(${JSON.stringify(it).replace(/"/g,'&quot;')})">
              ${eventIcon(it)} ${it.title.slice(0, 20)}${it.title.length > 20 ? '...' : ''}
            </div>
          `).join('')}
          ${dayItems.length > 3 ? `<div class="cal-more" onclick="showDayItems('${dateStr}')">+${dayItems.length - 3}</div>` : ''}
        </div>
      `);
    }
    // خزن البيانات للوصول من showDayItems
    window.__calItemsByDate = itemsByDate;

    const html = `
      <style>
        .cal-grid { display:grid; grid-template-columns:repeat(7, 1fr); gap:4px; background:var(--border); }
        .cal-header { background:var(--primary); color:#fff; padding:10px; text-align:center; font-weight:700; }
        .cal-day { background:#fff; min-height:100px; padding:6px; }
        .cal-day.today { background:#FFF8E7; border:2px solid var(--accent); }
        .cal-day-num { font-weight:700; color:var(--primary-dark); margin-bottom:4px; }
        .cal-item { padding:3px 6px; border-radius:4px; font-size:10px; margin-bottom:2px; cursor:pointer;
                    overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .cal-item:hover { transform:scale(1.03); }
        .cal-item-appointment { background:#DDEBF7; color:#1F4E79; }
        .cal-evt-today    { background:#FECACA; color:#7F1D1D; font-weight:700; border:1px solid #DC2626; }
        .cal-evt-soon     { background:#FED7AA; color:#7C2D12; font-weight:600; }
        .cal-evt-near     { background:#FEF3C7; color:#78350F; }
        .cal-evt-past     { background:#E5E7EB; color:#6B7280; opacity:0.7; }
        .cal-evt-newborn  { background:#FCE7F3; color:#9F1239; }
        .cal-evt-special  { background:#DBEAFE; color:#1E40AF; }
        .cal-evt-exhibition { background:#DDD6FE; color:#5B21B6; }
        .cal-more { font-size:11px; color:var(--primary); cursor:pointer; font-weight:600; }
        .cal-legend { display:flex; flex-wrap:wrap; gap:8px; padding:10px; font-size:11px; }
        .cal-legend span { display:inline-flex; align-items:center; gap:4px; padding:3px 8px; border-radius:4px; }
      </style>
      <div class="card" style="margin-bottom:12px">
        <div class="cal-legend">
          <span class="cal-evt-today">🔴 اليوم</span>
          <span class="cal-evt-soon">🟠 خلال 5 أيام</span>
          <span class="cal-evt-near">🟡 خلال 12 يوم</span>
          <span class="cal-evt-newborn">👶 استقبال مولود</span>
          <span class="cal-evt-special">💍 مناسبة خاصة</span>
          <span class="cal-evt-exhibition">🎪 معرض</span>
          <span class="cal-item-appointment">📅 موعد</span>
        </div>
      </div>
      <div class="page-header">
        <h2 class="page-title">🗓 التقويم — ${monthName}</h2>
        <div>
          <button class="btn btn-outline btn-sm" onclick="renderCalendarMonth(${year}, ${month-1 || 12})">‹ السابق</button>
          <button class="btn btn-outline btn-sm" onclick="renderCalendar()">اليوم</button>
          <button class="btn btn-outline btn-sm" onclick="renderCalendarMonth(${year}, ${month+1 > 12 ? 1 : month+1})">التالي ›</button>
        </div>
      </div>
      <div class="card">
        <div class="cal-grid">
          ${['الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت'].map(d => `<div class="cal-header">${d}</div>`).join('')}
          ${cells.join('')}
        </div>
      </div>
      <div class="stats-row" style="margin-top:16px">
        <div class="stat-mini">
          <div class="stat-label">🎉 المناسبات في الشهر</div>
          <div class="stat-value">${data.events.length}</div>
        </div>
        <div class="stat-mini">
          <div class="stat-label">📅 المواعيد في الشهر</div>
          <div class="stat-value">${data.appointments.length}</div>
        </div>
      </div>
    `;
    document.getElementById('page-content').innerHTML = html;
  } catch(e) {
    document.getElementById('page-content').innerHTML = '<div class="empty">' + e.message + '</div>';
  }
}

// عرض بطاقة عنصر التقويم
function showCalendarItem(item) {
  const dDays = Math.round((new Date(item.date) - new Date()) / (1000*60*60*24));
  const proximity = dDays === 0 ? '🔴 اليوم!'
                  : dDays > 0 ? `بعد ${dDays} يوم`
                  : `مرّت قبل ${Math.abs(dDays)} يوم`;
  const body = `
    <div class="detail-grid">
      <div class="detail-item"><strong>النوع</strong>${item.item_type === 'event' ? '🎉 مناسبة' : '📅 موعد'}</div>
      <div class="detail-item"><strong>التاريخ</strong>${item.date} <small>(${proximity})</small></div>
      <div class="detail-item"><strong>العميل</strong>${item.customer_name || '-'}</div>
      <div class="detail-item"><strong>المكان</strong>${item.location || item.venue_name || '-'}</div>
      ${item.notes ? `<div class="detail-item" style="grid-column:1/-1"><strong>ملاحظات</strong>${item.notes}</div>` : ''}
    </div>
  `;
  openModal(item.title, body, `
    ${item.item_type === 'event' ?
      `<button class="btn" onclick="closeModal();typeof openEventWorkPlans==='function'&&openEventWorkPlans(${item.id})">📋 خطط هذه المناسبة</button>` : ''}
    <button class="btn btn-outline" onclick="closeModal()">إغلاق</button>
  `);
}

function showDayItems(date) {
  const items = (window.__calItemsByDate || {})[date] || [];
  const body = `<div style="display:flex;flex-direction:column;gap:8px">
    ${items.map(it => `
      <div class="card" style="padding:10px;cursor:pointer" onclick="showCalendarItem(${JSON.stringify(it).replace(/"/g,'&quot;')})">
        <strong>${it.title}</strong>
        <div style="color:var(--text-light);font-size:12px">${it.customer_name || ''}</div>
      </div>
    `).join('')}
  </div>`;
  openModal(`أحداث يوم ${date}`, body, '<button class="btn btn-outline" onclick="closeModal()">إغلاق</button>');
}

// ============ حساب أولوية المخاطر حسب القرب من المناسبة ============
// القاعدة: نفس اليوم=حرجة، خلال 5 أيام=عالية، 6-12 يوم=متوسطة، أكثر من 12=منخفضة، مرّت=مكتملة
function computeRiskPriority(eventDate) {
  if (!eventDate) return {level:'unknown', icon:'⚪', label:'غير محدد'};
  const dDays = Math.round((new Date(eventDate) - new Date()) / (1000*60*60*24));
  if (dDays < 0)  return {level:'past',     icon:'⚫', label:'مرّت'};
  if (dDays === 0) return {level:'critical', icon:'🔴', label:'حرجة (اليوم)'};
  if (dDays <= 5) return {level:'high',     icon:'🟠', label:`عالية (${dDays} أيام)`};
  if (dDays <= 12) return {level:'medium',   icon:'🟡', label:`متوسطة (${dDays} يوم)`};
  return {level:'low', icon:'🟢', label:`منخفضة (${dDays} يوم)`};
}
// كشف Style للأولويات
if (typeof document !== 'undefined' && !document.getElementById('risk-styles')) {
  const s = document.createElement('style'); s.id = 'risk-styles';
  s.textContent = `
    .risk-critical { color:#7F1D1D; background:#FECACA; padding:3px 8px; border-radius:6px; font-weight:700; }
    .risk-high     { color:#7C2D12; background:#FED7AA; padding:3px 8px; border-radius:6px; font-weight:600; }
    .risk-medium   { color:#78350F; background:#FEF3C7; padding:3px 8px; border-radius:6px; }
    .risk-low      { color:#065F46; background:#D1FAE5; padding:3px 8px; border-radius:6px; }
    .risk-past     { color:#6B7280; background:#E5E7EB; padding:3px 8px; border-radius:6px; }
    .risk-unknown  { color:#6B7280; padding:3px 8px; }
  `;
  document.head.appendChild(s);
}

// ============ الخطط الفرعية ============
async function renderSubPlans() {
  try {
    const plans = await api('/sub-plans');
    const types = {
      warehouse_decor: '📦 ديكورات', warehouse_acc: '✨ اكسسوارات',
      factory: '🛠 مصنع', purchases: '🛒 مشتريات',
      risk: '⚠️ مخاطر', hospitality: '🍽 ضيافة'
    };
    const html = `
      <div class="page-header"><h2 class="page-title">📋 الخطط الفرعية (${plans.length})</h2></div>
      <div class="card">
        <table>
          <thead><tr><th>النوع</th><th>المناسبة</th><th>التاريخ</th><th>الأولوية</th><th>المسؤول</th><th>التقدم</th><th>الحالة</th><th>طباعة</th></tr></thead>
          <tbody>
            ${plans.length ? plans.map(p => {
              const pct = p.total_items ? Math.round((p.done_items / p.total_items) * 100) : 0;
              // === حساب أولوية المخاطر حسب القرب من تاريخ المناسبة ===
              const prio = computeRiskPriority(p.event_date);
              return `<tr>
                <td>${types[p.plan_type] || p.plan_type}</td>
                <td>${p.event_title || '-'}</td>
                <td>${p.event_date || '-'}</td>
                <td><span class="risk-${prio.level}">${prio.icon} ${prio.label}</span></td>
                <td>${p.assigned_name || '<em>غير معين</em>'}</td>
                <td>
                  <div style="background:var(--border);height:8px;border-radius:4px;overflow:hidden">
                    <div style="background:var(--primary);height:100%;width:${pct}%"></div>
                  </div>
                  <small>${p.done_items}/${p.total_items} (${pct}%)</small>
                </td>
                <td><span class="badge badge-${p.status}">${p.status}</span></td>
                <td>
                  <a href="/dashboard/plan_print.html?sub_plan_id=${p.id}" target="_blank" class="btn btn-sm btn-outline">🖨 طباعة</a>
                </td>
              </tr>`;
            }).join('') : '<tr><td colspan="8" class="empty">لا توجد خطط فرعية بعد</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
    document.getElementById('page-content').innerHTML = html;
  } catch(e) {
    document.getElementById('page-content').innerHTML = '<div class="empty">' + e.message + '</div>';
  }
}

// ============ مبدّل اللغة ============
function renderLanguageSwitcher() {
  return `
    <div class="lang-switcher" style="display:flex;gap:4px;justify-content:center;margin:8px 0">
      <button class="lang-btn" data-lang="ar" onclick="switchLanguage('ar')">🇸🇦 ع</button>
      <button class="lang-btn" data-lang="en" onclick="switchLanguage('en')">🇬🇧 EN</button>
      <button class="lang-btn" data-lang="ur" onclick="switchLanguage('ur')">🇵🇰 اردو</button>
    </div>
    <style>
      .lang-btn {
        background: rgba(255,255,255,0.15); color: #fff; border: 1px solid rgba(255,255,255,0.25);
        padding: 4px 10px; border-radius: 6px; font-size: 11px; cursor: pointer;
      }
      .lang-btn:hover { background: rgba(255,255,255,0.25); }
      .lang-btn.active { background: var(--accent); color: var(--primary-dark); font-weight: 700; }
    </style>
  `;
}

async function switchLanguage(lang) {
  await loadI18n(lang);
  // تحديث صلاحية المستخدم في قاعدة البيانات
  if (CURRENT_USER) {
    try {
      await fetch('/api/users/' + CURRENT_USER.id, {
        method: 'PUT',
        headers: {'Content-Type':'application/json','Authorization':'Bearer '+(localStorage.getItem('abela_token')||'')},
        body: JSON.stringify({ language: lang })
      });
    } catch(e) {}
  }
  // إعادة الرسم
  if (typeof renderPage === 'function') renderPage();
  // تحديث الأزرار
  document.querySelectorAll('.lang-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.lang === lang);
  });
}

// تصدير الدوال للنطاق العام
window.renderRawMaterials = renderRawMaterials;
window.renderAppointments = renderAppointments;
window.renderCalendar = renderCalendar;
window.renderCalendarMonth = renderCalendarMonth;
window.renderSubPlans = renderSubPlans;
window.showNewRawMaterial = showNewRawMaterial;
window.saveRawMaterial = saveRawMaterial;
window.showRawMaterialDetails = showRawMaterialDetails;
window.showNewAppointment = showNewAppointment;
window.saveAppointment = saveAppointment;
window.filterRawMaterials = filterRawMaterials;
window.filterRawType = filterRawType;
window.loadMyPermissions = loadMyPermissions;
window.loadI18n = loadI18n;
window.switchLanguage = switchLanguage;
window.renderDynamicSidebar = renderDynamicSidebar;
window.renderLanguageSwitcher = renderLanguageSwitcher;
window.t = t;
window.MENU_LABELS = MENU_LABELS;
window.ROLE_LABELS = ROLE_LABELS;
