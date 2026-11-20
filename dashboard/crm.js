/* =====================================================================
 * أبيلا — الإصدار 4: الدخول، الصلاحيات، خدمة العملاء، المبيعات، المالية
 * يُحمّل قبل السكربت الرئيسي في dashboard/index.html
 * ===================================================================== */
window.__abelaHasOwnPwUI = true;
const CRM = { me: null, perms: null, modules: [], users: [] };

// ---------------- مساعدات ----------------
function esc(s) {
  return (s === null || s === undefined ? '' : String(s))
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function can(mod, act = 'view') {
  if (!CRM.perms) return false;
  if (CRM.perms.is_super) return true;
  const m = (CRM.perms.modules || {})[mod];
  return !!(m && m[act]);
}
window.can = can;
function money(v) { return (Number(v) || 0).toLocaleString('en-US', { maximumFractionDigits: 2 }) + ' ر.س'; }
function dShort(s) {
  if (!s) return '—';
  const d = new Date(String(s).slice(0, 10) + 'T00:00:00');
  if (isNaN(d)) return esc(s);
  return d.toLocaleDateString('ar-SA-u-ca-gregory', { day: 'numeric', month: 'short', year: 'numeric' });
}
function todayISO() { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); }
function addDaysISO(n) { const d = new Date(); d.setDate(d.getDate() + n); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); }
function daysUntil(s) { if (!s) return null; const a = new Date(todayISO() + 'T00:00:00'), b = new Date(String(s).slice(0, 10) + 'T00:00:00'); return Math.round((b - a) / 86400000); }
function waLink(phone) {
  let p = String(phone || '').replace(/\D/g, '');
  if (!p || /^0+$/.test(p) || p === '0500000000') return '';
  if (p.startsWith('05')) p = '966' + p.slice(1);
  return 'https://wa.me/' + p;
}
function phoneCell(phone) {
  if (!phone || /^0+$/.test(String(phone).replace(/\D/g, '')) || phone === '0500000000') return '<span class="muted">—</span>';
  const w = waLink(phone);
  return `<span dir="ltr">${esc(phone)}</span> <a class="mini-link" href="tel:${esc(phone)}" onclick="event.stopPropagation()" title="اتصال">📞</a>${w ? ` <a class="mini-link" href="${w}" target="_blank" onclick="event.stopPropagation()" title="واتساب">💬</a>` : ''}`;
}
async function capi(path, method = 'GET', body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch('/api' + path, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || 'حدث خطأ');
  return j;
}
function pageShell(title, actions, body) {
  document.getElementById('page-content').innerHTML = `
    <div class="page-header"><h2 class="page-title">${title}</h2><div class="ph-actions">${actions || ''}</div></div>${body}`;
}
function setContent(html) { document.getElementById('page-content').innerHTML = html; }
function pill(text, cls) { return `<span class="pill ${cls || ''}">${esc(text)}</span>`; }

const EV_TYPES = { newborn: 'استقبال مولود', special: 'مناسبة خاصة / زواج', exhibition: 'معرض' };
const VENUES = { hospital: 'مستشفى', home: 'منزل', hall: 'قاعة', other: 'أخرى' };
const LEAD_STAGES = { new: 'جديد', contacted: 'تم التواصل', meeting: 'اجتماع', quoted: 'عرض سعر', won: 'تعاقد ✓', lost: 'خسارة' };
const LEAD_SOURCES = { instagram: 'إنستقرام', whatsapp: 'واتساب', snapchat: 'سناب', tiktok: 'تيك توك', website: 'الموقع', referral: 'توصية', returning: 'عميل سابق', other: 'أخرى' };
const QUOTE_STATUS = { draft: 'مسودة', sent: 'مرسل للعميل', accepted: 'مقبول', rejected: 'مرفوض', contracted: 'عقد' };
const CONF_STATUS = { pending: 'بانتظار التأكيد', confirmed: 'مؤكد', rescheduled: 'يعاد التأكيد' };
const CONTACT_RESULTS = { no_answer: 'لم يرد', reached: 'تم التواصل — لم يتحدد الموعد', postpone: 'طلب التأجيل/التعديل', other: 'أخرى' };
if (typeof STATUS_LABELS !== 'undefined') STATUS_LABELS.contract_issued = 'عقد صادر (بانتظار العربون)';

// ===================================================================
// الدخول
// ===================================================================
function showLogin(msg) {
  document.body.classList.add('locked');
  let ov = document.getElementById('login-overlay');
  if (!ov) {
    ov = document.createElement('div');
    ov.id = 'login-overlay';
    document.body.appendChild(ov);
  }
  ov.innerHTML = `
    <form class="login-card" onsubmit="event.preventDefault(); doLogin()">
      <img src="/assets/logo-abella.png" alt="أبيلا" class="login-logo" onerror="this.style.display='none'">
      <h2>نظام أبيلا</h2>
      <p class="login-sub">سجّل دخولك بحسابك</p>
      <label>اسم المستخدم<input id="li-user" autocomplete="username" dir="ltr" required></label>
      <label>كلمة المرور<input id="li-pass" type="password" autocomplete="current-password" dir="ltr" required></label>
      <div id="li-err" class="login-err">${esc(msg || '')}</div>
      <button class="btn" type="submit" id="li-btn">دخول</button>
    </form>`;
  ov.style.display = 'flex';
  setTimeout(() => document.getElementById('li-user')?.focus(), 50);
}
async function doLogin() {
  const btn = document.getElementById('li-btn');
  const err = document.getElementById('li-err');
  btn.disabled = true; err.textContent = '';
  try {
    const r = await fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: document.getElementById('li-user').value.trim(), password: document.getElementById('li-pass').value })
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'تعذر الدخول');
    localStorage.setItem('abela_token', j.token);
    localStorage.setItem('abela_user', JSON.stringify(j.user));
    location.reload();
  } catch (e) {
    err.textContent = e.message; btn.disabled = false;
  }
}
async function logout() {
  try { await capi('/auth/logout', 'POST', {}); } catch (e) {}
  localStorage.removeItem('abela_token'); localStorage.removeItem('abela_user');
  location.reload();
}
function showChangePassword(forced) {
  const ov = document.getElementById('login-overlay') || document.body.appendChild(Object.assign(document.createElement('div'), { id: 'login-overlay' }));
  document.body.classList.add('locked');
  ov.innerHTML = `
    <form class="login-card" onsubmit="event.preventDefault(); savePassword(${forced ? 'true' : 'false'})">
      <h2>🔒 ${forced ? 'اختر كلمة مرور جديدة' : 'تغيير كلمة المرور'}</h2>
      <p class="login-sub">${forced ? 'أهلاً ' + esc(CRM.me?.full_name || '') + ' — قبل ما تبدأ، اختر كلمة مرور خاصة فيك (8 أحرف على الأقل).' : '8 أحرف على الأقل'}</p>
      ${forced ? '' : '<label>كلمة المرور الحالية<input id="cp-old" type="password" dir="ltr" autocomplete="current-password"></label>'}
      <label>كلمة المرور الجديدة<input id="cp-new" type="password" dir="ltr" autocomplete="new-password" required></label>
      <label>أعد كتابتها<input id="cp-new2" type="password" dir="ltr" autocomplete="new-password" required></label>
      <div id="cp-err" class="login-err"></div>
      <button class="btn" type="submit">حفظ</button>
      ${forced ? '<button class="btn btn-outline" type="button" onclick="logout()" style="margin-top:8px">خروج</button>' : '<button class="btn btn-outline" type="button" onclick="closeLoginOverlay()" style="margin-top:8px">إلغاء</button>'}
    </form>`;
  ov.style.display = 'flex';
}
function closeLoginOverlay() { const ov = document.getElementById('login-overlay'); if (ov) ov.style.display = 'none'; document.body.classList.remove('locked'); }
async function savePassword(forced) {
  const n1 = document.getElementById('cp-new').value, n2 = document.getElementById('cp-new2').value;
  const err = document.getElementById('cp-err');
  if (n1.length < 8) return err.textContent = 'كلمة المرور قصيرة';
  if (n1 !== n2) return err.textContent = 'الكلمتان غير متطابقتين';
  try {
    await capi('/auth/change-password', 'POST', { new_password: n1, old_password: document.getElementById('cp-old')?.value || '' });
    if (forced) location.reload(); else { closeLoginOverlay(); toast('تم تغيير كلمة المرور', 'success'); }
  } catch (e) { err.textContent = e.message; }
}
window.addEventListener('abela:unauthorized', () => { if (!document.body.classList.contains('locked')) showLogin('انتهت الجلسة — سجّل الدخول مرة ثانية'); });
window.addEventListener('abela:must-change-password', () => showChangePassword(true));

// ===================================================================
// تشغيل التطبيق
// ===================================================================
async function startApp() {
  if (!localStorage.getItem('abela_token')) return showLogin();
  let me;
  try {
    const r = await fetch('/api/auth/me');
    if (r.status === 401) { localStorage.removeItem('abela_token'); return showLogin(); }
    me = await r.json();
  } catch (e) { return showLogin('تعذر الاتصال بالخادم'); }
  CRM.me = me.user; CRM.perms = me.perms; CRM.modules = me.modules; CRM.settings = me.settings || {};
  window.CURRENT_USER = me.user; window.CURRENT_PERMS = me;
  if (me.user.must_change_password) return showChangePassword(true);
  buildSidebar();
  wrapRenderPage();
  patchLegacy();
  if (!can('dashboard')) { currentPage = (me.menu || [])[0] || 'dashboard'; markActive(); }
  initApp();
  try { capi('/admin/users').then(u => CRM.users = u).catch(() => loadUsersLite()); } catch (e) {}
}
async function loadUsersLite() { try { CRM.users = await capi('/users'); } catch (e) { CRM.users = []; } }
function usersOptions(sel) {
  return (CRM.users || []).filter(u => u.is_active).map(u => `<option value="${u.id}" ${String(sel) === String(u.id) ? 'selected' : ''}>${esc(u.full_name)}</option>`).join('');
}

// ---------------- الشريط الجانبي حسب الصلاحيات ----------------
const NEW_NAV_ICONS = {
  confirmations: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><rect x="4" y="6" width="20" height="18" rx="2.5"/><path d="M4 11h20M9 3v5M19 3v5"/><path d="M10 17.5l3 3 5.5-6"/></svg>',
  leads: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><path d="M4 5h20l-7.5 9v8l-5 2.5V14z"/></svg>',
  quotes: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><path d="M7 3h10l5 5v17H7z"/><path d="M17 3v5h5"/><path d="M11 14h7M11 18h7M11 22h4"/></svg>',
  payments: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><rect x="3" y="7" width="22" height="15" rx="2.5"/><path d="M3 12h22"/><path d="M7 17h5"/></svg>',
  users: '<svg class="nav-svg" viewBox="0 0 28 28" fill="none"><circle cx="11" cy="9" r="4"/><path d="M3 24c0-4.4 3.6-8 8-8 1.6 0 3 .4 4.3 1.2"/><path d="M21 15l1 2 2.2.3-1.6 1.5.4 2.2-2-1-2 1 .4-2.2-1.6-1.5 2.2-.3z"/></svg>',
};
const NAV_LABEL_OVERRIDE = { quotes: 'عروض الأسعار والعقود', users: 'المستخدمين والصلاحيات', sync: 'المزامنة', finance: 'المالية والأرباح' };
function buildSidebar() {
  const nav = document.querySelector('.sidebar-nav');
  const existing = {};
  nav.querySelectorAll('.nav-item').forEach(a => {
    const k = a.dataset.page || (a.getAttribute('href') || '').includes('plan_builder') && 'plan_builder';
    if (k) existing[k] = a;
  });
  nav.innerHTML = '';
  let lastGroup = null;
  const groups = {};
  CRM.modules.forEach(m => { (groups[m.group] = groups[m.group] || []).push(m); });
  const mk = (key, label) => {
    const a = document.createElement('a');
    a.className = 'nav-item'; a.dataset.page = key; a.title = label;
    a.innerHTML = (NEW_NAV_ICONS[key] || '') + `<span>${esc(label)}</span>`;
    a.addEventListener('click', () => { currentPage = key; renderPage(); });
    return a;
  };
  let myAdded = false;
  Object.entries(groups).forEach(([g, mods]) => {
    if (!myAdded && g !== 'عام') {
      const h0 = document.createElement('div'); h0.className = 'nav-group'; h0.textContent = 'أنا'; nav.appendChild(h0);
      nav.appendChild(mk('myhr', 'ملفي ومهامي')); myAdded = true;
    }
    const visible = mods.filter(m => can(m.key));
    if (!visible.length) return;
    const h = document.createElement('div'); h.className = 'nav-group'; h.textContent = g; nav.appendChild(h);
    visible.forEach(m => {
      let a = existing[m.key];
      if (!a) {
        a = document.createElement('a');
        a.className = 'nav-item'; a.dataset.page = m.key; a.title = m.label;
        a.innerHTML = (NEW_NAV_ICONS[m.key] || '') + `<span>${esc(m.label)}</span>`;
        a.addEventListener('click', () => {
          document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
          a.classList.add('active'); currentPage = m.key; renderPage();
        });
      } else if (NAV_LABEL_OVERRIDE[m.key]) {
        const sp = a.querySelector('span'); if (sp) sp.textContent = NAV_LABEL_OVERRIDE[m.key];
      }
      nav.appendChild(a);
      if (m.key === 'sub_plans' && existing.plan_builder && can('work_plans', 'create')) nav.appendChild(existing.plan_builder);
    });
  });
  // بطاقة المستخدم + خروج
  const foot = document.querySelector('.sidebar-footer');
  if (foot && !document.getElementById('me-chip')) {
    const d = document.createElement('div'); d.id = 'me-chip';
    d.innerHTML = `<div class="me-name">${esc(CRM.me.full_name)}</div><div class="me-role">${esc(CRM.me.role_name || '')}</div>
      <div class="me-actions"><a onclick="showChangePassword(false)">كلمة المرور</a> · <a onclick="logout()">خروج</a></div>`;
    foot.prepend(d);
  }
  markActive();
}
function markActive() {
  document.querySelectorAll('.nav-item').forEach(i => i.classList.toggle('active', i.dataset.page === currentPage));
}

// ---------------- توجيه الصفحات ----------------
function wrapRenderPage() {
  const orig = window.renderPage;
  window.renderPage = function () {
    destroyCharts && destroyCharts();
    markActive();
    if (window.HR_PAGES && HR_PAGES[currentPage] && (currentPage === 'myhr' || can(currentPage))) return HR_PAGES[currentPage]();
    if (currentPage !== 'dashboard' && !can(currentPage)) {
      return setContent('<div class="empty">🔒 ما عندك صلاحية على هذا القسم</div>');
    }
    switch (currentPage) {
      case 'dashboard': if (!can('finance')) return renderMyDay(); break;
      case 'confirmations': return renderConfirmations();
      case 'leads': return renderLeads();
      case 'quotes': return renderQuotes();
      case 'payments': return renderPayments();
      case 'users': return renderUsersAdmin();
    }
    const p = orig();
    Promise.resolve(p).then(applyPermUI);
    return p;
  };
}
// إخفاء أزرار الإضافة/التعديل/الحذف في الصفحات القديمة حسب الصلاحية
const ENTITY_MODULE = { customer: 'customers', event: 'events', item: 'inventory', inventory: 'inventory', workplan: 'work_plans', work_plan: 'work_plans', appointment: 'appointments', raw: 'raw_materials', raw_material: 'raw_materials' };
const NEW_BTN_MODULE = { showNewCustomerForm: 'customers', showNewEventForm: 'events', showNewItemForm: 'inventory', showNewAppointment: 'appointments', showNewRawMaterial: 'raw_materials' };
function applyPermUI() {
  const root = document.getElementById('page-content'); if (!root) return;
  root.querySelectorAll('[onclick]').forEach(el => {
    const oc = el.getAttribute('onclick');
    let m = oc.match(/openEditModal\('(\w+)'/);
    if (m && ENTITY_MODULE[m[1]] && !can(ENTITY_MODULE[m[1]], 'edit')) el.style.display = 'none';
    m = oc.match(/confirmDelete\('(\w+)'/);
    if (m && ENTITY_MODULE[m[1]] && !can(ENTITY_MODULE[m[1]], 'delete')) el.style.display = 'none';
    m = oc.match(/^(show\w+)\(/);
    if (m && NEW_BTN_MODULE[m[1]] && !can(NEW_BTN_MODULE[m[1]], 'create')) el.style.display = 'none';
  });
}
function patchLegacy() {
  window.showCustomerDetails = showCustomerProfile;
  const _om = window.openModal;
  window.openModal = function (t, b, f) { document.querySelector('.modal')?.classList.remove('wide'); return _om(t, b, f); };
  // البحث العام: لا تجلب أقسام ما يملك صلاحيتها
  const oldApi = window.api;
  window.api = function (path, opts) {
    const p = String(path || '');
    if ((!opts || !opts.method || opts.method === 'GET')) {
      if (p.startsWith('/inventory') && !can('inventory') && !can('work_plans')) return Promise.resolve([]);
      if (p.startsWith('/appointments') && !can('appointments') && !can('calendar')) return Promise.resolve([]);
      if (p.startsWith('/customers') && !(can('customers') || can('leads') || can('quotes') || can('confirmations') || can('payments'))) return Promise.resolve([]);
    }
    return oldApi(path, opts);
  };
}

// ===================================================================
// يومي (لوحة لمن ليس لديه صلاحية المالية)
// ===================================================================
async function renderMyDay() {
  const jobs = [];
  const T = todayISO();
  if (can('appointments')) jobs.push(capi(`/appointments?from=${T}&to=${addDaysISO(7)}`).then(r => ['appts', r]).catch(() => ['appts', []]));
  if (can('confirmations')) jobs.push(capi('/confirmations').then(r => ['conf', r.rows]).catch(() => ['conf', []]));
  if (can('leads')) jobs.push(capi('/leads').then(r => ['leads', r]).catch(() => ['leads', []]));
  if (can('quotes')) jobs.push(capi('/quotes').then(r => ['quotes', r]).catch(() => ['quotes', []]));
  if (can('events')) jobs.push(capi('/events').then(r => ['events', r]).catch(() => ['events', []]));
  const data = Object.fromEntries(await Promise.all(jobs));
  const cards = [];
  const kpis = [];
  if (data.conf) {
    const due = data.conf.filter(r => r.needs_contact);
    kpis.push(`<div class="stat-card ${due.length ? 'danger' : 'success'}" onclick="goPage('confirmations')"><div class="stat-label">تأكيدات تحتاج اتصال</div><div class="stat-value">${due.length}</div></div>`);
    cards.push(`<div class="card"><div class="card-header"><h3 class="card-title">📞 تأكيد مواعيد — اتصل اليوم</h3><button class="btn btn-sm btn-outline" onclick="goPage('confirmations')">الكل</button></div>
      ${due.length ? `<table><tbody>${due.slice(0, 8).map(r => `<tr onclick="goPage('confirmations')"><td><strong>${esc(r.customer_name)}</strong></td><td>${phoneCell(r.customer_phone)}</td><td>${dShort(r.expected_date)}</td><td>${dueBadge(r.days_to_expected)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">ما فيه اتصالات مستحقة اليوم ✓</div>'}</div>`);
  }
  if (data.appts) {
    const mine = data.appts.filter(a => a.status !== 'cancelled');
    kpis.push(`<div class="stat-card"><div class="stat-label">مواعيد هذا الأسبوع</div><div class="stat-value">${mine.length}</div></div>`);
    cards.push(`<div class="card"><div class="card-header"><h3 class="card-title">🗓 المواعيد القادمة (7 أيام)</h3></div>
      ${mine.length ? `<table><tbody>${mine.slice(0, 8).map(a => `<tr><td>${dShort(a.appointment_date)} <small class="muted">${esc(a.start_time || '')}</small></td><td><strong>${esc(a.customer_full_name || a.customer_name || a.title)}</strong></td><td>${esc(a.assigned_name || '')}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">لا توجد مواعيد</div>'}</div>`);
  }
  if (data.leads) {
    const open = data.leads.filter(l => !['won', 'lost'].includes(l.stage));
    const due = open.filter(l => l.next_followup && l.next_followup <= T);
    kpis.push(`<div class="stat-card accent" onclick="goPage('leads')"><div class="stat-label">عملاء محتملون مفتوحون</div><div class="stat-value">${open.length}</div><div class="stat-sub">${due.length} متابعة مستحقة</div></div>`);
    cards.push(`<div class="card"><div class="card-header"><h3 class="card-title">🎯 متابعات المبيعات المستحقة</h3><button class="btn btn-sm btn-outline" onclick="goPage('leads')">الكل</button></div>
      ${due.length ? `<table><tbody>${due.slice(0, 8).map(l => `<tr onclick="showLead(${l.id})"><td><strong>${esc(l.full_name)}</strong></td><td>${phoneCell(l.phone)}</td><td>${pill(LEAD_STAGES[l.stage] || l.stage, 'st-' + l.stage)}</td><td>${dShort(l.next_followup)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">لا توجد متابعات مستحقة</div>'}</div>`);
  }
  if (data.quotes) {
    const waiting = data.quotes.filter(q => ['sent', 'accepted'].includes(q.status));
    kpis.push(`<div class="stat-card warning" onclick="goPage('quotes')"><div class="stat-label">عروض بانتظار العميل/التعاقد</div><div class="stat-value">${waiting.length}</div></div>`);
  }
  if (data.events) {
    const up = data.events.filter(e => { const d = daysUntil(e.actual_date || e.event_date); return d !== null && d >= 0 && d <= 7 && !['cancelled', 'completed', 'closed'].includes(e.status); });
    kpis.push(`<div class="stat-card success"><div class="stat-label">مناسبات خلال 7 أيام</div><div class="stat-value">${up.length}</div></div>`);
    cards.push(`<div class="card"><div class="card-header"><h3 class="card-title">🎉 مناسبات هذا الأسبوع</h3></div>
      ${up.length ? `<table><tbody>${up.map(e => `<tr><td>${dShort(e.actual_date || e.event_date)}</td><td><strong>${esc(e.customer_name || e.title)}</strong></td><td>${esc(e.venue_name || '')}</td><td>${e.actual_date ? pill('مؤكد', 'ok') : pill('متوقع', 'warn')}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">لا توجد مناسبات هذا الأسبوع</div>'}</div>`);
  }
  pageShell(`أهلاً ${esc((CRM.me.full_name || '').split('—')[0].trim())}`, `<span class="muted">${new Date().toLocaleDateString('ar-SA-u-ca-gregory', { weekday: 'long', day: 'numeric', month: 'long' })}</span>`,
    `<div class="stats-grid">${kpis.join('')}</div><div class="two-col">${cards.join('')}</div>`);
}
function goPage(p) { currentPage = p; renderPage(); }
function dueBadge(d) {
  if (d === null || d === undefined) return '';
  if (d < 0) return pill(`فات بـ ${-d} يوم`, 'bad');
  if (d === 0) return pill('اليوم', 'bad');
  if (d <= 7) return pill(`بعد ${d} يوم`, 'warn');
  return pill(`بعد ${d} يوم`, '');
}

// ===================================================================
// خدمة العملاء: تأكيد مواعيد المناسبات
// ===================================================================
let CONF = { tab: 'due', type: '', rows: [], settings: {} };
async function renderConfirmations() {
  try {
    const r = await capi('/confirmations' + (CONF.type ? '?type=' + CONF.type : ''));
    CONF.rows = r.rows; CONF.settings = r.settings;
  } catch (e) { return setContent(`<div class="empty">${esc(e.message)}</div>`); }
  const rows = CONF.rows;
  const due = rows.filter(r => r.needs_contact), pend = rows.filter(r => r.conf_status !== 'confirmed'), ok = rows.filter(r => r.conf_status === 'confirmed');
  const list = CONF.tab === 'due' ? due : CONF.tab === 'pending' ? pend : CONF.tab === 'confirmed' ? ok : rows;
  const tab = (k, l, n) => `<div class="tab ${CONF.tab === k ? 'active' : ''}" onclick="CONF.tab='${k}';renderConfirmations()">${l} <span class="cnt">${n}</span></div>`;
  pageShell('📞 تأكيد مواعيد المناسبات',
    `<select class="form-select inline" onchange="CONF.type=this.value;renderConfirmations()">
       <option value="">كل الأنواع</option>${Object.entries(EV_TYPES).map(([k, v]) => `<option value="${k}" ${CONF.type === k ? 'selected' : ''}>${v}</option>`).join('')}</select>`,
    `<div class="hint">تبدأ المتابعة قبل التاريخ المتوقع بـ ${CONF.settings.window} يوم، ويُعاد الاتصال كل ${CONF.settings.recontact} أيام حتى يتأكد. الولادة المبكرة بأكثر من ${Math.round(CONF.settings.rush_days / 7)} أسابيع تُعلَّم «رسوم تجهيز مستعجل».</div>
     <div class="tabs">${tab('due', 'يحتاج اتصال الآن', due.length)}${tab('pending', 'غير مؤكدة', pend.length)}${tab('confirmed', 'مؤكدة', ok.length)}${tab('all', 'الكل', rows.length)}</div>
     <div class="card tight">${list.length ? `<div class="tbl-wrap"><table>
       <thead><tr><th>العميل</th><th>الجوال</th><th>العقد</th><th>المكان</th><th>المتوقع</th><th>المؤكد</th><th>الحالة</th><th>آخر تواصل</th><th></th></tr></thead>
       <tbody>${list.map(r => `<tr>
         <td><a class="link" onclick="showCustomerProfile(${r.customer_id})">${esc(r.customer_name)}</a>${r.emergency_phone ? `<br><small class="muted">طوارئ: <span dir="ltr">${esc(r.emergency_phone)}</span></small>` : ''}</td>
         <td>${phoneCell(r.customer_phone)}</td>
         <td><strong>${esc(r.contract_code || '—')}</strong>${r.operation_order ? `<br><small class="muted">${esc(r.operation_order)}</small>` : ''}</td>
         <td>${esc(r.venue_name || '—')}<br><small class="muted">${esc(EV_TYPES[r.event_type] || '')}</small></td>
         <td>${dShort(r.expected_date)}<br>${r.conf_status !== 'confirmed' ? dueBadge(r.days_to_expected) : ''}</td>
         <td>${r.conf_status === 'confirmed' ? `<strong>${dShort(r.final_date)}</strong> ${esc(r.confirmed_time || r.event_start_time || '')}` : '—'}${r.rush_fee_due ? '<br>' + pill('رسوم تجهيز مستعجل', 'bad') : ''}</td>
         <td>${pill(CONF_STATUS[r.conf_status] || r.conf_status, r.conf_status === 'confirmed' ? 'ok' : r.needs_contact ? 'bad' : 'warn')}</td>
         <td>${r.last_contact_at ? dShort(r.last_contact_at) : '<span class="muted">لم يتم</span>'}${r.next_contact_date && r.conf_status !== 'confirmed' ? `<br><small class="muted">التالي: ${dShort(r.next_contact_date)}</small>` : ''}</td>
         <td class="nowrap">${can('confirmations', 'edit') ? (r.conf_status === 'confirmed'
           ? `<button class="btn btn-sm btn-outline" onclick="confReset(${r.event_id})">تعديل</button>`
           : `<button class="btn btn-sm" onclick="confConfirm(${r.event_id})">تأكيد التاريخ</button> <button class="btn btn-sm btn-outline" onclick="confLog(${r.event_id})">سجّل اتصال</button>`) : ''}
           <button class="btn btn-sm btn-outline" onclick="confHistory(${r.event_id})" title="سجل التواصل">🕘 ${r.contacts_count || ''}</button></td>
       </tr>`).join('')}</tbody></table></div>` : '<div class="empty">لا يوجد شيء هنا ✓</div>'}</div>`);
}
function confRow(id) { return CONF.rows.find(r => r.event_id === id) || {}; }
function confLog(id) {
  const r = confRow(id);
  openModal(`سجّل تواصل — ${r.customer_name}`, `
    <div class="form-row"><div class="form-group"><label class="form-label">الطريقة</label><select id="cl-ch" class="form-select"><option value="call">اتصال</option><option value="whatsapp">واتساب</option></select></div>
    <div class="form-group"><label class="form-label">النتيجة</label><select id="cl-res" class="form-select" onchange="document.getElementById('cl-next').value=this.value==='no_answer'?'${addDaysISO(1)}':'${addDaysISO(CONF.settings.recontact || 7)}'">${Object.entries(CONTACT_RESULTS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></div></div>
    <div class="form-group"><label class="form-label">ملاحظة</label><textarea id="cl-note" class="form-textarea" rows="2" placeholder="مثال: الموعد المتوقع ما تغيّر، تتصل بعد الكشف"></textarea></div>
    <div class="form-group"><label class="form-label">موعد الاتصال القادم</label><input id="cl-next" type="date" class="form-input" value="${addDaysISO(1)}"></div>`,
    `<button class="btn" onclick="confLogSave(${id})">حفظ</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
}
async function confLogSave(id) {
  try {
    await capi('/confirmations/' + id, 'POST', { action: 'log', channel: val('cl-ch'), result: val('cl-res'), note: val('cl-note'), next_contact_date: val('cl-next') });
    closeModal(); toast('تم التسجيل', 'success'); renderConfirmations();
  } catch (e) { toast(e.message, 'error'); }
}
function confConfirm(id) {
  const r = confRow(id);
  const rush = (CONF.settings.rush_days || 21);
  openModal(`تأكيد تاريخ المناسبة — ${r.customer_name}`, `
    <div class="detail-grid"><div class="detail-item"><strong>التاريخ المتوقع في العقد</strong>${dShort(r.expected_date)}</div><div class="detail-item"><strong>المكان</strong>${esc(r.venue_name || '—')}</div></div>
    <div class="form-row"><div class="form-group"><label class="form-label">التاريخ المؤكد *</label><input id="cc-date" type="date" class="form-input" value="${(r.expected_date || '').slice(0, 10)}" oninput="confRushHint('${(r.expected_date || '').slice(0, 10)}', ${rush}, '${r.event_type}')"></div>
    <div class="form-group"><label class="form-label">الوقت</label><input id="cc-time" type="time" class="form-input" value="${esc(r.event_start_time || '17:00')}"></div></div>
    <div id="cc-rush"></div>
    <div class="form-group"><label class="form-label">ملاحظة</label><textarea id="cc-note" class="form-textarea" rows="2"></textarea></div>`,
    `<button class="btn btn-success" onclick="confConfirmSave(${id})">تأكيد</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
}
function confRushHint(exp, rush, type) {
  const d = document.getElementById('cc-date').value, box = document.getElementById('cc-rush');
  if (!d || !exp || type !== 'newborn') return box.innerHTML = '';
  const diff = Math.round((new Date(exp) - new Date(d)) / 86400000);
  box.innerHTML = diff > rush ? `<div class="warn-box">⚠ قبل المتوقع بـ ${diff} يوم — تنطبق «رسوم التجهيز المستعجل» حسب الشروط (10% من قيمة الفاتورة قبل الضريبة + الضريبة). بلّغ المالية.</div>` : '';
}
async function confConfirmSave(id) {
  try {
    await capi('/confirmations/' + id, 'POST', { action: 'confirm', confirmed_date: val('cc-date'), confirmed_time: val('cc-time'), note: val('cc-note') });
    closeModal(); toast('تم تأكيد التاريخ', 'success'); renderConfirmations();
  } catch (e) { toast(e.message, 'error'); }
}
async function confReset(id) {
  const r = confRow(id);
  openModal('تعديل التأكيد', `<p>التاريخ المؤكد حالياً: <strong>${dShort(r.final_date)}</strong></p>
    <p class="muted">تقدر تغيّر التاريخ مباشرة، أو ترجعها «غير مؤكدة» عشان تعيد المتابعة.</p>`,
    `<button class="btn" onclick="closeModal();confConfirm(${id})">تغيير التاريخ</button>
     <button class="btn btn-outline" onclick="confResetDo(${id})">إلغاء التأكيد وإعادة المتابعة</button>
     <button class="btn btn-outline" onclick="closeModal()">إغلاق</button>`);
}
async function confResetDo(id) {
  try { await capi('/confirmations/' + id, 'POST', { action: 'reset' }); closeModal(); renderConfirmations(); } catch (e) { toast(e.message, 'error'); }
}
async function confHistory(id) {
  const r = confRow(id);
  try {
    const logs = await capi(`/confirmations/${id}/log`);
    openModal(`سجل التواصل — ${r.customer_name}`, logs.length ? `<table><thead><tr><th>التاريخ</th><th>الطريقة</th><th>النتيجة</th><th>ملاحظة</th><th>بواسطة</th></tr></thead><tbody>
      ${logs.map(l => `<tr><td class="nowrap">${esc((l.created_at || '').slice(0, 16))}</td><td>${l.channel === 'whatsapp' ? 'واتساب' : l.channel === 'system' ? 'النظام' : 'اتصال'}</td><td>${esc(CONTACT_RESULTS[l.result] || (l.result === 'confirmed' ? 'تم التأكيد' : l.result === 'rescheduled' ? 'أُعيد للمتابعة' : l.result))}</td><td>${esc(l.note || '')}</td><td>${esc(l.by_name || '')}</td></tr>`).join('')}
      </tbody></table>` : '<div class="empty">لا يوجد تواصل مسجّل</div>', '<button class="btn btn-outline" onclick="closeModal()">إغلاق</button>');
  } catch (e) { toast(e.message, 'error'); }
}
function val(id) { const el = document.getElementById(id); return el ? el.value : ''; }

// ===================================================================
// ملف العميل الشامل
// ===================================================================
async function showCustomerProfile(id) {
  try {
    const c = await capi(`/customers/${id}/profile`);
    const tabs = [['info', 'البيانات'], ['events', `المناسبات (${c.events.length})`], ['appts', `المواعيد (${c.appointments.length})`]];
    if (can('quotes')) tabs.push(['quotes', `العروض والعقود (${c.quotes.length})`]);
    const body = `
      <div class="tabs" id="cp-tabs">${tabs.map(([k, l], i) => `<div class="tab ${i ? '' : 'active'}" onclick="cpTab('${k}')">${l}</div>`).join('')}</div>
      <div class="cp-pane" data-k="info">
        <div class="detail-grid">
          <div class="detail-item"><strong>الجوال</strong>${phoneCell(c.phone)}</div>
          <div class="detail-item"><strong>جوال الطوارئ</strong><span dir="ltr">${esc(c.emergency_phone || '—')}</span></div>
          <div class="detail-item"><strong>رقم الهوية</strong><span dir="ltr">${esc(c.id_number || '—')}</span></div>
          <div class="detail-item"><strong>المدينة</strong>${esc(c.city || '—')}</div>
          <div class="detail-item"><strong>البريد</strong>${esc(c.email || '—')}</div>
          <div class="detail-item"><strong>التصنيف</strong>${esc({ individual: 'فرد', vip: 'VIP', company: 'شركة' }[c.customer_type] || '')}</div>
        </div>
        ${c.notes ? `<div class="note-box">📝 ${esc(c.notes)}</div>` : ''}
        ${c.preferences ? `<div class="note-box">💛 التفضيلات: ${esc(c.preferences)}</div>` : ''}
      </div>
      <div class="cp-pane" data-k="events" hidden>${c.events.length ? `<table><thead><tr><th>العقد</th><th>المناسبة</th><th>المتوقع</th><th>المؤكد</th><th>الحالة</th>${c.show_money ? '<th>القيمة</th><th>المدفوع</th>' : ''}</tr></thead><tbody>
        ${c.events.map(e => `<tr><td><strong>${esc(e.contract_code || '—')}</strong><br><small class="muted">${esc(e.operation_order || '')}</small></td><td>${esc(e.title)}<br><small class="muted">${esc(e.venue_name || '')}</small></td><td>${dShort(e.event_date)}</td><td>${e.confirmed_date || e.actual_date ? dShort(e.confirmed_date || e.actual_date) : pill('غير مؤكد', 'warn')}</td><td>${esc((typeof STATUS_LABELS !== 'undefined' && STATUS_LABELS[e.status]) || e.status)}</td>${c.show_money ? `<td>${money(e.total_price)}</td><td>${money(e.paid_amount)}</td>` : ''}</tr>`).join('')}</tbody></table>` : '<div class="empty">لا توجد مناسبات</div>'}</div>
      <div class="cp-pane" data-k="appts" hidden>${c.appointments.length ? `<table><thead><tr><th>التاريخ</th><th>الموعد</th><th>المسؤول</th><th>الحالة</th></tr></thead><tbody>
        ${c.appointments.map(a => `<tr><td>${dShort(a.appointment_date)} ${esc(a.start_time || '')}</td><td>${esc(a.title)}</td><td>${esc(a.assigned_name || '')}</td><td>${esc(a.status)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">لا توجد مواعيد</div>'}</div>
      <div class="cp-pane" data-k="quotes" hidden>${c.quotes.length ? `<table><thead><tr><th>العرض</th><th>الحالة</th><th>الإجمالي</th><th>العقد</th></tr></thead><tbody>
        ${c.quotes.map(q => `<tr onclick="closeModal();showQuote(${q.id})"><td><strong>${esc(q.quote_code)}</strong></td><td>${pill(QUOTE_STATUS[q.status] || q.status, 'q-' + q.status)}</td><td>${money(q.total_with_vat)}</td><td>${esc(q.contract_code || '—')}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">لا توجد عروض</div>'}</div>`;
    const foot = [
      can('quotes', 'create') ? `<button class="btn" onclick="closeModal();openQuoteEditor(null,{customer_id:${c.id},client_name:'${esc(c.full_name).replace(/'/g, '')}',client_phone:'${esc(c.phone || '')}',client_id_number:'${esc(c.id_number || '')}'})">+ عرض سعر</button>` : '',
      can('customers', 'edit') && typeof openEditModal === 'function' ? `<button class="btn btn-outline" onclick="closeModal();openEditModal('customer', ${c.id})">تعديل البيانات</button>` : '',
      '<button class="btn btn-outline" onclick="closeModal()">إغلاق</button>'].join('');
    openModal(`👤 ${c.full_name}`, body, foot);
    document.querySelector('.modal').classList.add('wide');
  } catch (e) { toast(e.message, 'error'); }
}
function cpTab(k) {
  document.querySelectorAll('#cp-tabs .tab').forEach(t => t.classList.toggle('active', t.getAttribute('onclick').includes(`'${k}'`)));
  document.querySelectorAll('.cp-pane').forEach(p => p.hidden = p.dataset.k !== k);
}

// ===================================================================
// المبيعات: العملاء المحتملون
// ===================================================================
let LEADS = { stage: 'open', rows: [], mine: false };
async function renderLeads() {
  try { LEADS.rows = await capi('/leads' + (LEADS.mine ? '?mine=1' : '')); } catch (e) { return setContent(`<div class="empty">${esc(e.message)}</div>`); }
  if (!CRM.users.length) await loadUsersLite();
  const rows = LEADS.rows, T = todayISO();
  const counts = {}; rows.forEach(r => counts[r.stage] = (counts[r.stage] || 0) + 1);
  const open = rows.filter(r => !['won', 'lost'].includes(r.stage));
  const list = LEADS.stage === 'open' ? open : LEADS.stage === 'all' ? rows : rows.filter(r => r.stage === LEADS.stage);
  const st = (k, l, n) => `<div class="tab ${LEADS.stage === k ? 'active' : ''}" onclick="LEADS.stage='${k}';renderLeads()">${l} <span class="cnt">${n || 0}</span></div>`;
  const won = counts.won || 0, lost = counts.lost || 0;
  pageShell('🎯 العملاء المحتملون',
    `<label class="chk"><input type="checkbox" ${LEADS.mine ? 'checked' : ''} onchange="LEADS.mine=this.checked;renderLeads()"> عملائي فقط</label>
     ${can('leads', 'create') ? '<button class="btn" onclick="openLeadEditor()">+ عميل محتمل</button>' : ''}`,
    `<div class="stats-grid">
       <div class="stat-card"><div class="stat-label">مفتوح</div><div class="stat-value">${open.length}</div></div>
       <div class="stat-card danger"><div class="stat-label">متابعة مستحقة</div><div class="stat-value">${open.filter(r => r.next_followup && r.next_followup <= T).length}</div></div>
       <div class="stat-card success"><div class="stat-label">تعاقد</div><div class="stat-value">${won}</div></div>
       <div class="stat-card accent"><div class="stat-label">نسبة الإغلاق</div><div class="stat-value">${won + lost ? Math.round(won * 100 / (won + lost)) + '%' : '—'}</div></div>
     </div>
     <div class="tabs">${st('open', 'المفتوحة', open.length)}${Object.entries(LEAD_STAGES).map(([k, l]) => st(k, l, counts[k])).join('')}${st('all', 'الكل', rows.length)}</div>
     <div class="card tight">${list.length ? `<div class="tbl-wrap"><table><thead><tr><th>العميل</th><th>الجوال</th><th>المصدر</th><th>المناسبة</th><th>التاريخ المتوقع</th><th>المرحلة</th><th>المتابعة القادمة</th><th>الاجتماع</th><th>المسؤول</th></tr></thead><tbody>
     ${list.map(l => `<tr onclick="showLead(${l.id})"><td><strong>${esc(l.full_name)}</strong><br><small class="muted">${esc(l.lead_code || '')}</small></td><td>${phoneCell(l.phone)}</td>
       <td>${esc(LEAD_SOURCES[l.source] || l.source || '—')}</td><td>${esc(EV_TYPES[l.event_type] || '—')}${l.venue_kind ? `<br><small class="muted">${esc(VENUES[l.venue_kind] || '')}</small>` : ''}</td>
       <td>${dShort(l.expected_date)}</td><td>${pill(LEAD_STAGES[l.stage] || l.stage, 'st-' + l.stage)}</td>
       <td>${l.next_followup ? (l.next_followup <= T && !['won', 'lost'].includes(l.stage) ? pill(dShort(l.next_followup), 'bad') : dShort(l.next_followup)) : '—'}</td>
       <td>${l.next_meeting ? dShort(l.next_meeting) : '—'}</td><td>${esc(l.assigned_name || '')}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">لا يوجد</div>'}</div>`);
}
function openLeadEditor(l) {
  l = l || { stage: 'new', next_followup: addDaysISO(1), assigned_to: CRM.me.id };
  openModal(l.id ? 'تعديل عميل محتمل' : 'عميل محتمل جديد', `
    <div class="form-row"><div class="form-group"><label class="form-label">الاسم *</label><input id="ld-name" class="form-input" value="${esc(l.full_name || '')}"></div>
    <div class="form-group"><label class="form-label">الجوال</label><input id="ld-phone" class="form-input" dir="ltr" value="${esc(l.phone || '')}" placeholder="05xxxxxxxx"></div></div>
    <div class="form-row"><div class="form-group"><label class="form-label">المصدر</label><select id="ld-src" class="form-select"><option value=""></option>${Object.entries(LEAD_SOURCES).map(([k, v]) => `<option value="${k}" ${l.source === k ? 'selected' : ''}>${v}</option>`).join('')}</select></div>
    <div class="form-group"><label class="form-label">نوع المناسبة</label><select id="ld-type" class="form-select"><option value=""></option>${Object.entries(EV_TYPES).map(([k, v]) => `<option value="${k}" ${l.event_type === k ? 'selected' : ''}>${v}</option>`).join('')}</select></div></div>
    <div class="form-row"><div class="form-group"><label class="form-label">المكان</label><select id="ld-venue" class="form-select"><option value=""></option>${Object.entries(VENUES).map(([k, v]) => `<option value="${k}" ${l.venue_kind === k ? 'selected' : ''}>${v}</option>`).join('')}</select></div>
    <div class="form-group"><label class="form-label">التاريخ المتوقع</label><input id="ld-date" type="date" class="form-input" value="${esc((l.expected_date || '').slice(0, 10))}"></div></div>
    <div class="form-row"><div class="form-group"><label class="form-label">الميزانية التقريبية</label><input id="ld-budget" type="number" class="form-input" value="${esc(l.budget || '')}"></div>
    <div class="form-group"><label class="form-label">المتابعة القادمة</label><input id="ld-follow" type="date" class="form-input" value="${esc((l.next_followup || '').slice(0, 10))}"></div></div>
    <div class="form-row"><div class="form-group"><label class="form-label">المرحلة</label><select id="ld-stage" class="form-select">${Object.entries(LEAD_STAGES).map(([k, v]) => `<option value="${k}" ${l.stage === k ? 'selected' : ''}>${v}</option>`).join('')}</select></div>
    <div class="form-group"><label class="form-label">المسؤول</label><select id="ld-assign" class="form-select">${usersOptions(l.assigned_to)}</select></div></div>
    <div class="form-group"><label class="form-label">سبب الخسارة (لو خسارة)</label><input id="ld-lost" class="form-input" value="${esc(l.lost_reason || '')}"></div>
    <div class="form-group"><label class="form-label">ملاحظات</label><textarea id="ld-notes" class="form-textarea" rows="3">${esc(l.notes || '')}</textarea></div>`,
    `<button class="btn" onclick="saveLead(${l.id || 'null'})">حفظ</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
}
async function saveLead(id) {
  const d = { full_name: val('ld-name'), phone: val('ld-phone'), source: val('ld-src'), event_type: val('ld-type'), venue_kind: val('ld-venue'),
    expected_date: val('ld-date'), budget: val('ld-budget'), next_followup: val('ld-follow'), stage: val('ld-stage'), assigned_to: val('ld-assign') || null, lost_reason: val('ld-lost'), notes: val('ld-notes') };
  try {
    if (id) await capi('/leads/' + id, 'PUT', d); else await capi('/leads', 'POST', d);
    closeModal(); toast('تم الحفظ', 'success'); renderLeads();
  } catch (e) { toast(e.message, 'error'); }
}
async function showLead(id) {
  try {
    const l = await capi('/leads/' + id);
    CRM._lead = l;
    const body = `
      <div class="detail-grid">
        <div class="detail-item"><strong>الجوال</strong>${phoneCell(l.phone)}</div>
        <div class="detail-item"><strong>المرحلة</strong>${pill(LEAD_STAGES[l.stage] || l.stage, 'st-' + l.stage)}</div>
        <div class="detail-item"><strong>المناسبة</strong>${esc(EV_TYPES[l.event_type] || '—')} ${l.venue_kind ? '— ' + esc(VENUES[l.venue_kind]) : ''}</div>
        <div class="detail-item"><strong>التاريخ المتوقع</strong>${dShort(l.expected_date)}</div>
        <div class="detail-item"><strong>المصدر</strong>${esc(LEAD_SOURCES[l.source] || l.source || '—')}</div>
        <div class="detail-item"><strong>المسؤول</strong>${esc(l.assigned_name || '—')}</div>
        <div class="detail-item"><strong>الميزانية</strong>${l.budget ? money(l.budget) : '—'}</div>
        <div class="detail-item"><strong>المتابعة القادمة</strong>${dShort(l.next_followup)}</div>
      </div>
      ${l.notes ? `<div class="note-box">📝 ${esc(l.notes)}</div>` : ''}
      ${l.lost_reason ? `<div class="warn-box">سبب الخسارة: ${esc(l.lost_reason)}</div>` : ''}
      <h4 class="sub-h">🤝 الاجتماعات</h4>
      ${l.meetings.length ? `<table><tbody>${l.meetings.map(m => `<tr><td>${dShort(m.appointment_date)} ${esc(m.start_time || '')}</td><td>${esc(m.title)}</td><td>${esc(m.location || '')}</td><td>${esc(m.assigned_name || '')}</td><td>${esc(m.status)}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">لا توجد اجتماعات</p>'}
      <h4 class="sub-h">📄 عروض الأسعار</h4>
      ${l.quotes.length ? `<table><tbody>${l.quotes.map(q => `<tr onclick="closeModal();showQuote(${q.id})"><td><strong>${esc(q.quote_code)}</strong></td><td>${pill(QUOTE_STATUS[q.status] || q.status, 'q-' + q.status)}</td><td>${money(q.total_with_vat)}</td><td>${esc(q.contract_code || '')}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">لا توجد عروض</p>'}`;
    const foot = [
      can('leads', 'edit') ? `<button class="btn" onclick="leadMeeting(${l.id})">+ اجتماع</button>` : '',
      can('quotes', 'create') && l.stage !== 'won' ? `<button class="btn btn-success" onclick="closeModal();openQuoteEditor(null,{lead_id:${l.id},client_name:'${esc(l.full_name).replace(/'/g, '')}',client_phone:'${esc(l.phone || '')}',event_type:'${l.event_type || ''}',venue_kind:'${l.venue_kind || ''}',expected_date:'${(l.expected_date || '').slice(0, 10)}'})">+ عرض سعر</button>` : '',
      can('leads', 'edit') ? `<button class="btn btn-outline" onclick="closeModal();openLeadEditor(CRM._lead)">تعديل</button>` : '',
      can('leads', 'delete') && l.stage !== 'won' ? `<button class="btn btn-outline danger-t" onclick="delLead(${l.id})">حذف</button>` : '',
      '<button class="btn btn-outline" onclick="closeModal()">إغلاق</button>'].join('');
    openModal(`🎯 ${l.full_name}`, body, foot);
    document.querySelector('.modal').classList.add('wide');
  } catch (e) { toast(e.message, 'error'); }
}
function leadMeeting(id) {
  openModal('اجتماع جديد', `
    <div class="form-row"><div class="form-group"><label class="form-label">التاريخ *</label><input id="mt-date" type="date" class="form-input" value="${addDaysISO(1)}"></div>
    <div class="form-group"><label class="form-label">الوقت *</label><input id="mt-time" type="time" class="form-input" value="17:00"></div></div>
    <div class="form-row"><div class="form-group"><label class="form-label">النوع</label><select id="mt-type" class="form-select"><option value="consultation">اجتماع/استشارة</option><option value="site_visit">معاينة موقع</option><option value="design_review">مراجعة تصميم</option><option value="contract_signing">توقيع عقد</option></select></div>
    <div class="form-group"><label class="form-label">المكان</label><input id="mt-loc" class="form-input" placeholder="المكتب / زووم / بيت العميل"></div></div>
    <div class="form-group"><label class="form-label">المسؤول</label><select id="mt-assign" class="form-select">${usersOptions(CRM.me.id)}</select></div>
    <div class="form-group"><label class="form-label">ملاحظات</label><textarea id="mt-notes" class="form-textarea" rows="2"></textarea></div>`,
    `<button class="btn" onclick="leadMeetingSave(${id})">حفظ</button><button class="btn btn-outline" onclick="showLead(${id})">رجوع</button>`);
}
async function leadMeetingSave(id) {
  try {
    await capi(`/leads/${id}/meetings`, 'POST', { appointment_date: val('mt-date'), start_time: val('mt-time'), appointment_type: val('mt-type'), location: val('mt-loc'), assigned_to: val('mt-assign'), notes: val('mt-notes') });
    toast('تمت إضافة الاجتماع', 'success'); showLead(id); if (currentPage === 'leads') renderLeads();
  } catch (e) { toast(e.message, 'error'); }
}
async function delLead(id) {
  if (!confirm('حذف العميل المحتمل نهائياً؟')) return;
  try { await capi('/leads/' + id, 'DELETE'); closeModal(); renderLeads(); } catch (e) { toast(e.message, 'error'); }
}

// ===================================================================
// المبيعات: عروض الأسعار والعقود
// ===================================================================
let QUOTES = { status: '', rows: [] };
async function renderQuotes() {
  try { QUOTES.rows = await capi('/quotes'); } catch (e) { return setContent(`<div class="empty">${esc(e.message)}</div>`); }
  const rows = QUOTES.rows;
  const cnt = {}; rows.forEach(r => cnt[r.status] = (cnt[r.status] || 0) + 1);
  const list = QUOTES.status ? rows.filter(r => r.status === QUOTES.status) : rows;
  const tab = (k, l) => `<div class="tab ${QUOTES.status === k ? 'active' : ''}" onclick="QUOTES.status='${k}';renderQuotes()">${l} <span class="cnt">${k ? (cnt[k] || 0) : rows.length}</span></div>`;
  pageShell('📄 عروض الأسعار والعقود', can('quotes', 'create') ? '<button class="btn" onclick="openQuoteEditor()">+ عرض سعر جديد</button>' : '',
    `<div class="tabs">${tab('', 'الكل')}${Object.entries(QUOTE_STATUS).map(([k, l]) => tab(k, l === 'عقد' ? 'العقود' : l)).join('')}</div>
     <div class="card tight">${list.length ? `<div class="tbl-wrap"><table><thead><tr><th>الرقم</th><th>العميل</th><th>المناسبة</th><th>التاريخ</th><th>الإجمالي</th><th>الحالة</th><th>العقد / التشغيل</th><th>المدفوع</th><th>أعدّه</th></tr></thead><tbody>
     ${list.map(q => `<tr onclick="showQuote(${q.id})"><td><strong>${esc(q.quote_code)}</strong><br><small class="muted">${dShort(q.created_at)}</small></td><td>${esc(q.client_name)}<br><small class="muted" dir="ltr">${esc(q.client_phone || '')}</small></td>
       <td>${esc(EV_TYPES[q.event_type] || '')}<br><small class="muted">${esc(VENUES[q.venue_kind] || '')} ${esc(q.venue_name || '')}</small></td><td>${dShort(q.expected_date)}</td>
       <td><strong>${money(q.total_with_vat)}</strong></td><td>${pill(QUOTE_STATUS[q.status] || q.status, 'q-' + q.status)}${q.status !== 'contracted' && q.valid_until && q.valid_until < todayISO() ? '<br>' + pill('منتهي الصلاحية', 'bad') : ''}</td>
       <td>${q.contract_code ? `<strong>${esc(q.contract_code)}</strong><br><small class="muted">${esc(q.operation_order || 'بانتظار العربون')}</small>` : '—'}</td>
       <td>${q.event_id ? money(q.paid_amount) : '—'}</td><td>${esc(q.created_by_name || '')}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">لا توجد عروض</div>'}</div>`);
}
let QE = null;
async function openQuoteEditor(id, preset) {
  let q = { event_type: 'newborn', venue_kind: 'hospital', contract_value: 0, additional: 0, discount: 0, items: [{ name: '', qty: 1 }], ...(preset || {}) };
  if (id) q = await capi('/quotes/' + id);
  QE = q;
  if (!QE.items || !QE.items.length) QE.items = [{ name: '', qty: 1 }];
  let catalog = [];
  try { catalog = await capi('/services-catalog'); } catch (e) {}
  let customers = [];
  try { customers = await capi('/customers'); } catch (e) {}
  const S = await quoteSettings();
  openModal(id ? `تعديل ${q.quote_code}` : 'عرض سعر جديد', `
    <datalist id="svc-list">${catalog.map(n => `<option value="${esc(n)}">`).join('')}</datalist>
    <h4 class="sub-h first">العميل</h4>
    <div class="form-group"><label class="form-label">عميل مسجّل (اختياري)</label><select id="qe-cust" class="form-select" onchange="qePickCustomer(this)"><option value="">— عميل جديد —</option>${customers.map(c => `<option value="${c.id}" data-name="${esc(c.full_name)}" data-phone="${esc(c.phone || '')}" data-idn="${esc(c.id_number || '')}" ${String(q.customer_id) === String(c.id) ? 'selected' : ''}>${esc(c.full_name)} ${c.phone && c.phone !== '0500000000' ? '— ' + esc(c.phone) : ''}</option>`).join('')}</select></div>
    <div class="form-row three"><div class="form-group"><label class="form-label">الاسم *</label><input id="qe-name" class="form-input" value="${esc(q.client_name || '')}"></div>
    <div class="form-group"><label class="form-label">الجوال</label><input id="qe-phone" class="form-input" dir="ltr" value="${esc(q.client_phone || '')}"></div>
    <div class="form-group"><label class="form-label">رقم الهوية</label><input id="qe-idn" class="form-input" dir="ltr" value="${esc(q.client_id_number || '')}"></div></div>
    <h4 class="sub-h">المناسبة</h4>
    <div class="form-row three"><div class="form-group"><label class="form-label">النوع *</label><select id="qe-type" class="form-select">${Object.entries(EV_TYPES).map(([k, v]) => `<option value="${k}" ${q.event_type === k ? 'selected' : ''}>${v}</option>`).join('')}</select></div>
    <div class="form-group"><label class="form-label">المكان</label><select id="qe-venue" class="form-select">${Object.entries(VENUES).map(([k, v]) => `<option value="${k}" ${q.venue_kind === k ? 'selected' : ''}>${v}</option>`).join('')}</select></div>
    <div class="form-group"><label class="form-label">اسم المكان</label><input id="qe-vname" class="form-input" value="${esc(q.venue_name || '')}" placeholder="الحبيب التخصصي"></div></div>
    <div class="form-row four"><div class="form-group"><label class="form-label">التاريخ (المتوقع)</label><input id="qe-date" type="date" class="form-input" value="${esc((q.expected_date || '').slice(0, 10))}"></div>
    <div class="form-group"><label class="form-label">الوقت</label><input id="qe-time" type="time" class="form-input" value="${esc(q.event_time || '')}"></div>
    <div class="form-group"><label class="form-label">عدد الضيوف</label><input id="qe-guests" type="number" class="form-input" value="${esc(q.guests_count || '')}"></div>
    <div class="form-group"><label class="form-label">أيام التنفيذ</label><input id="qe-days" type="number" class="form-input" value="${esc(q.execution_days || '')}" title="عدد أيام التجهيز — تستخدم لتوليد الخطط"></div></div>
    <div class="form-group"><label class="form-label">الباقة</label><select id="qe-pkg" class="form-select">${['', 'الماسية', 'الذهبية', 'الفضية', 'مخصصة'].map(p => `<option ${q.package === p ? 'selected' : ''}>${p}</option>`).join('')}</select></div>
    <h4 class="sub-h">الخدمات المقدمة <small class="muted">(اسم + عدد — بدون أسعار)</small></h4>
    <div id="qe-items"></div>
    <button class="btn btn-sm btn-outline" type="button" onclick="QE.items.push({name:'',qty:1});qeItems()">+ بند</button>
    <h4 class="sub-h">المبالغ</h4>
    <div class="form-row three"><div class="form-group"><label class="form-label">قيمة العقد (قبل الضريبة) *</label><input id="qe-cv" type="number" class="form-input" value="${q.contract_value || ''}" oninput="qeCalc()"></div>
    <div class="form-group"><label class="form-label">مبالغ إضافية</label><input id="qe-add" type="number" class="form-input" value="${q.additional || ''}" oninput="qeCalc()"></div>
    <div class="form-group"><label class="form-label">خصم</label><input id="qe-disc" type="number" class="form-input" value="${q.discount || ''}" oninput="qeCalc()"></div></div>
    <div id="qe-totals" class="totals-box" data-vat="${S.vat}" data-dep="${S.dep}" data-ins="${S.ins}"></div>
    <div class="form-group"><label class="form-label">ملاحظات تظهر للعميل</label><textarea id="qe-notes" class="form-textarea" rows="2">${esc(q.notes || '')}</textarea></div>
    <div class="form-group"><label class="form-label">ملاحظات داخلية</label><textarea id="qe-inotes" class="form-textarea" rows="2">${esc(q.internal_notes || '')}</textarea></div>`,
    `<button class="btn" onclick="saveQuote(${id || 'null'})">حفظ</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
  document.querySelector('.modal').classList.add('wide');
  qeItems(); qeCalc();
}
let _qs = null;
async function quoteSettings() {
  if (_qs) return _qs;
  // القيم الافتراضية (المعادلات المعتمدة) — المدير يقدر يعدلها من الإعدادات
  const s = (CRM.settings || {});
  _qs = { vat: +s.vat_rate || 0.15, dep: +s.deposit_rate || 0.5, ins: +s.insurance_rate || 0.2 };
  return _qs;
}
function qePickCustomer(sel) {
  const o = sel.selectedOptions[0]; if (!o || !o.value) return;
  document.getElementById('qe-name').value = o.dataset.name || '';
  document.getElementById('qe-phone').value = o.dataset.phone && o.dataset.phone !== '0500000000' ? o.dataset.phone : '';
  document.getElementById('qe-idn').value = o.dataset.idn || '';
}
function qeItems() {
  document.getElementById('qe-items').innerHTML = QE.items.map((it, i) => `
    <div class="item-row"><span class="item-n">${i + 1}</span>
      <input class="form-input" list="svc-list" placeholder="الخدمة" value="${esc(it.name)}" oninput="QE.items[${i}].name=this.value">
      <input class="form-input qty" type="number" min="0" step="1" value="${esc(it.qty)}" oninput="QE.items[${i}].qty=this.value">
      <input class="form-input" placeholder="تفاصيل (اختياري)" value="${esc(it.notes || '')}" oninput="QE.items[${i}].notes=this.value">
      <button class="icon-x" type="button" title="حذف" onclick="QE.items.splice(${i},1);if(!QE.items.length)QE.items.push({name:'',qty:1});qeItems()">×</button></div>`).join('');
}
function qeCalc() {
  const box = document.getElementById('qe-totals'); if (!box) return;
  const vat = +box.dataset.vat, dep = +box.dataset.dep, ins = +box.dataset.ins;
  const cv = +val('qe-cv') || 0, add = +val('qe-add') || 0, disc = +val('qe-disc') || 0;
  const base = Math.max(cv + add - disc, 0), v = base * vat, tot = base + v;
  box.innerHTML = `<div><span>الصافي قبل الضريبة</span><b>${money(base)}</b></div><div><span>ضريبة ${Math.round(vat * 100)}%</span><b>${money(v)}</b></div>
    <div class="big"><span>الإجمالي شامل الضريبة</span><b>${money(tot)}</b></div><div><span>العربون ${Math.round(dep * 100)}%</span><b>${money(tot * dep)}</b></div><div><span>التأمين ${Math.round(ins * 100)}% من قيمة العقد</span><b>${money(cv * ins)}</b></div>`;
}
async function saveQuote(id) {
  const d = {
    customer_id: val('qe-cust') || null, client_name: val('qe-name'), client_phone: val('qe-phone'), client_id_number: val('qe-idn'),
    event_type: val('qe-type'), venue_kind: val('qe-venue'), venue_name: val('qe-vname'), expected_date: val('qe-date'), event_time: val('qe-time'),
    guests_count: val('qe-guests'), execution_days: val('qe-days'), package: val('qe-pkg'),
    contract_value: val('qe-cv'), additional: val('qe-add'), discount: val('qe-disc'), notes: val('qe-notes'), internal_notes: val('qe-inotes'),
    items: QE.items.filter(i => (i.name || '').trim()), lead_id: QE.lead_id || null,
  };
  if (!d.client_name.trim()) return toast('اكتب اسم العميل', 'error');
  if (!(+d.contract_value > 0)) return toast('اكتب قيمة العقد', 'error');
  try {
    let r;
    if (id) { r = await capi('/quotes/' + id, 'PUT', d); r.id = id; } else r = await capi('/quotes', 'POST', d);
    closeModal(); toast('تم حفظ العرض', 'success');
    if (currentPage === 'quotes') renderQuotes();
    showQuote(r.id);
  } catch (e) { toast(e.message, 'error'); }
}
async function showQuote(id) {
  try {
    const q = await capi('/quotes/' + id);
    const contracted = q.status === 'contracted';
    const body = `
      <div class="q-head"><div>${pill(QUOTE_STATUS[q.status] || q.status, 'q-' + q.status)} ${contracted ? `<strong class="code">${esc(q.contract_code)}</strong> ${q.operation_order ? pill('تشغيل ' + q.operation_order, 'ok') : pill('بانتظار العربون', 'warn')}` : `<span class="muted">صالح حتى ${dShort(q.valid_until)}</span>`}</div>
        <div class="q-total">${money(q.total_with_vat)}</div></div>
      <div class="detail-grid">
        <div class="detail-item"><strong>العميل</strong>${esc(q.client_name)} ${q.customer_id ? `<a class="link" onclick="closeModal();showCustomerProfile(${q.customer_id})">الملف</a>` : ''}</div>
        <div class="detail-item"><strong>الجوال</strong>${phoneCell(q.client_phone)}</div>
        <div class="detail-item"><strong>المناسبة</strong>${esc(EV_TYPES[q.event_type] || '')} — ${esc(VENUES[q.venue_kind] || '')} ${esc(q.venue_name || '')}</div>
        <div class="detail-item"><strong>التاريخ</strong>${dShort(q.expected_date)} ${esc(q.event_time || '')}${q.actual_date ? ' — مؤكد ' + dShort(q.actual_date) : ''}</div>
        <div class="detail-item"><strong>الباقة / الضيوف</strong>${esc(q.package || '—')} / ${esc(q.guests_count || '—')}</div>
        <div class="detail-item"><strong>أيام التنفيذ</strong>${esc(q.execution_days || '—')}</div>
      </div>
      <h4 class="sub-h">الخدمات المقدمة</h4>
      <table><thead><tr><th>#</th><th>الخدمة</th><th>العدد</th><th>تفاصيل</th></tr></thead><tbody>${q.items.map((it, i) => `<tr><td>${i + 1}</td><td>${esc(it.name)}</td><td>${esc(+it.qty)}</td><td>${esc(it.notes || '')}</td></tr>`).join('')}</tbody></table>
      <div class="totals-box static">
        <div><span>قيمة العقد</span><b>${money(q.contract_value)}</b></div>${q.additional ? `<div><span>إضافي</span><b>${money(q.additional)}</b></div>` : ''}${q.discount ? `<div><span>خصم</span><b>- ${money(q.discount)}</b></div>` : ''}
        <div><span>الضريبة</span><b>${money(q.vat_amount)}</b></div><div class="big"><span>الإجمالي</span><b>${money(q.total_with_vat)}</b></div>
        <div><span>العربون</span><b>${money(q.deposit)}</b></div><div><span>التأمين</span><b>${money(q.insurance)}</b></div>
        ${contracted ? `<div><span>المدفوع</span><b>${money(q.paid_amount)}</b></div><div><span>المتبقي</span><b>${money((q.total_with_vat || 0) - (q.paid_amount || 0))}</b></div>` : ''}
      </div>
      ${q.notes ? `<div class="note-box">${esc(q.notes)}</div>` : ''}${q.internal_notes ? `<div class="note-box int">🔒 داخلي: ${esc(q.internal_notes)}</div>` : ''}
      ${contracted && q.payments.length ? `<h4 class="sub-h">الدفعات</h4><table><tbody>${q.payments.map(p => `<tr><td>${dShort(p.payment_date)}</td><td>${money(p.amount)}</td><td>${esc(PAY_METHODS[p.payment_method] || p.payment_method || '')}</td><td>${esc(p.reference || '')}</td><td>${esc(p.received_by_name || '')}</td></tr>`).join('')}</tbody></table>` : ''}
      <p class="muted small">أعدّه ${esc(q.created_by_name || '')} — ${esc((q.created_at || '').slice(0, 16))}</p>`;
    const b = [];
    b.push(`<button class="btn btn-outline" onclick="window.open('/dashboard/print_quote.html?id=${q.id}','_blank')">🖨 ${contracted ? 'طباعة العقد' : 'طباعة العرض'}</button>`);
    if (!contracted && can('quotes', 'edit')) {
      b.push(`<button class="btn btn-outline" onclick="closeModal();openQuoteEditor(${q.id})">تعديل</button>`);
      if (q.status === 'draft') b.push(`<button class="btn btn-outline" onclick="quoteStatus(${q.id},'sent')">أُرسل للعميل</button>`);
      if (['draft', 'sent'].includes(q.status)) b.push(`<button class="btn btn-outline" onclick="quoteStatus(${q.id},'accepted')">قبِل العميل</button>`);
      if (q.status !== 'rejected') b.push(`<button class="btn btn-outline danger-t" onclick="quoteStatus(${q.id},'rejected')">رفض</button>`);
      b.push(`<button class="btn btn-success" onclick="convertQuote(${q.id})">✍ تحويل لعقد</button>`);
    }
    if (contracted && can('payments', 'create') && (q.total_with_vat - (q.paid_amount || 0)) > 0.01) b.push(`<button class="btn btn-success" onclick="payDialog(${q.event_id})">+ تسجيل دفعة</button>`);
    if (!contracted && can('quotes', 'delete')) b.push(`<button class="btn btn-outline danger-t" onclick="delQuote(${q.id})">حذف</button>`);
    b.push('<button class="btn btn-outline" onclick="closeModal()">إغلاق</button>');
    openModal(`📄 ${q.quote_code} — ${q.client_name}`, body, b.join(''));
    document.querySelector('.modal').classList.add('wide');
  } catch (e) { toast(e.message, 'error'); }
}
async function quoteStatus(id, st) {
  try { await capi(`/quotes/${id}/status`, 'POST', { status: st }); toast('تم', 'success'); showQuote(id); if (currentPage === 'quotes') renderQuotes(); } catch (e) { toast(e.message, 'error'); }
}
async function convertQuote(id) {
  if (!confirm('تحويل العرض لعقد؟\n\n• يُصدر رقم العقد (B/W/E) ويُنشأ ملف المناسبة والعميل.\n• رقم التشغيل O يُصرف تلقائياً عند تسجيل العربون من المالية.\n• بعد التحويل ما يتعدل العرض.')) return;
  try {
    const r = await capi(`/quotes/${id}/convert`, 'POST', {});
    toast('تم إصدار العقد ' + r.contract_code, 'success'); showQuote(id); if (currentPage === 'quotes') renderQuotes();
  } catch (e) { toast(e.message, 'error'); }
}
async function delQuote(id) {
  if (!confirm('حذف العرض نهائياً؟')) return;
  try { await capi('/quotes/' + id, 'DELETE'); closeModal(); renderQuotes(); } catch (e) { toast(e.message, 'error'); }
}

// ===================================================================
// المالية: الدفعات والمستحقات
// ===================================================================
const PAY_METHODS = { bank_transfer: 'تحويل بنكي', cash: 'نقدي', mada: 'مدى / شبكة', link: 'رابط دفع', cheque: 'شيك' };
let PAY = { data: null };
async function renderPayments() {
  try { PAY.data = await capi('/payments/dues'); } catch (e) { return setContent(`<div class="empty">${esc(e.message)}</div>`); }
  const sys = PAY.data.system, sh = PAY.data.sheet;
  const tot = sys.reduce((a, r) => a + (r.total_price || 0), 0), paid = sys.reduce((a, r) => a + (r.paid_amount || 0), 0);
  const noDep = sys.filter(r => !r.deposit_paid);
  const shRem = sh.reduce((a, r) => a + (r.remaining || 0), 0);
  pageShell('💳 الدفعات والمستحقات', '',
    `<div class="stats-grid">
      <div class="stat-card"><div class="stat-label">عقود النظام — الإجمالي</div><div class="stat-value sm">${money(tot)}</div></div>
      <div class="stat-card success"><div class="stat-label">المحصّل</div><div class="stat-value sm">${money(paid)}</div></div>
      <div class="stat-card danger"><div class="stat-label">المتبقي</div><div class="stat-value sm">${money(tot - paid)}</div></div>
      <div class="stat-card warning"><div class="stat-label">عقود بانتظار العربون</div><div class="stat-value">${noDep.length}</div></div>
    </div>
    <div class="card tight"><div class="card-header"><h3 class="card-title">عقود النظام</h3><span class="muted small">العربون يصرف رقم التشغيل O تلقائياً</span></div>
    ${sys.length ? `<div class="tbl-wrap"><table><thead><tr><th>العقد</th><th>التشغيل</th><th>العميل</th><th>التاريخ</th><th>الإجمالي</th><th>المدفوع</th><th>المتبقي</th><th>العربون</th><th></th></tr></thead><tbody>
    ${sys.map(r => `<tr><td><a class="link" onclick="showQuote(${r.quote_id})"><strong>${esc(r.contract_code)}</strong></a></td><td>${esc(r.operation_order || '—')}</td><td>${esc(r.customer_name)}<br><small class="muted" dir="ltr">${esc(r.customer_phone || '')}</small></td>
      <td>${dShort(r.actual_date || r.event_date)}</td><td>${money(r.total_price)}</td><td>${money(r.paid_amount)}</td><td><strong>${money(r.remaining)}</strong></td>
      <td>${r.deposit_paid ? pill('مدفوع', 'ok') : pill('مطلوب ' + money(r.deposit), 'warn')}</td>
      <td class="nowrap">${can('payments', 'create') && r.remaining > 0.01 ? `<button class="btn btn-sm" onclick="payDialog(${r.event_id})">+ دفعة</button>` : ''} <button class="btn btn-sm btn-outline" onclick="payHistory(${r.event_id},'${esc(r.contract_code)}')">السجل</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">لا توجد عقود صادرة من النظام بعد</div>'}</div>
    <div class="card tight"><div class="card-header"><h3 class="card-title">عقود جدول Google (للعرض فقط) — متبقي ${money(shRem)}</h3><span class="muted small">تُسجّل دفعاتها في مولّد العقود حتى نقل البيانات</span></div>
    ${sh.length ? `<div class="tbl-wrap"><table><thead><tr><th>العقد</th><th>التشغيل</th><th>العميل</th><th>التاريخ</th><th>الإجمالي</th><th>المستلم</th><th>المتبقي</th></tr></thead><tbody>
    ${sh.map(r => `<tr><td><strong>${esc(r.contract_code || '')}</strong></td><td>${esc(r.operation_order || '')}</td><td>${esc(r.customer_name || '')}</td><td>${dShort(r.actual_date || r.expected_date)}</td><td>${money(r.total_revenue)}</td><td>${money(r.received)}</td><td><strong>${money(r.remaining)}</strong></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">لا يوجد</div>'}</div>`);
}
async function payDialog(eid) {
  let r = (PAY.data && PAY.data.system.find(x => x.event_id === eid));
  if (!r) { try { PAY.data = await capi('/payments/dues'); r = PAY.data.system.find(x => x.event_id === eid); } catch (e) {} }
  if (!r) return toast('العقد غير موجود', 'error');
  const suggested = !r.deposit_paid ? Math.max((r.deposit || 0) - (r.paid_amount || 0), 0) : r.remaining;
  openModal(`تسجيل دفعة — ${r.contract_code} / ${r.customer_name}`, `
    <div class="detail-grid"><div class="detail-item"><strong>الإجمالي</strong>${money(r.total_price)}</div><div class="detail-item"><strong>المدفوع</strong>${money(r.paid_amount)}</div>
    <div class="detail-item"><strong>المتبقي</strong>${money(r.remaining)}</div><div class="detail-item"><strong>العربون</strong>${r.deposit_paid ? 'مدفوع ✓' : money(r.deposit) + (r.operation_order ? '' : ' — يصرف رقم التشغيل')}</div></div>
    <div class="form-row"><div class="form-group"><label class="form-label">المبلغ *</label><input id="py-amt" type="number" step="0.01" class="form-input" value="${suggested.toFixed(2)}"></div>
    <div class="form-group"><label class="form-label">التاريخ</label><input id="py-date" type="date" class="form-input" value="${todayISO()}"></div></div>
    <div class="form-row"><div class="form-group"><label class="form-label">الطريقة</label><select id="py-m" class="form-select">${Object.entries(PAY_METHODS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select></div>
    <div class="form-group"><label class="form-label">نوع الدفعة</label><select id="py-t" class="form-select"><option value="deposit" ${!r.deposit_paid ? 'selected' : ''}>عربون</option><option value="installment">دفعة</option><option value="final" ${r.deposit_paid ? 'selected' : ''}>دفعة نهائية</option><option value="insurance">تأمين</option></select></div></div>
    <div class="form-group"><label class="form-label">المرجع (رقم الحوالة)</label><input id="py-ref" class="form-input" dir="ltr"></div>
    <div class="form-group"><label class="form-label">ملاحظات</label><input id="py-notes" class="form-input"></div>`,
    `<button class="btn btn-success" onclick="paySave(${eid})">حفظ الدفعة</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
}
async function paySave(eid) {
  try {
    const r = await capi('/payments', 'POST', { event_id: eid, amount: val('py-amt'), payment_date: val('py-date'), payment_method: val('py-m'), payment_type: val('py-t'), reference: val('py-ref'), notes: val('py-notes') });
    closeModal(); toast(r.operation_order ? `تم — صُرف رقم التشغيل ${r.operation_order}` : 'تم تسجيل الدفعة', 'success');
    if (currentPage === 'payments') renderPayments(); else if (currentPage === 'quotes') renderQuotes();
  } catch (e) { toast(e.message, 'error'); }
}
async function payHistory(eid, code) {
  try {
    const rows = await capi('/payments?event_id=' + eid);
    openModal(`دفعات ${code}`, rows.length ? `<table><thead><tr><th>التاريخ</th><th>المبلغ</th><th>الطريقة</th><th>النوع</th><th>المرجع</th><th>استلمها</th><th></th></tr></thead><tbody>
      ${rows.map(p => `<tr><td>${dShort(p.payment_date)}</td><td>${money(p.amount)}</td><td>${esc(PAY_METHODS[p.payment_method] || p.payment_method || '')}</td><td>${esc({ deposit: 'عربون', installment: 'دفعة', final: 'نهائية', insurance: 'تأمين' }[p.payment_type] || p.payment_type || '')}</td><td dir="ltr">${esc(p.reference || '')}</td><td>${esc(p.received_by_name || '')}</td>
      <td>${can('payments', 'delete') ? `<button class="btn btn-sm btn-outline danger-t" onclick="payDel(${p.id},${eid},'${esc(code)}')">حذف</button>` : ''}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">لا توجد دفعات</div>', '<button class="btn btn-outline" onclick="closeModal()">إغلاق</button>');
  } catch (e) { toast(e.message, 'error'); }
}
async function payDel(pid, eid, code) {
  if (!confirm('حذف الدفعة؟')) return;
  try { await capi('/payments/' + pid, 'DELETE'); payHistory(eid, code); renderPayments(); } catch (e) { toast(e.message, 'error'); }
}

// ===================================================================
// الإدارة: المستخدمين والأدوار والإعدادات
// ===================================================================
let ADM = { tab: 'users', roles: null, modules: [], selRole: null };
async function renderUsersAdmin() {
  const tabs = [['users', '👥 المستخدمون'], ['roles', '🔐 الأدوار والصلاحيات'], ['settings', '⚙ الإعدادات'], ['audit', '🕘 سجل العمليات']];
  const head = `<div class="tabs">${tabs.map(([k, l]) => `<div class="tab ${ADM.tab === k ? 'active' : ''}" onclick="ADM.tab='${k}';renderUsersAdmin()">${l}</div>`).join('')}</div>`;
  try {
    const r = await capi('/admin/roles'); ADM.roles = r.roles; ADM.modules = r.modules;
    if (ADM.tab === 'users') return admUsers(head);
    if (ADM.tab === 'roles') return admRoles(head);
    if (ADM.tab === 'settings') return admSettings(head);
    if (ADM.tab === 'audit') return admAudit(head);
  } catch (e) { setContent(`<div class="empty">${esc(e.message)}</div>`); }
}
async function admUsers(head) {
  const users = await capi('/admin/users'); CRM.users = users;
  pageShell('المستخدمين والصلاحيات', can('users', 'edit') ? '<button class="btn" onclick="userEditor()">+ مستخدم جديد</button>' : '', head + `
    <div class="card tight"><div class="tbl-wrap"><table><thead><tr><th>الاسم</th><th>اسم الدخول</th><th>الدور</th><th>المسمى</th><th>الجوال</th><th>آخر دخول</th><th>الحالة</th><th></th></tr></thead><tbody>
    ${users.map(u => `<tr class="${u.is_active ? '' : 'off'}"><td><strong>${esc(u.full_name)}</strong></td><td dir="ltr" style="text-align:right">${esc(u.username)}</td>
      <td>${pill(u.role_name || u.role, u.is_super ? 'gold' : '')}</td><td>${esc(u.job_title || '')}</td><td dir="ltr" style="text-align:right">${esc(u.phone || '')}</td>
      <td>${u.last_login ? esc(u.last_login.slice(0, 16)) : '<span class="muted">لم يدخل</span>'}${u.must_change_password ? '<br>' + pill('ينتظر تغيير كلمة المرور', 'warn') : ''}</td>
      <td>${u.is_active ? pill('فعّال', 'ok') : pill('موقوف', 'bad')}</td>
      <td class="nowrap">${can('users', 'edit') ? `<button class="btn btn-sm btn-outline" onclick="userEditor(${u.id})">تعديل</button> <button class="btn btn-sm btn-outline" onclick="userReset(${u.id})">كلمة مرور مؤقتة</button>` : ''}</td></tr>`).join('')}
    </tbody></table></div></div>`);
}
function roleOptions(sel) { return ADM.roles.map(r => `<option value="${r.key}" ${r.key === sel ? 'selected' : ''}>${esc(r.name)}${r.is_super ? ' (صلاحية كاملة)' : ''}</option>`).join(''); }
function userEditor(id) {
  const u = id ? CRM.users.find(x => x.id === id) : { role: 'customer_service', is_active: 1, language: 'ar' };
  openModal(id ? `تعديل ${u.full_name}` : 'مستخدم جديد', `
    <div class="form-row"><div class="form-group"><label class="form-label">الاسم الكامل *</label><input id="us-name" class="form-input" value="${esc(u.full_name || '')}"></div>
    <div class="form-group"><label class="form-label">اسم الدخول * <small class="muted">(إنجليزي)</small></label><input id="us-user" class="form-input" dir="ltr" value="${esc(u.username || '')}" placeholder="rahaf"></div></div>
    <div class="form-row"><div class="form-group"><label class="form-label">الدور (يحدد الأقسام اللي يشوفها) *</label><select id="us-role" class="form-select">${roleOptions(u.role)}</select></div>
    <div class="form-group"><label class="form-label">المسمى الوظيفي</label><input id="us-title" class="form-input" value="${esc(u.job_title || '')}"></div></div>
    <div class="form-row"><div class="form-group"><label class="form-label">الجوال</label><input id="us-phone" class="form-input" dir="ltr" value="${esc(u.phone || '')}"></div>
    <div class="form-group"><label class="form-label">اللغة</label><select id="us-lang" class="form-select"><option value="ar" ${u.language === 'ar' ? 'selected' : ''}>عربي</option><option value="en" ${u.language === 'en' ? 'selected' : ''}>English</option><option value="ur" ${u.language === 'ur' ? 'selected' : ''}>اردو</option></select></div></div>
    ${id ? `<label class="chk"><input id="us-active" type="checkbox" ${u.is_active ? 'checked' : ''}> الحساب فعّال</label>` : `<div class="form-group"><label class="form-label">كلمة المرور <small class="muted">(اتركها فاضية لتوليد كلمة مؤقتة)</small></label><input id="us-pass" class="form-input" dir="ltr"></div><p class="muted small">المستخدم يُطلب منه تغيير كلمة المرور أول ما يدخل.</p>`}`,
    `<button class="btn" onclick="userSave(${id || 'null'})">حفظ</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
}
async function userSave(id) {
  const d = { full_name: val('us-name'), username: val('us-user'), role: val('us-role'), job_title: val('us-title'), phone: val('us-phone'), language: val('us-lang') };
  try {
    if (id) {
      d.is_active = document.getElementById('us-active').checked ? 1 : 0;
      await capi('/admin/users/' + id, 'PUT', d); closeModal(); toast('تم الحفظ', 'success');
    } else {
      d.password = val('us-pass');
      const r = await capi('/admin/users', 'POST', d);
      showCredentials(d.full_name, d.username, r.temp_password);
    }
    renderUsersAdmin();
  } catch (e) { toast(e.message, 'error'); }
}
function showCredentials(name, username, pw) {
  const link = location.origin + '/';
  const msg = `السلام عليكم ${name}\nحسابك في نظام أبيلا:\nالرابط: ${link}\nاسم الدخول: ${username}\nكلمة المرور المؤقتة: ${pw}\n(بيطلب منك تغييرها أول دخول)`;
  openModal('✅ بيانات الدخول', `<p>أرسلها للموظف — كلمة المرور المؤقتة ما تظهر مرة ثانية.</p><pre class="cred">${esc(msg)}</pre>`,
    `<button class="btn" onclick="navigator.clipboard.writeText(document.querySelector('.cred').innerText).then(()=>toast('تم النسخ','success'))">نسخ</button><button class="btn btn-outline" onclick="closeModal()">تم</button>`);
}
async function userReset(id) {
  const u = CRM.users.find(x => x.id === id);
  if (!confirm(`إصدار كلمة مرور مؤقتة جديدة لـ ${u.full_name}؟ (تُلغى كل جلساته الحالية)`)) return;
  try { const r = await capi('/admin/users/' + id, 'PUT', { reset_password: true }); showCredentials(u.full_name, u.username, r.temp_password); renderUsersAdmin(); } catch (e) { toast(e.message, 'error'); }
}
function admRoles(head) {
  if (!ADM.selRole || !ADM.roles.find(r => r.key === ADM.selRole)) ADM.selRole = (ADM.roles.find(r => !r.is_super) || ADM.roles[0]).key;
  const role = ADM.roles.find(r => r.key === ADM.selRole);
  const groups = {}; ADM.modules.forEach(m => (groups[m.group] = groups[m.group] || []).push(m));
  const ed = can('users', 'edit') && !role.is_super;
  const cell = (m, a) => { const p = (role.perms || {})[m.key] || {}; const on = role.is_super || p[a];
    return `<td class="c"><input type="checkbox" data-m="${m.key}" data-a="${a}" ${on ? 'checked' : ''} ${ed ? '' : 'disabled'} onchange="permToggle(this)"></td>`; };
  pageShell('المستخدمين والصلاحيات', can('users', 'edit') ? '<button class="btn" onclick="roleNew()">+ دور جديد</button>' : '', head + `
    <div class="roles-layout">
      <div class="card tight roles-list">${ADM.roles.map(r => `<div class="role-item ${r.key === ADM.selRole ? 'sel' : ''}" onclick="ADM.selRole='${r.key}';renderUsersAdmin()"><span>${esc(r.name)}</span><small>${r.users_count} ${r.is_super ? '★' : ''}</small></div>`).join('')}</div>
      <div class="card tight">
        <div class="card-header"><h3 class="card-title">${esc(role.name)} ${role.is_super ? pill('صلاحية كاملة على كل الأقسام', 'gold') : ''}</h3>
          <div>${ed ? `<button class="btn btn-sm btn-outline" onclick="roleRename('${role.key}')">إعادة تسمية</button> ${!role.is_system && !role.users_count ? `<button class="btn btn-sm btn-outline danger-t" onclick="roleDelete('${role.key}')">حذف</button>` : ''}` : ''}</div></div>
        <p class="muted small">حدّد وش يقدر هذا الدور يسوي في كل قسم. القسم اللي ما عليه «عرض» ما يظهر له في القائمة أصلاً.</p>
        <table class="perm-table"><thead><tr><th>القسم</th><th class="c">عرض</th><th class="c">إضافة</th><th class="c">تعديل</th><th class="c">حذف</th></tr></thead>
        <tbody>${Object.entries(groups).map(([g, mods]) => `<tr class="grp"><td colspan="5">${esc(g)}</td></tr>` + mods.map(m => `<tr><td>${esc(m.label)}</td>${cell(m, 'view')}${cell(m, 'create')}${cell(m, 'edit')}${cell(m, 'delete')}</tr>`).join('')).join('')}</tbody></table>
        ${ed ? `<div class="perm-actions"><button class="btn" onclick="permSave('${role.key}')">حفظ الصلاحيات</button><span class="muted small">تنطبق على ${role.users_count} مستخدم فوراً</span></div>` : ''}
      </div></div>`);
}
function permToggle(cb) {
  const row = cb.closest('tr'); const a = cb.dataset.a;
  if (a !== 'view' && cb.checked) row.querySelector('[data-a=view]').checked = true;
  if (a === 'view' && !cb.checked) row.querySelectorAll('input').forEach(i => i.checked = false);
}
async function permSave(key) {
  const perms = {};
  document.querySelectorAll('.perm-table input[type=checkbox]').forEach(cb => { (perms[cb.dataset.m] = perms[cb.dataset.m] || {})[cb.dataset.a] = cb.checked; });
  try { await capi('/admin/roles/' + key, 'PUT', { perms }); toast('تم حفظ الصلاحيات', 'success'); renderUsersAdmin(); } catch (e) { toast(e.message, 'error'); }
}
function roleNew() {
  openModal('دور جديد', `<div class="form-group"><label class="form-label">اسم الدور *</label><input id="rl-name" class="form-input" placeholder="مثال: السكرتارية التنفيذية"></div>
    <div class="form-group"><label class="form-label">ابدأ من صلاحيات دور موجود (اختياري)</label><select id="rl-copy" class="form-select"><option value="">— بدون صلاحيات —</option>${ADM.roles.filter(r => !r.is_super).map(r => `<option value="${r.key}">${esc(r.name)}</option>`).join('')}</select></div>`,
    `<button class="btn" onclick="roleCreate()">إنشاء</button><button class="btn btn-outline" onclick="closeModal()">إلغاء</button>`);
}
async function roleCreate() {
  try { const r = await capi('/admin/roles', 'POST', { name: val('rl-name'), copy_from: val('rl-copy') }); closeModal(); ADM.selRole = r.key; renderUsersAdmin(); } catch (e) { toast(e.message, 'error'); }
}
async function roleRename(key) {
  const r = ADM.roles.find(x => x.key === key); const n = prompt('الاسم الجديد', r.name); if (!n) return;
  try { await capi('/admin/roles/' + key, 'PUT', { name: n }); renderUsersAdmin(); } catch (e) { toast(e.message, 'error'); }
}
async function roleDelete(key) {
  if (!confirm('حذف الدور؟')) return;
  try { await capi('/admin/roles/' + key, 'DELETE'); ADM.selRole = null; renderUsersAdmin(); } catch (e) { toast(e.message, 'error'); }
}
const SETTINGS_FIELDS = [
  ['بيانات المنشأة (تظهر في العروض والعقود)', [['company_name', 'اسم المنشأة'], ['company_cr', 'السجل التجاري'], ['company_vat', 'الرقم الضريبي'], ['company_unified', 'الرقم الموحد']]],
  ['معادلات العرض والعقد', [['vat_rate', 'نسبة الضريبة (0.15 = 15%)'], ['deposit_rate', 'نسبة العربون من الإجمالي'], ['insurance_rate', 'نسبة التأمين من قيمة العقد'], ['quote_valid_days', 'صلاحية العرض (أيام)']]],
  ['تأكيد مواعيد المناسبات', [['confirm_window_days', 'تبدأ المتابعة قبل التاريخ المتوقع بـ (يوم)'], ['confirm_recontact_days', 'إعادة الاتصال كل (يوم)'], ['rush_fee_weeks', 'رسوم الاستعجال: ولادة مبكرة بأكثر من (أسبوع)'], ['rush_fee_rate', 'نسبة رسوم الاستعجال']]],
];
const TERMS_FIELDS = [['terms_newborn_hospital', 'شروط استقبالات الولادة — المستشفيات'], ['terms_newborn_home', 'شروط استقبالات الولادة — المنازل'], ['terms_special', 'شروط الزواجات والمناسبات الخاصة'], ['terms_exhibition', 'شروط المعارض']];
async function admSettings(head) {
  const s = await capi('/admin/settings');
  const ed = can('users', 'edit');
  pageShell('المستخدمين والصلاحيات', '', head + SETTINGS_FIELDS.map(([t, f]) => `<div class="card"><div class="card-header"><h3 class="card-title">${t}</h3></div><div class="form-row">
      ${f.map(([k, l]) => `<div class="form-group"><label class="form-label">${l}</label><input class="form-input st-in" data-k="${k}" value="${esc(s[k] || '')}" ${ed ? '' : 'disabled'}></div>`).join('')}</div></div>`).join('') +
    `<div class="card"><div class="card-header"><h3 class="card-title">الشروط والأحكام في العقد المطبوع</h3></div><p class="muted small">كل سطر = بند. تُطبع تحت العقد حسب نوع المناسبة والمكان.</p>
      ${TERMS_FIELDS.map(([k, l]) => `<div class="form-group"><label class="form-label">${l}</label><textarea class="form-textarea st-in" data-k="${k}" rows="6" ${ed ? '' : 'disabled'}>${esc(s[k] || '')}</textarea></div>`).join('')}</div>
    ${ed ? '<button class="btn" onclick="settingsSave()">حفظ الإعدادات</button>' : ''}`);
}
async function settingsSave() {
  const d = {}; document.querySelectorAll('.st-in').forEach(i => d[i.dataset.k] = i.value);
  try { await capi('/admin/settings', 'PUT', d); _qs = null; Object.assign(CRM.settings, d); toast('تم الحفظ', 'success'); } catch (e) { toast(e.message, 'error'); }
}
const AUDIT_LABELS = { CREATE: 'إضافة', UPDATE: 'تعديل', DELETE: 'حذف', DEACTIVATE: 'إيقاف', UPDATE_PERMS: 'تعديل صلاحيات', CHANGE_PASSWORD: 'تغيير كلمة مرور', CONVERT: 'تحويل لعقد', PAYMENT: 'دفعة', DELETE_PAYMENT: 'حذف دفعة', CONFIRM_DATE: 'تأكيد تاريخ', UNCONFIRM_DATE: 'إلغاء تأكيد', STATUS: 'تغيير حالة' };
async function admAudit(head) {
  const rows = await capi('/admin/audit?limit=300');
  pageShell('المستخدمين والصلاحيات', '', head + `<div class="card tight"><div class="tbl-wrap"><table><thead><tr><th>الوقت</th><th>المستخدم</th><th>العملية</th><th>على</th><th>التفاصيل</th></tr></thead><tbody>
    ${rows.map(a => `<tr><td class="nowrap">${esc((a.timestamp || '').slice(0, 16))}</td><td>${esc(a.user_name || '—')}</td><td>${esc(AUDIT_LABELS[a.action] || a.action)}</td><td>${esc(a.entity_type || '')} ${esc(a.entity_id || '')}</td><td class="small muted" style="max-width:380px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(a.new_value || '')}</td></tr>`).join('')}</tbody></table></div></div>`);
}

function accountMenu() {
  openModal('حسابي', `<div class="detail-grid"><div class="detail-item"><strong>الاسم</strong>${esc(CRM.me.full_name)}</div><div class="detail-item"><strong>الدور</strong>${esc(CRM.me.role_name || '')}</div></div>`,
    `<button class="btn btn-outline" onclick="closeModal();showChangePassword(false)">تغيير كلمة المرور</button><button class="btn" onclick="logout()">تسجيل خروج</button>`);
}
