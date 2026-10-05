/* Nabz-e Farda — lightweight shell cache. Do not intercept stories JSON aggressively. */
const CACHE = "nabz-shell-v1";
const SHELL = [
  "/",
  "/offline.html",
  "/assets/style.css?v=4",
  "/assets/article.css?v=4",
  "/assets/app.js?v=4",
  "/assets/site.js?v=4",
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
  // Never cache-bust stories/data live feeds incorrectly — network first for JSON
  if (url.pathname.startsWith("/data/") || url.pathname.startsWith("/api/")) {
    e.respondWith(fetch(req).catch(() => caches.match(req)));
    return;
  }
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      if (res.ok && (url.pathname.startsWith("/assets/") || url.pathname.endsWith(".html") || url.pathname === "/")) {
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match("/offline.html")))
  );
});
