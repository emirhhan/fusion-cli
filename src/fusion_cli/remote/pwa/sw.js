// Yalnız kabuk dosyaları önbelleğe alınır; RPC ve görev verisi ASLA önbelleğe girmez.
const SHELL = [
  "/", "/app.js", "/app.js?v=mobile-workspace-20261017", "/styles.css?v=mobile-workspace-20261017", "/icon.svg?v=mobile-workspace-20261017", "/api.js", "/approvals.js", "/chat.js", "/dom.js", "/media.js", "/screen-stream.js", "/screen-view.js", "/dock.js",
  "/signing.js", "/store.js", "/views-chats.js", "/views-settings.js", "/views-tasks.js", "/voice.js", "/styles.css", "/manifest.webmanifest", "/icon.svg",
  "/icon-192.png", "/icon-192.png?v=logo-20261017", "/icon-512.png", "/apple-touch-icon.png",
];
const CACHE = "fusion-kabuk-v9";
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
  event.respondWith(networkOrShell(event.request));
});

// Ağ ve önbellek birlikte yoksa respondWith hiçbir zaman boş yanıt almamalı.
async function networkOrShell(request) {
  try {
    return await fetch(request);
  } catch {
    try {
      const cache = await caches.open(CACHE);
      const cached = await cache.match(request, { ignoreSearch: request.mode === "navigate" });
      if (cached) return cached;
    } catch {
      // Özel gezinmede veya depolama reddinde de bağlantı açıklaması gösterilir.
    }
    return new Response(
      "Fusion bilgisayarına ulaşılamıyor. Telefonda ve bilgisayarda Tailscale bağlantısını açıp bu sayfayı yeniden yükle.",
      { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" } },
    );
  }
}
