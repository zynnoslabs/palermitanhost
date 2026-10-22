// ### CAMBIO AQUÍ ### — PalermitanHost instalable (PWA).
// Solo guarda los archivos de diseño (estilos, íconos, logo) para que abra rápido.
// NUNCA guarda páginas con datos del negocio: esas siempre vienen del servidor.
// Sin internet muestra un aviso en vez de la pantalla del dinosaurio.
const VERSION = 'ph-v1';
const BASICOS = ['/static/offline.html', '/static/style.css', '/static/app.js',
  '/static/iconos/icono-192.png', '/static/marca/palermitan.png', '/static/marca/estrellas.png',
  '/static/marca/host.png', '/static/marca/letras.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(BASICOS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET' || new URL(r.url).origin !== location.origin) return;
  if (r.mode === 'navigate') {   // páginas: siempre del servidor; sin conexión, el aviso
    e.respondWith(fetch(r).catch(() => caches.match('/static/offline.html')));
    return;
  }
  if (new URL(r.url).pathname.startsWith('/static/')) {   // diseño: lo guardado al instante y se actualiza por detrás
    e.respondWith(caches.open(VERSION).then(c => c.match(r).then(guardado => {
      const red = fetch(r).then(resp => { if (resp.ok) c.put(r, resp.clone()); return resp; }).catch(() => guardado);
      return guardado || red;
    })));
  }
});
