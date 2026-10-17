// Yalnız kabuk dosyaları önbelleğe alınır; RPC ve görev verisi ASLA önbelleğe girmez.
const SHELL = [
  "/", "/app.js", "/api.js", "/approvals.js", "/chat.js", "/dom.js", "/media.js", "/screen-stream.js",
  "/signing.js", "/store.js", "/views-chats.js", "/views-settings.js", "/views-tasks.js", "/voice.js", "/styles.css", "/manifest.webmanifest", "/icon.svg",
  "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png",
];
const CACHE = "fusion-kabuk-v3";
self.addEventListener("install", (event) => {
  self.skipWaiting();
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
