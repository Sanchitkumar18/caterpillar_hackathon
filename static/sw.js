/* CAT Operator Copilot — service worker for offline-first operation.
 * Caches the app shell + static assets so the UI boots with no network, and
 * serves last-known API data when offline. Writes (POST) are handled by the
 * app's own offline queue, so they pass straight through here. */
const CACHE = "cat-copilot-v3";
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

  // Network-first for everything (so code/data stay fresh when online), fall
  // back to the cached copy when the network is unavailable — that fallback is
  // what makes the app boot and run offline.
  e.respondWith(
    fetch(req)
      .then((r) => { const cp = r.clone(); caches.open(CACHE).then((c) => c.put(req, cp)); return r; })
      .catch(() => caches.match(req).then((m) => m || (url.pathname.startsWith("/api/")
        ? new Response(JSON.stringify({ offline: true }), { headers: { "content-type": "application/json" } })
        : Response.error())))
  );
});
