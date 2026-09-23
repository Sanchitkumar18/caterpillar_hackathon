/* CAT Operator Copilot — service worker for offline-first operation.
 * Caches the app shell + static assets so the UI boots with no network, and
 * serves last-known API data when offline. Writes (POST) are handled by the
 * app's own offline queue, so they pass straight through here. */
const CACHE = "cat-copilot-v2";
const PRECACHE = [
  "/login",
  "/static/styles.css",
  "/static/app.js",
  "/static/manifest.webmanifest",
  "/static/icon.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return; // POST/PUT bypass — app handles offline queueing
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/api/")) {
    // Network-first, fall back to last cached response (stale data offline).
    e.respondWith(
      fetch(req).then((r) => { const cp = r.clone(); caches.open(CACHE).then((c) => c.put(req, cp)); return r; })
        .catch(() => caches.match(req).then((m) => m || new Response(JSON.stringify({ offline: true }), { headers: { "content-type": "application/json" } })))
    );
  } else {
    // Cache-first for shell + static; refresh cache in the background.
    e.respondWith(
      caches.match(req).then((m) => m || fetch(req).then((r) => { const cp = r.clone(); caches.open(CACHE).then((c) => c.put(req, cp)); return r; }))
    );
  }
});
