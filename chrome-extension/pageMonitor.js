// Fusion Browser sayfa izleyicisi: konsol iletileri ve ağ istekleri (P-042).
//
// Sayfanın ANA dünyasında (world: MAIN), belge yüklenmeye başlarken çalışır; yalnız
// kullanıcının izin verdiği sitelere kayıtlı içerik betiği olarak eklenir. `debugger`
// izni İSTENMEZ: Chrome'un "bu eklenti tarayıcıyı hata ayıklıyor" uyarısı çıkmaz.
// `console.*`, hata olayları, `fetch` ve `XMLHttpRequest` sarmalanır; her şey sayfa
// başına sınırlı bir halka tamponda tutulur ve yalnız Fusion sorduğunda okunur.
//
// Gizlilik: istek/yanıt BAŞLIKLARI (çerez, yetki) hiç kaydedilmez; gövde yalnız
// metin/JSON yanıtlarda ve küçük bir sınıra kadar saklanır. Fusion tarafı çıktıyı
// ayrıca sır maskesinden geçirir.
(() => {
  const KEY = "__fusionMonitor";
  if (globalThis[KEY]) return;
  const MAX_CONSOLE = 300;
  const MAX_NETWORK = 150;
  const MAX_TEXT = 2000;
  const MAX_BODY = 16384;
  const TEXT_TYPES = /^(application\/(json|.*\+json|javascript|xml|x-www-form-urlencoded)|text\/)/i;
  const monitor = { console: [], network: [], pending: 0, seq: 0, started: Date.now() };
  Object.defineProperty(globalThis, KEY, { value: monitor, enumerable: false, configurable: false });

  const push = (list, limit, item) => { list.push(item); if (list.length > limit) list.splice(0, list.length - limit); };
  const asText = (value) => {
    try {
      if (typeof value === "string") return value;
      if (value instanceof Error) return `${value.name}: ${value.message}${value.stack ? `\n${value.stack}` : ""}`;
      if (value && typeof value === "object") return JSON.stringify(value);
      return String(value);
    } catch { return Object.prototype.toString.call(value); }
  };
  const record = (level, parts, stack) => {
    const text = parts.map(asText).join(" ").slice(0, MAX_TEXT);
    const item = { id: ++monitor.seq, ts: Date.now(), level, text };
    if (stack) item.stack = String(stack).slice(0, MAX_TEXT);
    push(monitor.console, MAX_CONSOLE, item);
  };

  for (const level of ["log", "info", "warn", "error", "debug", "trace"]) {
    const original = console[level];
    if (typeof original !== "function") continue;
    console[level] = function fusionConsole(...args) {
      record(level === "trace" ? "debug" : level, args);
      return original.apply(this, args);
    };
  }
  addEventListener("error", (event) => {
    const where = event.filename ? ` (${event.filename}:${event.lineno}:${event.colno})` : "";
    record("error", [`${event.message || "Hata"}${where}`], event.error?.stack);
  });
  addEventListener("unhandledrejection", (event) => {
    record("error", ["Yakalanmayan promise reddi:", event.reason], event.reason?.stack);
  });

  const start = (method, url, kind) => {
    const item = { id: ++monitor.seq, ts: Date.now(), method: String(method || "GET").toUpperCase(),
      url: String(url).slice(0, MAX_TEXT), kind, status: null, type: "", ms: null, size: null };
    monitor.pending += 1;
    push(monitor.network, MAX_NETWORK, item);
    return item;
  };
  const finish = (item, status, type, body, error) => {
    monitor.pending = Math.max(0, monitor.pending - 1);
    item.status = status;
    item.type = String(type || "").split(";")[0].trim();
    item.ms = Date.now() - item.ts;
    if (typeof body === "string") {
      item.size = body.length;
      if (TEXT_TYPES.test(item.type) || !item.type) item.body = body.slice(0, MAX_BODY);
    }
    if (error) item.error = String(error && error.message || error).slice(0, MAX_TEXT);
  };

  const originalFetch = globalThis.fetch;
  if (typeof originalFetch === "function") {
    globalThis.fetch = function fusionFetch(input, init) {
      const url = typeof input === "string" ? input : input && input.url ? input.url : String(input);
      const item = start(init && init.method || (input && input.method) || "GET", url, "fetch");
      return originalFetch.apply(this, arguments).then((response) => {
        const type = response.headers.get("content-type") || "";
        if (TEXT_TYPES.test(type)) {
          response.clone().text().then((body) => finish(item, response.status, type, body),
            () => finish(item, response.status, type));
        } else {
          finish(item, response.status, type);
        }
        return response;
      }, (error) => { finish(item, 0, "", undefined, error); throw error; });
    };
  }

  const XHR = globalThis.XMLHttpRequest;
  if (XHR && XHR.prototype) {
    const open = XHR.prototype.open;
    const send = XHR.prototype.send;
    XHR.prototype.open = function fusionOpen(method, url) {
      this.__fusionRequest = { method, url: String(url) };
      return open.apply(this, arguments);
    };
    XHR.prototype.send = function fusionSend() {
      const info = this.__fusionRequest || { method: "GET", url: "" };
      const item = start(info.method, info.url, "xhr");
      this.addEventListener("loadend", () => {
        let body;
        try { body = this.responseType === "" || this.responseType === "text" ? this.responseText : undefined; } catch { body = undefined; }
        finish(item, this.status, this.getResponseHeader("content-type") || "", body,
          this.status === 0 ? "istek tamamlanamadı" : undefined);
      }, { once: true });
      return send.apply(this, arguments);
    };
  }
})();
