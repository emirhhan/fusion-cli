// Yalnız kabuk dosyaları önbelleğe alınır; RPC ve görev verisi ASLA önbelleğe girmez.
const SHELL = ["/", "/app.js", "/signing.js", "/styles.css", "/manifest.webmanifest", "/icon.svg"];
const CACHE = "fusion-kabuk-v1";
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))),
  );
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/v1/")) return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
