/* =====================================================================
 * أبيلا — الإصدار 4.1: الموارد البشرية + الأصول والمعدات والسيارات + ملفي ومهامي
 * ===================================================================== */
Object.assign(NEW_NAV_ICONS, {
  myhr: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><circle cx="14" cy="9" r="4.5"/><path d="M5 24c0-5 4-8.5 9-8.5s9 3.5 9 8.5"/></svg>',
  employees: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><rect x="4" y="5" width="20" height="18" rx="2.5"/><circle cx="11" cy="12" r="2.6"/><path d="M6.5 19.5c.6-2.4 2.3-3.6 4.5-3.6s3.9 1.2 4.5 3.6M17 11h4M17 15h4"/></svg>',
  leaves: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><path d="M14 4c5 3 7 7 7 11a7 7 0 0 1-14 0c0-4 2-8 7-11z"/><path d="M14 24V12"/></svg>',
  payroll: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><circle cx="14" cy="14" r="10"/><path d="M17.5 10.5c-.7-1.2-2-1.8-3.5-1.8-2 0-3.5 1-3.5 2.6 0 3.6 7 1.8 7 5.3 0 1.6-1.6 2.7-3.5 2.7-1.6 0-3-.7-3.6-2M14 6.5v2.2M14 19.3v2.2"/></svg>',
  tasks: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><rect x="5" y="4" width="18" height="21" rx="2.5"/><path d="M9 11l2 2 4-4M9 18l2 2 4-4M17.5 12h2M17.5 19h2"/></svg>',
  assets: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><path d="M3 17h22v4H3z"/><path d="M5 17l2.5-6h13L23 17"/><circle cx="8" cy="21.5" r="2"/><circle cx="20" cy="21.5" r="2"/></svg>',
});

const LV_STATUS = { pending: 'بانتظار الاعتماد', approved: 'معتمدة', rejected: 'مرفوضة', cancelled: 'ملغاة' };
const LV_CLS = { pending: 'warn', approved: 'ok', rejected: 'bad', cancelled: '' };
const TASK_ST = { todo: 'جديدة', in_progress: 'قيد التنفيذ', done: 'منجزة', cancelled: 'ملغاة' };
const TASK_PR = { low: 'منخفضة', normal: 'عادية', high: 'عالية', urgent: 'عاجلة' };
const EMP_ST = { active: 'على رأس العمل', on_leave: 'في إجازة', suspended: 'موقوف', terminated: 'انتهت خدمته' };
const ASSET_CAT = { vehicle: '🚗 سيارات', equipment: '⚙ معدات', tool: '🔧 عدد وأدوات', device: '💻 أجهزة', furniture: '🪑 أثاث', other: '📦 أخرى' };
const ASSET_ST = { active: 'في الخدمة', in_maintenance: 'في الصيانة', out_of_service: 'معطّل', disposed: 'مستبعد/مباع', lost: 'مفقود' };
const M_TYPES = { service: 'صيانة دورية', repair: 'إصلاح', inspection: 'فحص', tires: 'إطارات', accident: 'حادث', other: 'أخرى' };
let LV_TYPES = {};
let EMPS = [];
async function loadEmps() { try { EMPS = await capi('/hr/employees'); } catch (e) { EMPS = []; } return EMPS; }
function empOptions(sel, withEmpty = true) {
  return (withEmpty ? '<option value=""></option>' : '') + EMPS.filter(e => e.status !== 'terminated' || String(e.id) === String(sel))
    .map(e => `<option value="${e.id}" ${String(sel) === String(e.id) ? 'selected' : ''}>${esc(e.full_name)}${e.department ? ' — ' + esc(e.department) : ''}</option>`).join('');
}
function fld(id, label, value = '', type = 'text', extra = '') {
  return `<div class="form-group"><label class="form-label">${label}</label><input id="${id}" type="${type}" class="form-input" value="${esc(value ?? '')}" ${extra}></div>`;
}
function sel(id, label, opts, value, extra = '') {
  return `<div class="form-group"><label class="form-label">${label}</label><select id="${id}" class="form-select" ${extra}>${Object.entries(opts).map(([k, v]) => `<option value="${k}" ${String(value) === String(k) ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></div>`;
}
function expiryCell(d) {
  if (!d) return '<span class="muted">—</span>';
  const n = daysUntil(d);
  return `${dShort(d)}${n !== null && n < 0 ? '<br>' + pill('منتهية', 'bad') : n !== null && n <= 60 ? '<br>' + pill(`بعد ${n} يوم`, 'warn') : ''}`;
}
function moneyOrDash(v) { return v === undefined ? '<span class="muted">🔒</span>' : money(v); }

// ===================================================================
// ملفي ومهامي (الخدمة الذاتية لكل مستخدم)
// ===================================================================
async function renderMyHR() {
  let d;
  try { d = await capi('/me/hr'); } catch (e) { return setContent(`<div class="empty">${esc(e.message)}</div>`); }
  LV_TYPES = d.types;
  const open = d.tasks.filter(t => ['todo', 'in_progress'].includes(t.status));
  const T = todayISO();
  const taskRow = t => `<tr><td><strong>${esc(t.title)}</strong>${t.description ? `<br><small class="muted">${esc(t.description)}</small>` : ''}</td>
    <td>${pill(TASK_PR[t.priority] || t.priority, t.priority === 'urgent' || t.priority === 'high' ? 'bad' : '')}</td>
    <td>${t.due_date ? (t.due_date < T && open.includes(t) ? pill(dShort(t.due_date), 'bad') : dShort(t.due_date)) : '—'}</td>
    <td>${esc(t.assigned_by_name || '')}</td><td>${pill(TASK_ST[t.status], t.status === 'done' ? 'ok' : t.status === 'in_progress' ? 'gold' : 'warn')}</td>
    <td class="nowrap">${t.status === 'todo' ? `<button class="btn btn-sm btn-outline" onclick="myTask(${t.id},'in_progress')">بدأت</button> ` : ''}${['todo', 'in_progress'].includes(t.status) ? `<button class="btn btn-sm" onclick="myTask(${t.id},'done')">✓ أنجزت</button>` : ''}</td></tr>`;
  let body = `<div class="card tight"><div class="card-header"><h3 class="card-title">✅ مهامي (${open.length} مفتوحة)</h3></div>
    ${d.tasks.length ? `<div class="tbl-wrap"><table><thead><tr><th>المهمة</th><th>الأولوية</th><th>الموعد</th><th>من</th><th>الحالة</th><th></th></tr></thead><tbody>${d.tasks.map(taskRow).join('')}</tbody></table></div>` : '<div class="empty">ما عندك مهام</div>'}</div>`;
  if (!d.employee) {
    body += `<div class="hint">حسابك غير مربوط بملف موظف، فما تقدر تطلب إجازة من هنا. اطلب من الموارد البشرية ربط حسابك بملفك.</div>`;
  } else {
    const a = d.annual;
    body = `<div class="stats-grid">
      <div class="stat-card success"><div class="stat-label">رصيد الإجازة السنوية</div><div class="stat-value">${a.available}</div><div class="stat-sub">يوم متاح (الاستحقاق ${a.entitlement} يوم/سنة)</div></div>
      <div class="stat-card"><div class="stat-label">إجازات مرضية آخر 12 شهر</div><div class="stat-value">${d.sick.used}</div><div class="stat-sub">متبقي بأجر كامل ${d.sick.full_pay_left}</div></div>
      <div class="stat-card accent"><div class="stat-label">مهام مفتوحة</div><div class="stat-value">${open.length}</div></div>
      <div class="stat-card"><div class="stat-label">العُهد اللي معي</div><div class="stat-value">${d.custody.length}</div></div>
    </div>` + body + `
    <div class="two-col">
      <div class="card tight"><div class="card-header"><h3 class="card-title">🌿 إجازاتي</h3><button class="btn btn-sm" onclick="myLeaveDialog()">+ طلب إجازة</button></div>
        ${d.leaves.length ? `<table><tbody>${d.leaves.map(l => `<tr><td>${esc((LV_TYPES[l.leave_type] || {}).label || l.leave_type)}</td><td>${dShort(l.start_date)} ← ${dShort(l.end_date)}</td><td>${l.days} يوم</td><td>${pill(LV_STATUS[l.status], LV_CLS[l.status])}${l.decision_note ? `<br><small class="muted">${esc(l.decision_note)}</small>` : ''}</td><td>${l.status === 'pending' ? `<button class="btn btn-sm btn-outline" onclick="myLeaveCancel(${l.id})">إلغاء</button>` : ''}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">لا توجد طلبات</div>'}</div>
      <div class="card tight"><div class="card-header"><h3 class="card-title">💵 مسيّرات راتبي</h3></div>
        ${d.payslips.length ? `<table><thead><tr><th>الشهر</th><th>الإجمالي</th><th>الخصومات</th><th>الصافي</th></tr></thead><tbody>${d.payslips.map(p => `<tr><td>${esc(p.period)}</td><td>${money(p.gross)}</td><td>${money(p.total_ded)}</td><td><strong>${money(p.net)}</strong></td></tr>`).join('')}</tbody></table>` : '<div class="empty">لا يوجد</div>'}
        ${d.custody.length ? `<div class="card-header"><h3 class="card-title">🔑 عُهدي</h3></div><table><tbody>${d.custody.map(c => `<tr><td>${esc(c.asset_code)}</td><td>${esc(c.name)} ${esc(c.plate_no || '')}</td><td>منذ ${dShort(c.custody_since)}</td></tr>`).join('')}</tbody></table>` : ''}
      </div></div>`;
  }
  pageShell(`👤 ${esc(d.employee ? d.employee.full_name : CRM.me.full_name)}`, d.employee ? `<span class="muted">${esc(d.employee.job_title || '')} ${d.employee.emp_no ? '· ' + esc(d.employee.emp_no) : ''}</span>` : '', body);
}
async function myTask(id, st) {
  let note = null;
  if (st === 'done') { note = prompt('ملاحظة الإنجاز (اختياري)', ''); if (note === null) return; }
  try { await capi('/me/tasks/' + id, 'POST', { status: st, note }); toast('تم', 'success'); renderPage(); } catch (e) { toast(e.message, 'error'); }
}
function leaveForm(prefix, withEmp) {
  const types = Object.fromEntries(Object.entries(LV_TYPES).map(([k, v]) => [k, v.label + (v.max ? ` (حتى ${v.max} يوم)` : '')]));
  return `${withEmp ? `<div class="form-group"><label class="form-label">الموظف *</label><select id="${prefix}-emp" class="form-select">${empOptions('')}</select></div>` : ''}
    <div class="form-row">${sel(prefix + '-type', 'نوع الإجازة', types, 'annual')}${fld(prefix + '-days', 'عدد الأيام', '', 'number', 'placeholder="يُحسب تلقائياً"')}</div>
    <div class="form-row">${fld(prefix + '-from', 'من *', todayISO(), 'date', `oninput="lvDays('${prefix}')"`)}${fld(prefix + '-to', 'إلى *', todayISO(), 'date', `oninput="lvDays('${prefix}')"`)}</div>
    <div class="form-group"><label class="form-label">السبب / ملاحظات</label><textarea id="${prefix}-reason" class="form-textarea" rows="2"></textarea></div>`;
}
function lvDays(p) {
  const a = val(p + '-from'), b = val(p + '-to');
  if (a && b) { const n = Math.round((new Date(b) - new Date(a)) / 86400000) + 1; if (n > 0) document.getElementById(p + '-days').value = n; }
}
function myLeaveDialog() {
  openModal('طلب إجازة', leaveForm('ml', false) + '<p class="muted small">يوصل الطلب للموارد البشرية للاعتماد.</p>',
    `<button class="btn" onclick="myLeaveSave()">إرسال الطلب</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
  lvDays('ml');
}
async function myLeaveSave() {
  try {
    await capi('/me/leaves', 'POST', { leave_type: val('ml-type'), start_date: val('ml-from'), end_date: val('ml-to'), days: val('ml-days'), reason: val('ml-reason') });
    closeModal(); toast('تم إرسال الطلب', 'success'); renderPage();
  } catch (e) { toast(e.message, 'error'); }
}
async function myLeaveCancel(id) {
  if (!confirm('إلغاء الطلب؟')) return;
  try { await capi('/me/leaves/' + id, 'DELETE'); renderPage(); } catch (e) { toast(e.message, 'error'); }
}

// ===================================================================
// الموظفون
// ===================================================================
let EMPF = { status: 'active', alerts: null };
async function renderEmployees() {
  await loadEmps();
  try { EMPF.alerts = await capi('/hr/alerts'); } catch (e) { EMPF.alerts = { items: [] }; }
  const showPay = can('payroll');
  const list = EMPF.status === 'all' ? EMPS : EMPS.filter(e => EMPF.status === 'active' ? e.status !== 'terminated' : e.status === 'terminated');
  const active = EMPS.filter(e => e.status !== 'terminated');
  const empAlerts = (EMPF.alerts.items || []).filter(a => a.kind === 'employee');
  const totWage = active.reduce((s, e) => s + (e.wage || 0), 0);
  const tab = (k, l, n) => `<div class="tab ${EMPF.status === k ? 'active' : ''}" onclick="EMPF.status='${k}';renderEmployees()">${l} <span class="cnt">${n}</span></div>`;
  pageShell('👥 الموظفون', can('employees', 'create') ? '<button class="btn" onclick="empEditor()">+ موظف</button>' : '',
    `<div class="stats-grid">
      <div class="stat-card"><div class="stat-label">على رأس العمل</div><div class="stat-value">${active.length}</div><div class="stat-sub">${active.filter(e => e.is_saudi).length} سعودي · ${active.filter(e => !e.is_saudi).length} غير سعودي</div></div>
      ${showPay ? `<div class="stat-card accent"><div class="stat-label">إجمالي الرواتب الشهرية</div><div class="stat-value sm">${money(totWage)}</div></div>` : ''}
      <div class="stat-card ${empAlerts.length ? 'danger' : 'success'}"><div class="stat-label">وثائق/عقود تنتهي خلال ${EMPF.alerts.window || 60} يوم</div><div class="stat-value">${empAlerts.length}</div></div>
      <div class="stat-card warning" onclick="goPage('leaves')"><div class="stat-label">إجازات بانتظار الاعتماد</div><div class="stat-value">${EMPF.alerts.pending_leaves || 0}</div></div>
    </div>
    ${empAlerts.length ? `<div class="card tight"><div class="card-header"><h3 class="card-title">⚠ تنبيهات</h3></div><table><tbody>${empAlerts.map(a => `<tr onclick="empProfile(${a.id})"><td><strong>${esc(a.name)}</strong></td><td>${esc(a.what)}</td><td>${dShort(a.date)}</td><td>${a.days_left < 0 ? pill('منتهية منذ ' + (-a.days_left) + ' يوم', 'bad') : pill('بعد ' + a.days_left + ' يوم', a.days_left <= 14 ? 'bad' : 'warn')}</td></tr>`).join('')}</tbody></table></div>` : ''}
    <div class="tabs">${tab('active', 'الحاليون', active.length)}${tab('terminated', 'انتهت خدمتهم', EMPS.length - active.length)}${tab('all', 'الكل', EMPS.length)}</div>
    <div class="card tight">${list.length ? `<div class="tbl-wrap"><table><thead><tr><th>الموظف</th><th>القسم / المسمى</th><th>الجنسية</th><th>المباشرة</th><th>الهوية/الإقامة</th><th>العقد</th>${showPay ? '<th>الراتب الشامل</th>' : ''}<th>حساب الدخول</th><th>الحالة</th></tr></thead><tbody>
      ${list.map(e => `<tr onclick="empProfile(${e.id})"><td><strong>${esc(e.full_name)}</strong><br><small class="muted">${esc(e.emp_no || '')}</small></td>
        <td>${esc(e.department || '—')}<br><small class="muted">${esc(e.job_title || '')}</small></td><td>${esc(e.nationality || (e.is_saudi ? 'سعودي' : '—'))}</td>
        <td>${dShort(e.hire_date)}</td><td>${expiryCell(e.id_expiry)}</td><td>${e.contract_type === 'indefinite' ? 'غير محدد المدة' : expiryCell(e.contract_end)}</td>
        ${showPay ? `<td>${money(e.wage)}</td>` : ''}<td>${e.username ? `<span dir="ltr">${esc(e.username)}</span>` : '<span class="muted">—</span>'}</td>
        <td>${pill(EMP_ST[e.status] || e.status, e.status === 'active' ? 'ok' : e.status === 'terminated' ? 'bad' : 'warn')}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">لا يوجد موظفون — ابدأ بإضافة الفريق</div>'}</div>`);
}
async function empEditor(id) {
  if (!EMPS.length) await loadEmps();
  const e = id ? await capi('/hr/employees/' + id) : { is_saudi: 1, gosi_registered: 1, gosi_category: 'legacy', contract_type: 'fixed', status: 'active' };
  if (!CRM.users.length) await loadUsersLite();
  const showPay = can('payroll', 'edit') || (can('payroll') && !id);
  const usersOpt = `<option value=""></option>` + (CRM.users || []).map(u => `<option value="${u.id}" ${String(e.user_id) === String(u.id) ? 'selected' : ''}>${esc(u.full_name)} (${esc(u.username)})</option>`).join('');
  openModal(id ? `تعديل — ${e.full_name}` : 'موظف جديد', `
    <h4 class="sub-h first">البيانات الأساسية</h4>
    <div class="form-row three">${fld('em-name', 'الاسم الكامل *', e.full_name)}${fld('em-phone', 'الجوال', e.phone, 'text', 'dir="ltr"')}${fld('em-email', 'البريد', e.email, 'email', 'dir="ltr"')}</div>
    <div class="form-row four">${sel('em-saudi', 'سعودي؟', { 1: 'سعودي', 0: 'غير سعودي' }, e.is_saudi ? 1 : 0)}${fld('em-nat', 'الجنسية', e.nationality)}${sel('em-gender', 'الجنس', { '': '', m: 'ذكر', f: 'أنثى' }, e.gender || '')}${sel('em-status', 'الحالة', EMP_ST, e.status)}</div>
    <div class="form-row four">${fld('em-idn', 'رقم الهوية/الإقامة', e.id_number, 'text', 'dir="ltr"')}${fld('em-idx', 'انتهاء الهوية/الإقامة', (e.id_expiry || '').slice(0, 10), 'date')}${fld('em-pp', 'رقم الجواز', e.passport_no, 'text', 'dir="ltr"')}${fld('em-ppx', 'انتهاء الجواز', (e.passport_expiry || '').slice(0, 10), 'date')}</div>
    <h4 class="sub-h">الوظيفة والعقد</h4>
    <div class="form-row four">${fld('em-dept', 'القسم', e.department, 'text', 'list="dept-list"')}${fld('em-title', 'المسمى الوظيفي', e.job_title)}<div class="form-group"><label class="form-label">المدير المباشر</label><select id="em-mgr" class="form-select">${empOptions(e.manager_id)}</select></div>${fld('em-loc', 'مقر العمل', e.work_location)}</div>
    <datalist id="dept-list">${['الإدارة', 'خدمة العملاء', 'المبيعات', 'المالية', 'العمليات', 'الإشراف', 'التصميم', 'المصنع', 'المستودعات', 'الضيافة', 'المشتريات'].map(d => `<option value="${d}">`).join('')}</datalist>
    <div class="form-row four">${fld('em-hire', 'تاريخ المباشرة *', (e.hire_date || '').slice(0, 10), 'date')}${fld('em-prob', 'نهاية التجربة', (e.probation_end || '').slice(0, 10), 'date', 'title="تُحسب تلقائياً 90 يوم لو تركتها فاضية"')}${sel('em-ctype', 'نوع العقد', { fixed: 'محدد المدة', indefinite: 'غير محدد المدة' }, e.contract_type)}${fld('em-cend', 'نهاية العقد', (e.contract_end || '').slice(0, 10), 'date')}</div>
    ${showPay ? `<h4 class="sub-h">الراتب والتأمينات 🔒</h4>
    <div class="form-row four">${fld('em-basic', 'الراتب الأساسي', e.basic_salary, 'number')}${fld('em-house', 'بدل السكن', e.housing_allowance, 'number')}${fld('em-trans', 'بدل النقل', e.transport_allowance, 'number')}${fld('em-other', 'بدلات أخرى', e.other_allowances, 'number')}</div>
    <div class="form-row four">${fld('em-bank', 'البنك', e.bank_name)}${fld('em-iban', 'الآيبان', e.iban, 'text', 'dir="ltr"')}${sel('em-gosi', 'مسجّل في التأمينات', { 1: 'نعم', 0: 'لا' }, e.gosi_registered ? 1 : 0)}${sel('em-gcat', 'فئة التأمينات (للسعودي)', { legacy: 'مسجّل قبل 3-7-2024', new: 'مسجّل من 3-7-2024' }, e.gosi_category)}</div>` : ''}
    <h4 class="sub-h">رصيد الإجازات</h4>
    <div class="form-row">${fld('em-lob', 'الرصيد الافتتاحي (يوم)', e.leave_opening_balance ?? 0, 'number', 'step="0.5"')}${fld('em-lod', 'كما في تاريخ', (e.leave_opening_date || '').slice(0, 10), 'date')}</div>
    <p class="muted small">للموظف الحالي: اكتب رصيده المتبقي اليوم (من سجلاتكم) واترك التاريخ فاضي — النظام يحسب الاستحقاق من اليوم: ٢١ يوم سنوياً، و٣٠ يوم بعد ٥ سنوات خدمة (م١٠٩).</p>
    ${e.status === 'terminated' || id ? `<div class="form-row">${fld('em-tdate', 'تاريخ انتهاء الخدمة', (e.termination_date || '').slice(0, 10), 'date')}${fld('em-treason', 'سبب الانتهاء', e.termination_reason)}</div>` : ''}
    <div class="form-row"><div class="form-group"><label class="form-label">حساب الدخول للنظام</label><select id="em-user" class="form-select">${usersOpt}</select></div><div class="form-group"><label class="form-label">ملاحظات</label><input id="em-notes" class="form-input" value="${esc(e.notes || '')}"></div></div>`,
    `<button class="btn" onclick="empSave(${id || 'null'}, ${showPay})">حفظ</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
  document.querySelector('.modal').classList.add('wide');
}
async function empSave(id, showPay) {
  const d = {
    full_name: val('em-name'), phone: val('em-phone'), email: val('em-email'), is_saudi: val('em-saudi'), nationality: val('em-nat'), gender: val('em-gender'),
    status: val('em-status'), id_number: val('em-idn'), id_expiry: val('em-idx'), passport_no: val('em-pp'), passport_expiry: val('em-ppx'),
    department: val('em-dept'), job_title: val('em-title'), manager_id: val('em-mgr'), work_location: val('em-loc'), hire_date: val('em-hire'),
    probation_end: val('em-prob'), contract_type: val('em-ctype'), contract_end: val('em-cend'), leave_opening_balance: val('em-lob'),
    leave_opening_date: val('em-lod'), user_id: val('em-user'), notes: val('em-notes'),
  };
  if (document.getElementById('em-tdate')) { d.termination_date = val('em-tdate'); d.termination_reason = val('em-treason'); }
  if (showPay) Object.assign(d, { basic_salary: val('em-basic'), housing_allowance: val('em-house'), transport_allowance: val('em-trans'), other_allowances: val('em-other'), bank_name: val('em-bank'), iban: val('em-iban'), gosi_registered: val('em-gosi'), gosi_category: val('em-gcat') });
  if (!id && !d.leave_opening_date) delete d.leave_opening_date;
  try {
    const r = id ? await capi('/hr/employees/' + id, 'PUT', d) : await capi('/hr/employees', 'POST', d);
    closeModal(); toast('تم الحفظ', 'success'); await renderEmployees(); empProfile(r.id || id);
  } catch (e) { toast(e.message, 'error'); }
}
async function empProfile(id) {
  try {
    const e = await capi('/hr/employees/' + id);
    const a = e.annual;
    const payTab = e.eos !== undefined;
    const body = `
      <div class="detail-grid">
        <div class="detail-item"><strong>القسم / المسمى</strong>${esc(e.department || '—')} — ${esc(e.job_title || '')}</div>
        <div class="detail-item"><strong>المدير المباشر</strong>${esc(e.manager_name || '—')}</div>
        <div class="detail-item"><strong>المباشرة</strong>${dShort(e.hire_date)}</div>
        <div class="detail-item"><strong>الجوال</strong>${phoneCell(e.phone)}</div>
        <div class="detail-item"><strong>الهوية/الإقامة</strong><span dir="ltr">${esc(e.id_number || '—')}</span> ${e.id_expiry ? '· ' + expiryCell(e.id_expiry) : ''}</div>
        <div class="detail-item"><strong>العقد</strong>${e.contract_type === 'indefinite' ? 'غير محدد المدة' : 'ينتهي ' + expiryCell(e.contract_end)}</div>
        <div class="detail-item"><strong>نهاية التجربة</strong>${dShort(e.probation_end)}</div>
        <div class="detail-item"><strong>حساب الدخول</strong>${e.username ? `<span dir="ltr">${esc(e.username)}</span>` : (can('users', 'edit') ? `<a class="link" onclick="empCreateUser(${e.id})">إنشاء حساب</a>` : '—')}</div>
      </div>
      <div class="stats-grid" style="margin-top:14px">
        <div class="stat-card success"><div class="stat-label">رصيد السنوية المتاح</div><div class="stat-value">${a.available}</div><div class="stat-sub">مستحق ${a.accrued} · مأخوذ ${a.taken} · معلّق ${a.pending}</div></div>
        <div class="stat-card"><div class="stat-label">مرضية آخر 12 شهر</div><div class="stat-value">${e.sick.used}</div><div class="stat-sub">بأجر كامل متبقي ${e.sick.full_pay_left}</div></div>
        ${payTab ? `<div class="stat-card accent"><div class="stat-label">الراتب الشامل</div><div class="stat-value sm">${money(e.wage)}</div><div class="stat-sub">أساسي ${money(e.basic_salary)}</div></div>
        <div class="stat-card warning"><div class="stat-label">مكافأة نهاية الخدمة (تقدير)</div><div class="stat-value sm">${money(e.eos.termination)}</div><div class="stat-sub">عند الاستقالة ${money(e.eos.resignation)} · ${e.eos.years} سنة</div></div>` : ''}
      </div>
      ${e.custody.length ? `<h4 class="sub-h">🔑 العُهد</h4><table><tbody>${e.custody.map(c => `<tr><td>${esc(c.asset_code)}</td><td>${esc(c.name)} ${esc(c.plate_no || '')}</td><td>منذ ${dShort(c.custody_since)}</td></tr>`).join('')}</tbody></table>` : ''}
      <h4 class="sub-h">🌿 الإجازات</h4>${e.leaves.length ? `<table><tbody>${e.leaves.map(l => `<tr><td>${esc((LV_TYPES[l.leave_type] || {}).label || l.leave_type)}</td><td>${dShort(l.start_date)} ← ${dShort(l.end_date)}</td><td>${l.days} يوم</td><td>${pill(LV_STATUS[l.status], LV_CLS[l.status])}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">لا يوجد</p>'}
      ${payTab && e.advances.length ? `<h4 class="sub-h">السلف</h4><table><tbody>${e.advances.map(x => `<tr><td>${money(x.amount)}</td><td>القسط ${money(x.monthly_installment)}</td><td>المتبقي ${money(x.remaining)}</td><td>${x.status === 'settled' ? pill('مسددة', 'ok') : pill('قائمة', 'warn')}</td></tr>`).join('')}</tbody></table>` : ''}
      ${payTab && e.payslips.length ? `<h4 class="sub-h">آخر المسيّرات</h4><table><tbody>${e.payslips.map(p => `<tr><td>${esc(p.period)}</td><td>${money(p.gross)}</td><td>- ${money(p.total_ded)}</td><td><strong>${money(p.net)}</strong></td></tr>`).join('')}</tbody></table>` : ''}
      ${payTab ? '<p class="muted small">مكافأة نهاية الخدمة تقدير على الأجر الفعلي الحالي وفق م٨٤ و م٨٥ — لا تشمل فترات الإجازة بدون راتب الطويلة ولا الحالات الخاصة (م٨٠/م٨١/م٨٧).</p>' : ''}`;
    const f = [
      can('employees', 'edit') ? `<button class="btn" onclick="closeModal();empEditor(${e.id})">تعديل</button>` : '',
      can('leaves', 'create') ? `<button class="btn btn-outline" onclick="leaveDialog(${e.id})">+ إجازة</button>` : '',
      can('payroll', 'create') ? `<button class="btn btn-outline" onclick="advanceDialog(${e.id})">+ سلفة</button>` : '',
      can('employees', 'delete') ? `<button class="btn btn-outline danger-t" onclick="empDelete(${e.id})">حذف</button>` : '',
      '<button class="btn btn-outline" onclick="closeModal()">إغلاق</button>'].join('');
    openModal(`👤 ${e.full_name}${e.emp_no ? ' — ' + e.emp_no : ''}`, body, f);
    document.querySelector('.modal').classList.add('wide');
  } catch (err) { toast(err.message, 'error'); }
}
async function empCreateUser(id) {
  const e = EMPS.find(x => x.id === id) || {};
  if (!ADM.roles) { try { const r = await capi('/admin/roles'); ADM.roles = r.roles; } catch (er) { return toast(er.message, 'error'); } }
  openModal('إنشاء حساب دخول', `${fld('cu-user', 'اسم الدخول (إنجليزي)', '', 'text', 'dir="ltr"')}<div class="form-group"><label class="form-label">الدور</label><select id="cu-role" class="form-select">${roleOptions('')}</select></div>`,
    `<button class="btn" onclick="empCreateUserSave(${id})">إنشاء</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
  CRM._newEmpName = e.full_name;
}
async function empCreateUserSave(id) {
  try {
    const r = await capi('/admin/users', 'POST', { username: val('cu-user'), full_name: CRM._newEmpName, role: val('cu-role'), employee_id: id });
    showCredentials(CRM._newEmpName, val('cu-user') || '', r.temp_password); loadUsersLite();
  } catch (e) { toast(e.message, 'error'); }
}
async function empDelete(id) {
  if (!confirm('حذف ملف الموظف نهائياً؟ (لو له سجلات، استخدم «انتهت خدمته» بدل الحذف)')) return;
  try { await capi('/hr/employees/' + id, 'DELETE'); closeModal(); renderEmployees(); } catch (e) { toast(e.message, 'error'); }
}

// ===================================================================
// الإجازات
// ===================================================================
let LVF = { status: 'pending' };
async function renderLeaves() {
  let d;
  try { d = await capi('/hr/leaves'); } catch (e) { return setContent(`<div class="empty">${esc(e.message)}</div>`); }
  LV_TYPES = d.types;
  const rows = d.rows;
  const cnt = {}; rows.forEach(r => cnt[r.status] = (cnt[r.status] || 0) + 1);
  const T = todayISO();
  const now = rows.filter(r => r.status === 'approved' && r.start_date <= T && r.end_date >= T);
  const list = LVF.status === 'all' ? rows : LVF.status === 'now' ? now : rows.filter(r => r.status === LVF.status);
  const tab = (k, l, n) => `<div class="tab ${LVF.status === k ? 'active' : ''}" onclick="LVF.status='${k}';renderLeaves()">${l} <span class="cnt">${n || 0}</span></div>`;
  pageShell('🌿 الإجازات', can('leaves', 'create') ? '<button class="btn" onclick="leaveDialog()">+ تسجيل إجازة</button>' : '',
    `<div class="tabs">${tab('pending', 'بانتظار الاعتماد', cnt.pending)}${tab('now', 'في إجازة اليوم', now.length)}${tab('approved', 'معتمدة', cnt.approved)}${tab('rejected', 'مرفوضة', cnt.rejected)}${tab('all', 'الكل', rows.length)}</div>
    <div class="card tight">${list.length ? `<div class="tbl-wrap"><table><thead><tr><th>الموظف</th><th>النوع</th><th>من</th><th>إلى</th><th>الأيام</th><th>السبب</th><th>طلبها</th><th>الحالة</th><th></th></tr></thead><tbody>
    ${list.map(l => `<tr><td><a class="link" onclick="empProfile(${l.employee_id})">${esc(l.employee_name)}</a><br><small class="muted">${esc(l.department || '')}</small></td><td>${esc(l.type_label)}</td><td>${dShort(l.start_date)}</td><td>${dShort(l.end_date)}</td><td>${l.days}</td>
      <td class="small">${esc(l.reason || '')}</td><td class="small">${esc(l.requested_by_name || '')}</td>
      <td>${pill(LV_STATUS[l.status], LV_CLS[l.status])}${l.decided_by_name ? `<br><small class="muted">${esc(l.decided_by_name)}</small>` : ''}${l.decision_note ? `<br><small class="muted">${esc(l.decision_note)}</small>` : ''}</td>
      <td class="nowrap">${can('leaves', 'edit') && l.status === 'pending' ? `<button class="btn btn-sm btn-success" onclick="leaveDecide(${l.id},'approved')">اعتماد</button> <button class="btn btn-sm btn-outline danger-t" onclick="leaveDecide(${l.id},'rejected')">رفض</button>` : ''}
        ${can('leaves', 'delete') && ['pending', 'approved'].includes(l.status) ? ` <button class="btn btn-sm btn-outline" onclick="leaveCancel(${l.id})">إلغاء</button>` : ''}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">لا يوجد</div>'}</div>
    <p class="muted small">المرجع (نظام العمل بعد تعديلات 2025): السنوية 21 يوم و30 بعد 5 سنوات (م109) · المرضية 30 بأجر كامل ثم 60 بثلاثة أرباع ثم 30 بدون أجر في السنة (م117) · الزواج 5 · المولود 3 · وفاة الزوج/الأصل/الفرع 5 · وفاة الأخ/الأخت 2 · الوضع 12 أسبوعاً.</p>`);
}
async function leaveDialog(empId) {
  await loadEmps();
  if (!Object.keys(LV_TYPES).length) { try { LV_TYPES = (await capi('/hr/leaves?status=x')).types; } catch (e) {} }
  openModal('تسجيل إجازة', leaveForm('lv', true) + (can('leaves', 'edit') ? '<label class="chk"><input type="checkbox" id="lv-approve" checked> اعتمادها مباشرة</label>' : ''),
    `<button class="btn" onclick="leaveSave()">حفظ</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
  if (empId) document.getElementById('lv-emp').value = empId;
  lvDays('lv');
}
async function leaveSave() {
  try {
    await capi('/hr/leaves', 'POST', { employee_id: val('lv-emp'), leave_type: val('lv-type'), start_date: val('lv-from'), end_date: val('lv-to'), days: val('lv-days'), reason: val('lv-reason'), approve_now: document.getElementById('lv-approve')?.checked });
    closeModal(); toast('تم', 'success'); if (currentPage === 'leaves') renderLeaves();
  } catch (e) { toast(e.message, 'error'); }
}
async function leaveDecide(id, dec) {
  const note = dec === 'rejected' ? prompt('سبب الرفض') : '';
  if (dec === 'rejected' && note === null) return;
  try { await capi(`/hr/leaves/${id}/decision`, 'POST', { decision: dec, note }); renderLeaves(); } catch (e) { toast(e.message, 'error'); }
}
async function leaveCancel(id) {
  if (!confirm('إلغاء الإجازة؟')) return;
  try { await capi('/hr/leaves/' + id, 'DELETE'); renderLeaves(); } catch (e) { toast(e.message, 'error'); }
}

// ===================================================================
// الرواتب والسلف
// ===================================================================
let PR = { tab: 'runs' };
async function renderPayroll() {
  const tabs = `<div class="tabs"><div class="tab ${PR.tab === 'runs' ? 'active' : ''}" onclick="PR.tab='runs';renderPayroll()">💵 المسيّرات الشهرية</div><div class="tab ${PR.tab === 'adv' ? 'active' : ''}" onclick="PR.tab='adv';renderPayroll()">💳 السلف</div></div>`;
  if (PR.tab === 'adv') {
    const adv = await capi('/hr/advances');
    return pageShell('الرواتب والسلف', can('payroll', 'create') ? '<button class="btn" onclick="advanceDialog()">+ سلفة</button>' : '', tabs + `
      <div class="card tight">${adv.length ? `<table><thead><tr><th>الموظف</th><th>المبلغ</th><th>القسط الشهري</th><th>يبدأ الخصم</th><th>المتبقي</th><th>الحالة</th><th>السبب</th><th></th></tr></thead><tbody>
      ${adv.map(a => `<tr><td>${esc(a.employee_name)}</td><td>${money(a.amount)}</td><td>${money(a.monthly_installment)}</td><td>${esc(a.start_period)}</td><td><strong>${money(a.remaining)}</strong></td><td>${a.status === 'settled' ? pill('مسددة', 'ok') : pill('قائمة', 'warn')}</td><td class="small">${esc(a.reason || '')}</td>
      <td>${can('payroll', 'delete') && a.remaining >= a.amount ? `<button class="btn btn-sm btn-outline danger-t" onclick="advDel(${a.id})">حذف</button>` : ''}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">لا توجد سلف</div>'}</div>
      <p class="muted small">القسط يُخصم تلقائياً في مسيّر كل شهر، ويُنزّل من رصيد السلفة عند تأشير المسيّر «مصروف».</p>`);
  }
  const runs = await capi('/hr/payroll');
  const next = (() => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); })();
  pageShell('الرواتب والسلف', can('payroll', 'create') ? `<input type="month" id="pr-period" class="form-input" style="width:auto" value="${next}"> <button class="btn" onclick="payrollCreate()">+ توليد مسيّر</button>` : '', tabs + `
    <div class="card tight">${runs.length ? `<table><thead><tr><th>الشهر</th><th>الموظفون</th><th>الإجمالي</th><th>الصافي المستحق</th><th>تأمينات صاحب العمل</th><th>الحالة</th></tr></thead><tbody>
    ${runs.map(r => `<tr onclick="payrollOpen(${r.id})"><td><strong>${esc(r.period)}</strong></td><td>${r.employees}</td><td>${money(r.total_gross)}</td><td><strong>${money(r.total_net)}</strong></td><td>${money(r.total_gosi_employer)}</td>
      <td>${pill({ draft: 'مسودة', approved: 'معتمد', paid: 'مصروف' }[r.status], r.status === 'paid' ? 'ok' : r.status === 'approved' ? 'gold' : 'warn')}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">لا توجد مسيّرات — اختر الشهر واضغط «توليد مسيّر»</div>'}</div>
    <p class="muted small">التوليد يسحب الرواتب من ملفات الموظفين ويحسب تلقائياً: أيام الشهر للمباشر/المنتهية خدمته، خصم الإجازة بدون راتب (الراتب الشامل ÷ 30)، قسط السلف، وحصة التأمينات (على الأساسي + السكن بحد ${money(45000)}). العمل الإضافي والمكافآت والجزاءات تُدخل يدوياً، وكذلك خصم المرضية بعد أول 30 يوم.</p>`);
}
async function payrollCreate() {
  try { const r = await capi('/hr/payroll', 'POST', { period: val('pr-period') }); toast('تم توليد المسيّر', 'success'); payrollOpen(r.id); } catch (e) { toast(e.message, 'error'); }
}
let RUN = null;
async function payrollOpen(id) {
  try { RUN = await capi('/hr/payroll/' + id); } catch (e) { return toast(e.message, 'error'); }
  const r = RUN, draft = r.status === 'draft', ed = draft && can('payroll', 'edit');
  const sum = k => r.lines.reduce((s, l) => s + (+l[k] || 0), 0);
  const cell = (l, k) => ed ? `<input class="pr-in" type="number" step="0.01" value="${+l[k] || ''}" onchange="prLine(${l.id},'${k}',this.value)">` : (+l[k] ? money(l[k]).replace(' ر.س', '') : '—');
  const acts = [
    `<button class="btn btn-outline" onclick="window.open('/dashboard/print_payroll.html?id=${r.id}','_blank')">🖨 طباعة المسيّر والقسائم</button>`,
    ed ? `<button class="btn btn-outline" onclick="prAct(${r.id},'regenerate')">↻ إعادة التوليد</button>` : '',
    ed ? `<button class="btn btn-success" onclick="prAct(${r.id},'approve')">✓ اعتماد</button>` : '',
    r.status === 'approved' && can('payroll', 'edit') ? `<button class="btn btn-outline" onclick="prAct(${r.id},'reopen')">إعادة فتح</button> <button class="btn btn-success" onclick="prAct(${r.id},'paid')">💸 تم الصرف</button>` : '',
    draft && can('payroll', 'delete') ? `<button class="btn btn-outline danger-t" onclick="prDel(${r.id})">حذف</button>` : '',
    `<button class="btn btn-outline" onclick="renderPayroll()">رجوع</button>`].join(' ');
  pageShell(`💵 مسيّر رواتب ${esc(r.period)} ${pill({ draft: 'مسودة', approved: 'معتمد', paid: 'مصروف' }[r.status], r.status === 'paid' ? 'ok' : 'warn')}`, acts, `
    <div class="stats-grid">
      <div class="stat-card"><div class="stat-label">الإجمالي</div><div class="stat-value sm">${money(sum('gross'))}</div></div>
      <div class="stat-card danger"><div class="stat-label">الخصومات</div><div class="stat-value sm">${money(sum('total_ded'))}</div></div>
      <div class="stat-card success"><div class="stat-label">الصافي للتحويل</div><div class="stat-value sm">${money(sum('net'))}</div></div>
      <div class="stat-card accent"><div class="stat-label">تكلفة التأمينات على المنشأة</div><div class="stat-value sm">${money(sum('gosi_employer'))}</div></div>
    </div>
    ${ed ? '<div class="hint">عدّل الخانات مباشرة (عمل إضافي، مكافأة، غياب، جزاءات، خصومات أخرى) — يُحفظ تلقائياً.</div>' : ''}
    <div class="card tight"><div class="tbl-wrap"><table class="pr-table"><thead><tr><th>الموظف</th><th>أيام</th><th>الأساسي</th><th>السكن</th><th>النقل</th><th>أخرى</th><th>إضافي</th><th>مكافأة</th><th>الإجمالي</th>
      <th>بدون راتب</th><th>غياب</th><th>جزاءات</th><th>سلفة</th><th>أخرى</th><th>تأمينات</th><th>الصافي</th></tr></thead><tbody>
      ${r.lines.map(l => `<tr><td><strong>${esc(l.full_name)}</strong><br><small class="muted">${esc(l.department || '')}</small></td><td>${l.days_worked}</td>
        <td>${money(l.basic).replace(' ر.س', '')}</td><td>${(+l.housing || 0).toLocaleString()}</td><td>${(+l.transport || 0).toLocaleString()}</td><td>${(+l.other_allow || 0).toLocaleString()}</td>
        <td>${cell(l, 'overtime')}</td><td>${cell(l, 'bonus')}</td><td><strong id="g-${l.id}">${money(l.gross).replace(' ر.س', '')}</strong></td>
        <td>${cell(l, 'unpaid_leave_ded')}${l.unpaid_leave_days ? `<br><small class="muted">${l.unpaid_leave_days} يوم</small>` : ''}</td><td>${cell(l, 'absence_ded')}</td><td>${cell(l, 'penalty_ded')}</td><td>${cell(l, 'advance_ded')}</td><td>${cell(l, 'other_ded')}</td><td>${cell(l, 'gosi_employee')}</td>
        <td><strong id="n-${l.id}">${money(l.net)}</strong></td></tr>`).join('')}</tbody></table></div></div>`);
}
async function prLine(lid, k, v) {
  try {
    const r = await capi('/hr/payroll/lines/' + lid, 'PUT', { [k]: v });
    document.getElementById('g-' + lid).textContent = money(r.line.gross).replace(' ر.س', '');
    document.getElementById('n-' + lid).textContent = money(r.line.net);
  } catch (e) { toast(e.message, 'error'); }
}
async function prAct(id, act) {
  const msg = { approve: 'اعتماد المسيّر؟ بعدها ما يتعدل إلا بإعادة فتحه.', paid: 'تأكيد صرف الرواتب؟ تُخصم أقساط السلف من أرصدتها.', regenerate: 'إعادة التوليد تمسح أي تعديل يدوي. متأكد؟', reopen: 'إعادة فتح المسيّر للتعديل؟' }[act];
  if (msg && !confirm(msg)) return;
  try { await capi(`/hr/payroll/${id}/${act}`, 'POST', {}); toast('تم', 'success'); payrollOpen(id); } catch (e) { toast(e.message, 'error'); }
}
async function prDel(id) { if (!confirm('حذف المسيّر؟')) return; try { await capi('/hr/payroll/' + id, 'DELETE'); renderPayroll(); } catch (e) { toast(e.message, 'error'); } }
async function advanceDialog(empId) {
  await loadEmps();
  const nm = (() => { const d = new Date(); d.setMonth(d.getMonth() + 1); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); })();
  openModal('سلفة جديدة', `<div class="form-group"><label class="form-label">الموظف *</label><select id="ad-emp" class="form-select">${empOptions(empId || '')}</select></div>
    <div class="form-row three">${fld('ad-amt', 'المبلغ *', '', 'number')}${fld('ad-inst', 'القسط الشهري *', '', 'number')}${fld('ad-start', 'يبدأ الخصم من شهر', nm, 'month')}</div>
    ${fld('ad-reason', 'السبب')}`,
    `<button class="btn" onclick="advSave()">حفظ</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
}
async function advSave() {
  try { await capi('/hr/advances', 'POST', { employee_id: val('ad-emp'), amount: val('ad-amt'), monthly_installment: val('ad-inst'), start_period: val('ad-start'), reason: val('ad-reason') }); closeModal(); toast('تم', 'success'); if (currentPage === 'payroll') { PR.tab = 'adv'; renderPayroll(); } } catch (e) { toast(e.message, 'error'); }
}
async function advDel(id) { if (!confirm('حذف السلفة؟')) return; try { await capi('/hr/advances/' + id, 'DELETE'); renderPayroll(); } catch (e) { toast(e.message, 'error'); } }

// ===================================================================
// المهام
// ===================================================================
let TK = { status: 'open', who: '' };
async function renderTasks() {
  if (!CRM.users.length) await loadUsersLite();
  let rows;
  try { rows = await capi(`/hr/tasks?status=${TK.status === 'all' ? '' : TK.status}${TK.who ? '&assignee=' + TK.who : ''}`); } catch (e) { return setContent(`<div class="empty">${esc(e.message)}</div>`); }
  const T = todayISO();
  const late = rows.filter(t => ['todo', 'in_progress'].includes(t.status) && t.due_date && t.due_date < T);
  const tab = (k, l) => `<div class="tab ${TK.status === k ? 'active' : ''}" onclick="TK.status='${k}';renderTasks()">${l}</div>`;
  pageShell('✅ المهام', `<select class="form-select inline" onchange="TK.who=this.value;renderTasks()"><option value="">كل الموظفين</option>${usersOptions(TK.who)}</select>
    ${can('tasks', 'create') ? '<button class="btn" onclick="taskEditor()">+ مهمة</button>' : ''}`,
    `${late.length ? `<div class="warn-box">⏰ ${late.length} مهمة متأخرة عن موعدها</div>` : ''}
    <div class="tabs">${tab('open', 'المفتوحة')}${tab('done', 'المنجزة')}${tab('all', 'الكل')}</div>
    <div class="card tight">${rows.length ? `<div class="tbl-wrap"><table><thead><tr><th>المهمة</th><th>المسؤول</th><th>الأولوية</th><th>الموعد</th><th>الحالة</th><th>أسندها</th><th></th></tr></thead><tbody>
    ${rows.map(t => `<tr><td><strong>${esc(t.title)}</strong>${t.related ? ` <small class="muted">· ${esc(t.related)}</small>` : ''}${t.description ? `<br><small class="muted">${esc(t.description)}</small>` : ''}${t.completion_note ? `<br><small>✓ ${esc(t.completion_note)}</small>` : ''}</td>
      <td>${esc(t.assigned_name || '—')}</td><td>${pill(TASK_PR[t.priority] || t.priority, ['high', 'urgent'].includes(t.priority) ? 'bad' : '')}</td>
      <td>${t.due_date ? (late.includes(t) ? pill(dShort(t.due_date), 'bad') : dShort(t.due_date)) : '—'}</td>
      <td>${pill(TASK_ST[t.status], t.status === 'done' ? 'ok' : t.status === 'in_progress' ? 'gold' : t.status === 'cancelled' ? '' : 'warn')}</td><td class="small">${esc(t.assigned_by_name || '')}</td>
      <td class="nowrap">${can('tasks', 'edit') ? `<button class="btn btn-sm btn-outline" onclick='taskEditor(${JSON.stringify(t).replace(/'/g, "&#39;")})'>تعديل</button>` : ''} ${can('tasks', 'delete') ? `<button class="btn btn-sm btn-outline danger-t" onclick="taskDel(${t.id})">حذف</button>` : ''}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">لا توجد مهام</div>'}</div>`);
}
function taskEditor(t) {
  t = t || { priority: 'normal', status: 'todo', due_date: addDaysISO(2) };
  openModal(t.id ? 'تعديل مهمة' : 'مهمة جديدة', `${fld('tk-title', 'العنوان *', t.title)}
    <div class="form-group"><label class="form-label">التفاصيل</label><textarea id="tk-desc" class="form-textarea" rows="3">${esc(t.description || '')}</textarea></div>
    <div class="form-row"><div class="form-group"><label class="form-label">المسؤول *</label><select id="tk-to" class="form-select"><option value=""></option>${usersOptions(t.assigned_to)}</select></div>${fld('tk-due', 'الموعد', (t.due_date || '').slice(0, 10), 'date')}</div>
    <div class="form-row three">${sel('tk-pr', 'الأولوية', TASK_PR, t.priority)}${sel('tk-st', 'الحالة', TASK_ST, t.status)}${fld('tk-rel', 'مرتبطة بـ (عقد/مناسبة)', t.related)}</div>
    <p class="muted small">المهمة تظهر للموظف في «ملفي ومهامي» وفي لوحته الرئيسية.</p>`,
    `<button class="btn" onclick="taskSave(${t.id || 'null'})">حفظ</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
}
async function taskSave(id) {
  const d = { title: val('tk-title'), description: val('tk-desc'), assigned_to: val('tk-to'), due_date: val('tk-due'), priority: val('tk-pr'), status: val('tk-st'), related: val('tk-rel') };
  try { if (id) await capi('/hr/tasks/' + id, 'PUT', d); else await capi('/hr/tasks', 'POST', d); closeModal(); toast('تم', 'success'); renderTasks(); } catch (e) { toast(e.message, 'error'); }
}
async function taskDel(id) { if (!confirm('حذف المهمة؟')) return; try { await capi('/hr/tasks/' + id, 'DELETE'); renderTasks(); } catch (e) { toast(e.message, 'error'); } }

// ===================================================================
// الأصول والمعدات والسيارات
// ===================================================================
let AS = { cat: '', rows: [] };
async function renderAssets() {
  try { AS.rows = await capi('/assets'); } catch (e) { return setContent(`<div class="empty">${esc(e.message)}</div>`); }
  let al = { items: [] };
  try { al = await capi('/hr/alerts'); } catch (e) {}
  const aAl = al.items.filter(a => a.kind === 'asset');
  const all = AS.rows, list = AS.cat ? all.filter(a => a.category === AS.cat) : all;
  const live = all.filter(a => !['disposed', 'lost'].includes(a.status));
  const cnt = {}; all.forEach(a => cnt[a.category] = (cnt[a.category] || 0) + 1);
  const tab = (k, l, n) => `<div class="tab ${AS.cat === k ? 'active' : ''}" onclick="AS.cat='${k}';renderAssets()">${l} <span class="cnt">${n || 0}</span></div>`;
  const veh = AS.cat === 'vehicle';
  pageShell('🚗 الأصول والمعدات والسيارات', can('assets', 'create') ? '<button class="btn" onclick="assetEditor()">+ أصل</button>' : '',
    `<div class="stats-grid">
      <div class="stat-card"><div class="stat-label">أصول في الخدمة</div><div class="stat-value">${live.length}</div></div>
      <div class="stat-card accent"><div class="stat-label">تكلفة الشراء</div><div class="stat-value sm">${money(live.reduce((s, a) => s + (+a.purchase_price || 0), 0))}</div></div>
      <div class="stat-card"><div class="stat-label">القيمة الدفترية (تقديرية)</div><div class="stat-value sm">${money(live.reduce((s, a) => s + (+a.book_value || 0), 0))}</div></div>
      <div class="stat-card ${aAl.length ? 'danger' : 'success'}"><div class="stat-label">وثائق/صيانات مستحقة</div><div class="stat-value">${aAl.length}</div></div>
    </div>
    ${aAl.length ? `<div class="card tight"><div class="card-header"><h3 class="card-title">⚠ تنبيهات الأصول والسيارات</h3></div><table><tbody>${aAl.map(a => `<tr onclick="assetView(${a.id})"><td><strong>${esc(a.name)}</strong></td><td>${esc(a.what)}</td><td>${dShort(a.date)}</td><td>${a.days_left < 0 ? pill('متأخر ' + (-a.days_left) + ' يوم', 'bad') : pill('بعد ' + a.days_left + ' يوم', a.days_left <= 14 ? 'bad' : 'warn')}</td></tr>`).join('')}</tbody></table></div>` : ''}
    <div class="tabs">${tab('', 'الكل', all.length)}${Object.entries(ASSET_CAT).map(([k, l]) => tab(k, l, cnt[k])).join('')}</div>
    <div class="card tight">${list.length ? `<div class="tbl-wrap"><table><thead><tr><th>الكود</th><th>الأصل</th>${veh ? '<th>اللوحة</th><th>الاستمارة</th><th>التأمين</th><th>الفحص</th><th>العداد</th>' : '<th>التصنيف</th><th>الموقع</th><th>تاريخ الشراء</th><th>القيمة</th>'}<th>العهدة</th><th>الحالة</th></tr></thead><tbody>
    ${list.map(a => `<tr onclick="assetView(${a.id})"><td><strong>${esc(a.asset_code)}</strong></td><td>${esc(a.name)}<br><small class="muted">${esc([a.brand, a.model].filter(Boolean).join(' '))}</small></td>
      ${veh ? `<td>${esc(a.plate_no || '—')}</td><td>${expiryCell(a.registration_expiry)}</td><td>${expiryCell(a.insurance_expiry)}</td><td>${expiryCell(a.inspection_expiry)}</td><td>${a.odometer ? (+a.odometer).toLocaleString() + ' كم' : '—'}</td>`
        : `<td>${esc(ASSET_CAT[a.category] || '')}</td><td>${esc(a.location || '—')}</td><td>${dShort(a.purchase_date)}</td><td>${a.purchase_price ? money(a.purchase_price) : '—'}${a.book_value != null ? `<br><small class="muted">دفترية ${money(a.book_value)}</small>` : ''}</td>`}
      <td>${esc(a.custodian_name || '—')}</td><td>${pill(ASSET_ST[a.status] || a.status, a.status === 'active' ? 'ok' : ['disposed', 'lost'].includes(a.status) ? 'bad' : 'warn')}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">لا توجد أصول مسجلة</div>'}</div>`);
}
async function assetEditor(id) {
  await loadEmps();
  const a = id ? await capi('/assets/' + id) : { category: AS.cat || 'equipment', status: 'active' };
  openModal(id ? `تعديل ${a.asset_code}` : 'أصل جديد', `
    <div class="form-row three">${sel('as-cat', 'التصنيف *', ASSET_CAT, a.category, 'onchange="document.getElementById(\'as-veh\').hidden=this.value!==\'vehicle\'"')}${fld('as-name', 'الاسم *', a.name, 'text', 'placeholder="مثال: هايلكس نقل / مكينة CNC / لابتوب التصميم"')}${sel('as-st', 'الحالة', ASSET_ST, a.status)}</div>
    <div class="form-row three">${fld('as-brand', 'الماركة', a.brand)}${fld('as-model', 'الموديل', a.model)}${fld('as-serial', 'الرقم التسلسلي', a.serial_no, 'text', 'dir="ltr"')}</div>
    <div class="form-row four">${fld('as-pdate', 'تاريخ الشراء', (a.purchase_date || '').slice(0, 10), 'date')}${fld('as-price', 'سعر الشراء', a.purchase_price, 'number')}${fld('as-life', 'العمر الإنتاجي (سنوات)', a.useful_life_years, 'number', 'title="للإهلاك بالقسط الثابت"')}${fld('as-sup', 'المورد', a.supplier)}</div>
    <div class="form-row three">${fld('as-loc', 'الموقع', a.location, 'text', 'placeholder="المصنع / المستودع / المكتب"')}${fld('as-war', 'انتهاء الضمان', (a.warranty_expiry || '').slice(0, 10), 'date')}${id ? '' : `<div class="form-group"><label class="form-label">العهدة لدى</label><select id="as-cust" class="form-select">${empOptions('')}</select></div>`}</div>
    <div id="as-veh" ${a.category === 'vehicle' ? '' : 'hidden'}><h4 class="sub-h">🚗 بيانات السيارة</h4>
      <div class="form-row four">${fld('as-plate', 'رقم اللوحة', a.plate_no)}${fld('as-vin', 'رقم الهيكل', a.vin, 'text', 'dir="ltr"')}${fld('as-year', 'سنة الصنع', a.year, 'number')}${fld('as-color', 'اللون', a.color)}</div>
      <div class="form-row four">${fld('as-reg', 'انتهاء الاستمارة', (a.registration_expiry || '').slice(0, 10), 'date')}${fld('as-ins', 'انتهاء التأمين', (a.insurance_expiry || '').slice(0, 10), 'date')}${fld('as-insp', 'انتهاء الفحص الدوري', (a.inspection_expiry || '').slice(0, 10), 'date')}${fld('as-auth', 'انتهاء تفويض القيادة', (a.authorization_expiry || '').slice(0, 10), 'date')}</div>
      <div class="form-row three">${fld('as-odo', 'قراءة العداد (كم)', a.odometer, 'number')}${fld('as-nkm', 'الصيانة القادمة عند (كم)', a.next_service_km, 'number')}${fld('as-ndate', 'أو بتاريخ', (a.next_service_date || '').slice(0, 10), 'date')}</div></div>
    ${a.category !== 'vehicle' ? `<div class="form-row">${fld('as-ndate2', 'موعد الصيانة القادمة', (a.next_service_date || '').slice(0, 10), 'date')}</div>` : ''}
    <div class="form-group"><label class="form-label">ملاحظات</label><textarea id="as-notes" class="form-textarea" rows="2">${esc(a.notes || '')}</textarea></div>`,
    `<button class="btn" onclick="assetSave(${id || 'null'})">حفظ</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
  document.querySelector('.modal').classList.add('wide');
}
async function assetSave(id) {
  const d = { category: val('as-cat'), name: val('as-name'), status: val('as-st'), brand: val('as-brand'), model: val('as-model'), serial_no: val('as-serial'),
    purchase_date: val('as-pdate'), purchase_price: val('as-price'), useful_life_years: val('as-life'), supplier: val('as-sup'), location: val('as-loc'),
    warranty_expiry: val('as-war'), notes: val('as-notes') };
  if (d.category === 'vehicle') Object.assign(d, { plate_no: val('as-plate'), vin: val('as-vin'), year: val('as-year'), color: val('as-color'), registration_expiry: val('as-reg'),
    insurance_expiry: val('as-ins'), inspection_expiry: val('as-insp'), authorization_expiry: val('as-auth'), odometer: val('as-odo'), next_service_km: val('as-nkm'), next_service_date: val('as-ndate') });
  else if (document.getElementById('as-ndate2')) d.next_service_date = val('as-ndate2');
  if (!id) d.custodian_id = val('as-cust');
  try {
    const r = id ? await capi('/assets/' + id, 'PUT', d) : await capi('/assets', 'POST', d);
    closeModal(); toast(r.asset_code ? 'تم تسجيل ' + r.asset_code : 'تم الحفظ', 'success'); await renderAssets(); assetView(r.id || id);
  } catch (e) { toast(e.message, 'error'); }
}
async function assetView(id) {
  try {
    const a = await capi('/assets/' + id);
    const veh = a.category === 'vehicle';
    const body = `
      <div class="detail-grid">
        <div class="detail-item"><strong>التصنيف</strong>${esc(ASSET_CAT[a.category] || '')}</div>
        <div class="detail-item"><strong>الحالة</strong>${pill(ASSET_ST[a.status] || a.status, a.status === 'active' ? 'ok' : 'warn')}</div>
        <div class="detail-item"><strong>الماركة / الموديل</strong>${esc([a.brand, a.model, a.year].filter(Boolean).join(' ') || '—')}</div>
        <div class="detail-item"><strong>${veh ? 'اللوحة / الهيكل' : 'الرقم التسلسلي'}</strong><span dir="ltr">${esc(veh ? [a.plate_no, a.vin].filter(Boolean).join(' / ') : a.serial_no || '—')}</span></div>
        <div class="detail-item"><strong>الشراء</strong>${dShort(a.purchase_date)} ${a.purchase_price ? '· ' + money(a.purchase_price) : ''}</div>
        <div class="detail-item"><strong>القيمة الدفترية</strong>${a.book_value != null ? money(a.book_value) : '—'}</div>
        <div class="detail-item"><strong>الموقع</strong>${esc(a.location || '—')}</div>
        <div class="detail-item"><strong>العهدة لدى</strong>${esc(a.custodian_name || '—')} ${a.custody_since ? '· منذ ' + dShort(a.custody_since) : ''}</div>
        ${veh ? `<div class="detail-item"><strong>الاستمارة</strong>${expiryCell(a.registration_expiry)}</div><div class="detail-item"><strong>التأمين</strong>${expiryCell(a.insurance_expiry)}</div>
        <div class="detail-item"><strong>الفحص الدوري</strong>${expiryCell(a.inspection_expiry)}</div><div class="detail-item"><strong>تفويض القيادة</strong>${expiryCell(a.authorization_expiry)}</div>
        <div class="detail-item"><strong>العداد</strong>${a.odometer ? (+a.odometer).toLocaleString() + ' كم' : '—'}</div>` : ''}
        <div class="detail-item"><strong>الصيانة القادمة</strong>${a.next_service_km ? (+a.next_service_km).toLocaleString() + ' كم ' : ''}${a.next_service_date ? expiryCell(a.next_service_date) : (a.next_service_km ? '' : '—')}</div>
      </div>${a.notes ? `<div class="note-box">${esc(a.notes)}</div>` : ''}
      <h4 class="sub-h">🔧 سجل الصيانة (${money(a.maintenance.reduce((s, m) => s + (+m.cost || 0), 0))})</h4>
      ${a.maintenance.length ? `<table><tbody>${a.maintenance.map(m => `<tr><td>${dShort(m.m_date)}</td><td>${esc(M_TYPES[m.m_type] || m.m_type)}</td><td>${esc(m.description || '')}</td><td>${money(m.cost)}</td><td>${esc(m.vendor || '')}</td><td>${m.odometer ? (+m.odometer).toLocaleString() + ' كم' : ''}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">لا يوجد</p>'}
      <h4 class="sub-h">🔑 سجل العهدة</h4>
      ${a.custody_log.length ? `<table><tbody>${a.custody_log.map(c => `<tr><td class="nowrap">${esc((c.created_at || '').slice(0, 10))}</td><td>${c.action === 'assign' ? 'تسليم إلى' : 'استلام من'} <strong>${esc(c.employee_name || '')}</strong></td><td>${esc(c.condition || '')}</td><td>${esc(c.notes || '')}</td><td class="small">${esc(c.by_name || '')}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">لا يوجد</p>'}`;
    const f = [
      can('assets', 'edit') ? `<button class="btn" onclick="custodyDialog(${a.id}, ${a.custodian_id || 'null'})">🔑 ${a.custodian_id ? 'نقل/استلام العهدة' : 'تسليم عهدة'}</button>` : '',
      can('assets', 'edit') ? `<button class="btn btn-outline" onclick="maintDialog(${a.id}, ${veh})">+ صيانة</button>` : '',
      can('assets', 'edit') ? `<button class="btn btn-outline" onclick="closeModal();assetEditor(${a.id})">تعديل</button>` : '',
      can('assets', 'delete') ? `<button class="btn btn-outline danger-t" onclick="assetDel(${a.id})">حذف</button>` : '',
      '<button class="btn btn-outline" onclick="closeModal()">إغلاق</button>'].join('');
    openModal(`${esc(a.asset_code)} — ${esc(a.name)}`, body, f);
    document.querySelector('.modal').classList.add('wide');
  } catch (e) { toast(e.message, 'error'); }
}
async function custodyDialog(id, cur) {
  await loadEmps();
  openModal('العهدة', `<div class="form-group"><label class="form-label">تسليم إلى (اتركه فاضي = استلام العهدة وإرجاعها للمستودع)</label><select id="cs-emp" class="form-select">${empOptions('')}</select></div>
    ${fld('cs-cond', 'حالة الأصل عند التسليم/الاستلام', '', 'text', 'placeholder="سليم / خدش بالباب الخلفي..."')}${fld('cs-notes', 'ملاحظات')}`,
    `<button class="btn" onclick="custodySave(${id})">حفظ</button><button class="btn btn-outline" onclick="assetView(${id})">رجوع</button>`);
}
async function custodySave(id) {
  try { await capi(`/assets/${id}/custody`, 'POST', { employee_id: val('cs-emp'), condition: val('cs-cond'), notes: val('cs-notes') }); toast('تم', 'success'); assetView(id); if (currentPage === 'assets') renderAssets(); } catch (e) { toast(e.message, 'error'); }
}
function maintDialog(id, veh) {
  openModal('تسجيل صيانة', `<div class="form-row three">${fld('mt2-date', 'التاريخ *', todayISO(), 'date')}${sel('mt2-type', 'النوع', M_TYPES, 'service')}${fld('mt2-cost', 'التكلفة', '', 'number')}</div>
    ${fld('mt2-desc', 'الوصف')}<div class="form-row three">${fld('mt2-vendor', 'الورشة/المورد')}${veh ? fld('mt2-odo', 'العداد (كم)', '', 'number') : ''}${fld('mt2-ndate', 'الصيانة القادمة بتاريخ', '', 'date')}</div>
    ${veh ? fld('mt2-nkm', 'الصيانة القادمة عند (كم)', '', 'number') : ''}`,
    `<button class="btn" onclick="maintSave(${id})">حفظ</button><button class="btn btn-outline" onclick="assetView(${id})">رجوع</button>`);
}
async function maintSave(id) {
  try {
    await capi(`/assets/${id}/maintenance`, 'POST', { m_date: val('mt2-date'), m_type: val('mt2-type'), cost: val('mt2-cost'), description: val('mt2-desc'), vendor: val('mt2-vendor'), odometer: val('mt2-odo'), next_due_date: val('mt2-ndate'), next_due_km: val('mt2-nkm') });
    toast('تم', 'success'); assetView(id); if (currentPage === 'assets') renderAssets();
  } catch (e) { toast(e.message, 'error'); }
}
async function assetDel(id) { if (!confirm('حذف الأصل وسجلاته نهائياً؟ (للأصل المباع/المستبعد غيّر حالته بدل الحذف)')) return; try { await capi('/assets/' + id, 'DELETE'); closeModal(); renderAssets(); } catch (e) { toast(e.message, 'error'); } }

// ===================================================================
// تسجيل الصفحات + إضافات لوحة «يومي»
// ===================================================================
window.HR_PAGES = { myhr: renderMyHR, employees: renderEmployees, leaves: renderLeaves, payroll: renderPayroll, tasks: renderTasks, assets: renderAssets };

const _origMyDay = renderMyDay;
renderMyDay = async function () {
  await _origMyDay();
  const extra = [];
  try {
    const me = await capi('/me/hr');
    const open = me.tasks.filter(t => ['todo', 'in_progress'].includes(t.status));
    if (open.length) extra.push(`<div class="card"><div class="card-header"><h3 class="card-title">✅ مهامي</h3><button class="btn btn-sm btn-outline" onclick="goPage('myhr')">الكل</button></div><table><tbody>${open.slice(0, 6).map(t => `<tr onclick="goPage('myhr')"><td><strong>${esc(t.title)}</strong></td><td>${t.due_date ? (t.due_date < todayISO() ? pill(dShort(t.due_date), 'bad') : dShort(t.due_date)) : ''}</td><td>${pill(TASK_ST[t.status], 'warn')}</td></tr>`).join('')}</tbody></table></div>`);
  } catch (e) {}
  if (can('employees') || can('assets') || can('leaves')) {
    try {
      const al = await capi('/hr/alerts');
      if (al.items.length || al.pending_leaves) extra.push(`<div class="card"><div class="card-header"><h3 class="card-title">⚠ تنبيهات الموظفين والأصول</h3></div>
        ${al.pending_leaves ? `<div class="warn-box" onclick="goPage('leaves')" style="cursor:pointer">🌿 ${al.pending_leaves} طلب إجازة بانتظار الاعتماد</div>` : ''}
        <table><tbody>${al.items.slice(0, 8).map(a => `<tr onclick="goPage('${a.kind === 'asset' ? 'assets' : 'employees'}')"><td><strong>${esc(a.name)}</strong></td><td>${esc(a.what)}</td><td>${a.days_left < 0 ? pill('متأخر', 'bad') : pill('بعد ' + a.days_left + ' يوم', 'warn')}</td></tr>`).join('')}</tbody></table></div>`);
    } catch (e) {}
  }
  if (extra.length) {
    const grid = document.querySelector('#page-content .two-col');
    if (grid) grid.insertAdjacentHTML('afterbegin', extra.join(''));
  }
};
