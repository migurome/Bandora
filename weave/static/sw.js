// Service worker de Bandora: la app y sus datos quedan en el móvil y funciona sin conexión.
// - Al instalarse guarda la página, data.js, D3, los iconos y los datos (data/weave.json).
// - Página, data.js y datos: primero la red, preguntando si cambiaron (si no, el servidor contesta 304 y no se baja
//   nada); sin conexión, la última copia.
// - Lo demás de la app (D3, iconos): primero la caché.
// - Fotos de artistas de Deezer: se guardan al verlas (hasta 500). Las canciones nunca (sus URLs caducan).
const APP = 'weave-bands-app-1', PHOTOS = 'weave-bands-fotos', MAX_PHOTOS = 500;
const SHELL = ['./', 'index.html', 'data.js', 'd3.min.js', 'manifest.json', 'weave-icon.svg', 'app-icon.svg',
               'icon-192.png', 'icon-512.png', 'ayuda.html', 'data/weave.json'];
const FRESH = ['./', 'index.html', 'data.js', 'data/weave.json'].map(p => new URL(p, self.registration.scope).pathname);

self.addEventListener('install', e => e.waitUntil(caches.open(APP).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));

self.addEventListener('activate', e => {  // borra las cachés de versiones anteriores de la app (las fotos se quedan)
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== APP && k !== PHOTOS).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function networkFirst(req) {
  const cache = await caches.open(APP);
  try {
    const res = await fetch(req, { cache: 'no-cache' });  // revalida: si no cambió, 304 y casi nada de datos
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req, { ignoreSearch: true });
    if (hit) return hit;
    throw err;
  }
}

async function cacheFirst(req, name, max) {
  const cache = await caches.open(name);
  const hit = await cache.match(req, { ignoreSearch: name === APP });
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok || res.type === 'opaque') {
    await cache.put(req, res.clone());
    if (max) cache.keys().then(keys => keys.slice(0, Math.max(0, keys.length - max)).forEach(k => cache.delete(k)));
  }
  return res;
}

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin === location.origin) {
    // solo lo de esta versión: la oficial no toca las carpetas de las betas (b0.3.11/…) ni una beta lo de fuera
    const scope = new URL(self.registration.scope).pathname;
    if (!url.pathname.startsWith(scope) || /^b\d/.test(url.pathname.slice(scope.length))) return;
    if (url.pathname.startsWith('/api/') || url.pathname.includes('_smoke') || url.pathname.includes('_pwa')) return;
    e.respondWith(FRESH.includes(url.pathname) ? networkFirst(e.request) : cacheFirst(e.request, APP));
  } else if (url.hostname.endsWith('dzcdn.net') && url.pathname.includes('/images/')) {
    e.respondWith(cacheFirst(e.request, PHOTOS, MAX_PHOTOS));  // fotos de artistas
  }  // el resto (API de Deezer, canciones) va directo a la red
});
