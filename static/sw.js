/* Service worker: оболочка приложения в кэше и показ уведомлений. */
const VERSION = 'feel-v3';
const SHELL = [
  '/', '/index.html', '/manifest.webmanifest', '/css/app.css',
  '/js/app.js', '/js/api.js', '/js/ui.js', '/js/store.js', '/js/push.js', '/js/grid.js', '/js/media.js',
  '/js/screens/install.js', '/js/screens/login.js', '/js/screens/welcome.js',
  '/js/screens/today.js', '/js/screens/checkin.js', '/js/screens/morning.js',
  '/js/screens/evening.js', '/js/screens/diary.js', '/js/screens/day.js',
  '/js/screens/settings.js', '/js/screens/analytics.js',
  '/icons/icon-192.png', '/icons/apple-touch-icon.png',
];
const NETWORK_TIMEOUT_MS = 3000;

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('timeout')), ms);
    promise.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

// Статика: сначала сеть (свежая версия), при плохой связи — кэш. API не кэшируется.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) {
    return;
  }
  const key = req.mode === 'navigate' ? '/index.html' : req;
  event.respondWith((async () => {
    const cache = await caches.open(VERSION);
    try {
      const res = await withTimeout(fetch(req), NETWORK_TIMEOUT_MS);
      if (res.ok) cache.put(key, res.clone());
      return res;
    } catch (e) {
      const cached = await cache.match(key);
      if (cached) return cached;
      throw e;
    }
  })());
});

// Каждый пуш обязан показать уведомление, иначе Safari отзовёт подписку.
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }
  const title = data.title || 'Feel';
  const options = {
    body: data.body || 'Как ты себя чувствуешь?',
    tag: data.tag || 'feel',
    data: { url: data.url || '/' },
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// На iOS notification.data бывает пустым — тогда адрес берём из tag (он последний, через пробел).
function urlOf(notification) {
  const fromData = notification.data && notification.data.url;
  if (fromData) return fromData;
  const parts = (notification.tag || '').split(' ');
  const last = parts[parts.length - 1];
  return last && last.startsWith('http') ? last : '/';
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL(urlOf(event.notification), self.location.origin).href;
  event.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of all) {
      if (new URL(client.url).origin === self.location.origin) {
        client.postMessage({ type: 'navigate', url: target });
        try { await client.focus(); } catch (e) { /* не во всех браузерах */ }
        return;
      }
    }
    await self.clients.openWindow(target);
  })());
});
