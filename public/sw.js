/* Nabz-e Farda — lightweight shell cache. Network-first for HTML; cache assets. */
const CACHE = "nabz-shell-v2";
const SHELL = [
  "/offline.html",
  "/assets/fonts.css?v=5",
  "/assets/style.css?v=5",
  "/assets/article.css?v=5",
  "/assets/app.js?v=5",
  "/assets/site.js?v=5",
  "/assets/favicon.svg",
  "/manifest.webmanifest"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Live JSON — network first, never block on cache
  if (url.pathname.startsWith("/data/")) {
    e.respondWith(fetch(req).catch(() => caches.match(req)));
    return;
  }

  const isNav = req.mode === "navigate" || url.pathname.endsWith(".html") || url.pathname === "/";
  if (isNav) {
    e.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        if (res.ok) caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req).then((h) => h || caches.match("/offline.html")))
    );
    return;
  }

  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      if (res.ok && url.pathname.startsWith("/assets/")) {
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match("/offline.html")))
  );
});
