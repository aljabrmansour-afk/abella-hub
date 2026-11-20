// Service Worker لتطبيق أبيلا - يدعم العمل أوفلاين
// v5: HTML/JS/CSS = network-first (التحديثات تظهر فوراً)، الأيقونات فقط = cache-first
const CACHE_VERSION = 'abela-v7-2026-11-10';
const STATIC_CACHE = `${CACHE_VERSION}-static`;

// أصول قليلة جداً نخزّنها (الأيقونات + manifest فقط)
const STATIC_ASSETS = [
  '/mobile/manifest.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(STATIC_ASSETS).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // حذف كل الـ caches القديمة (من أي إصدار سابق)
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== STATIC_CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // طلبات API: شبكة فقط (لا تخزين)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => new Response(
        JSON.stringify({ error: 'لا يوجد اتصال - حاول لاحقًا' }),
        { status: 503, headers: { 'Content-Type': 'application/json' } }
      ))
    );
    return;
  }

  // HTML/JS/CSS: network-first (التحديثات تظهر فوراً، fallback للـ cache فقط أوفلاين)
  const isPage = url.pathname.endsWith('/') || url.pathname.endsWith('.html')
              || url.pathname.endsWith('.js') || url.pathname.endsWith('.css');
  if (isPage) {
    event.respondWith(
      fetch(event.request).then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(event.request, clone));
        }
        return res;
      }).catch(() => caches.match(event.request).then((c) => c || new Response('Offline', { status: 503 })))
    );
    return;
  }

  // أيقونات وصور: cache-first (نادراً تتغير)
  event.respondWith(
    caches.match(event.request).then((cached) =>
      cached || fetch(event.request).then((res) => {
        if (res.ok) {
          const clone = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(event.request, clone));
        }
        return res;
      })
    )
  );
});
