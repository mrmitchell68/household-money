/* Household Money service worker.
   cache-bust: hm-v1.10.0
   A service worker cannot network-first its own script. Bump VERSION to refresh the shell.
   The page posts "skipWaiting" so an update takes control. This file is not put in the cache.
   Bill reminders are checked while the page is open (on load and on a timer). There is no
   push subscription. If the phone has the app fully closed, this worker does not wake up
   to notify. notificationclick only runs after a notification was already shown. */
const VERSION = "hm-v1.10.0";
const SHELL_CACHE = VERSION + "-shell";
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png",
  "./icons/apple-touch-icon.png",
  "./vendor/tesseract/tesseract.min.js",
  "./vendor/tesseract/worker.min.js",
  "./vendor/tesseract/tesseract-core.wasm.js",
  "./vendor/tesseract/tesseract-core-simd.wasm.js",
  "./vendor/tesseract/tesseract-core-lstm.wasm.js",
  "./vendor/tesseract/tesseract-core-simd-lstm.wasm.js",
  "./vendor/tessdata/eng.traineddata.gz"
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    await Promise.all(SHELL.map(async (url) => {
      const res = await fetch(new Request(url, { cache: "reload" }));
      if (!res.ok) throw new Error("Failed to cache " + url);
      await cache.put(url, res);
    }));
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith("hm-v") && key !== SHELL_CACHE).map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  const data = event.data;
  if (data === "skipWaiting" || (data && data.type === "skipWaiting")) self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // Leave sw.js to the browser. Do not store it in the cache.
  if (url.pathname.endsWith("/sw.js")) return;

  if (req.mode === "navigate") {
    event.respondWith((async () => {
      const cache = await caches.open(SHELL_CACHE);
      const cached = await cache.match("./index.html") || await cache.match("./");
      const network = fetch(req).then((res) => {
        if (res.ok) cache.put("./index.html", res.clone());
        return res;
      }).catch(() => null);
      if (cached) {
        event.waitUntil(network);
        return cached;
      }
      return (await network) || new Response("Offline and not cached yet. Open this page once while online.", {
        status: 503,
        headers: { "Content-Type": "text/plain" }
      });
    })());
    return;
  }

  event.respondWith((async () => {
    const cache = await caches.open(SHELL_CACHE);
    const cached = await cache.match(req, { ignoreSearch: true });
    const network = fetch(req).then((res) => {
      if (res.ok) cache.put(req, res.clone());
      return res;
    }).catch(() => null);
    if (cached) {
      event.waitUntil(network);
      return cached;
    }
    return (await network) || new Response("", { status: 504 });
  })());
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const hash = typeof data.hash === "string" && data.hash.indexOf("#/") === 0 ? data.hash : "#/";
  event.waitUntil((async () => {
    const list = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of list) {
      if (client.url.indexOf(self.registration.scope) !== 0) continue;
      client.postMessage({ type: "openHash", hash: hash });
      if ("focus" in client) return client.focus();
    }
    if (self.clients.openWindow) {
      const url = new URL("./index.html" + hash, self.registration.scope);
      return self.clients.openWindow(url.href);
    }
  })());
});
