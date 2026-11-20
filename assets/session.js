/* أبيلا — جلسة الدخول المشتركة لكل صفحات النظام (الإصدار 4)
 * - يضيف رمز الدخول تلقائياً لأي طلب /api/
 * - لو الحساب يحتاج تغيير كلمة المرور (مثل الحسابات القديمة admin123) يفتح نافذة التغيير
 * - يرسل حدث abela:unauthorized لما تنتهي الجلسة (لوحة التحكم تفتح شاشة الدخول)
 */
(function () {
  if (window.__abelaSession) return;
  window.__abelaSession = true;

  function getToken() {
    try {
      return localStorage.getItem('abela_token') || localStorage.getItem('abela_owner_token') || '';
    } catch (e) { return ''; }
  }
  window.abelaGetToken = getToken;

  const origFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    init = init || {};
    let url = typeof input === 'string' ? input : (input && input.url) || '';
    const isApi = url.startsWith('/api') || url.startsWith(location.origin + '/api');
    if (isApi) {
      const headers = new Headers(init.headers || (typeof input !== 'string' && input.headers) || {});
      const tok = getToken();
      if (tok && !headers.has('Authorization')) headers.set('Authorization', 'Bearer ' + tok);
      init.headers = headers;
    }
    const res = await origFetch(input, init);
    if (isApi && !/\/api\/(auth\/)?login$/.test(url)) {
      if (res.status === 401) {
        window.dispatchEvent(new CustomEvent('abela:unauthorized'));
      } else if (res.status === 403) {
        try {
          const j = await res.clone().json();
          if (j && /كلمة المرور/.test(j.error || '')) showForcedPasswordChange();
        } catch (e) {}
      }
    }
    return res;
  };

  let shown = false;
  function showForcedPasswordChange() {
    if (shown || document.getElementById('abela-pw-overlay')) return;
    if (window.__abelaHasOwnPwUI) { window.dispatchEvent(new CustomEvent('abela:must-change-password')); return; }
    shown = true;
    const ov = document.createElement('div');
    ov.id = 'abela-pw-overlay';
    ov.setAttribute('dir', 'rtl');
    ov.style.cssText = 'position:fixed;inset:0;background:rgba(45,31,20,.75);z-index:99999;display:flex;align-items:center;justify-content:center;padding:16px;font-family:Segoe UI,Tahoma,Arial,sans-serif';
    ov.innerHTML = `
      <div style="background:#fff;border-radius:14px;max-width:380px;width:100%;padding:22px;box-shadow:0 10px 40px rgba(0,0,0,.3)">
        <h3 style="margin:0 0 6px;color:#5C4528;font-size:18px">🔒 غيّر كلمة المرور</h3>
        <p style="margin:0 0 14px;color:#8B7E6E;font-size:13px;line-height:1.7">لحماية بيانات أبيلا، لازم تختار كلمة مرور جديدة خاصة فيك (8 أحرف على الأقل).</p>
        <input id="abela-pw1" type="password" placeholder="كلمة المرور الجديدة" autocomplete="new-password"
               style="width:100%;padding:12px;border:1px solid #E8DFD0;border-radius:8px;font-size:15px;margin-bottom:8px;box-sizing:border-box">
        <input id="abela-pw2" type="password" placeholder="أعد كتابتها" autocomplete="new-password"
               style="width:100%;padding:12px;border:1px solid #E8DFD0;border-radius:8px;font-size:15px;margin-bottom:8px;box-sizing:border-box">
        <div id="abela-pw-err" style="color:#A04545;font-size:13px;min-height:18px;margin-bottom:6px"></div>
        <button id="abela-pw-save" style="width:100%;padding:12px;background:#8B6F47;color:#fff;border:0;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer">حفظ والمتابعة</button>
      </div>`;
    document.body.appendChild(ov);
    ov.querySelector('#abela-pw-save').onclick = async () => {
      const a = ov.querySelector('#abela-pw1').value, b = ov.querySelector('#abela-pw2').value;
      const err = ov.querySelector('#abela-pw-err');
      if (a.length < 8) { err.textContent = 'كلمة المرور قصيرة (8 أحرف على الأقل)'; return; }
      if (a !== b) { err.textContent = 'الكلمتان غير متطابقتين'; return; }
      const r = await fetch('/api/auth/change-password', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ new_password: a })
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { err.textContent = j.error || 'تعذر الحفظ'; return; }
      location.reload();
    };
  }
  window.abelaShowPasswordChange = showForcedPasswordChange;
})();
