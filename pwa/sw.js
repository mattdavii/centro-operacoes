// Service worker do Centro de Operações (PWA): sempre busca no servidor local; se ele não responder,
// mostra a última tela guardada (os dados offline ficam no próprio painel, em localStorage).
const CACHE = "centro-v1";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(["/", "/manifest.webmanifest", "/icone-192.png"])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return;  // dados: sempre ao vivo
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok && (url.pathname === "/" || url.pathname.startsWith("/vendor/"))) {
      const copia = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copia));
    }
    return r;
  }).catch(() => caches.match(e.request).then(r => r || caches.match("/"))));
});
