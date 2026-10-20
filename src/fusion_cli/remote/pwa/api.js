import { sign } from "./signing.js";

export const REQUEST_TIMEOUT_MS = 20000;
// İmza geçerliyken gelen bu 401'ler geçicidir: yeni sıra/saat/nonce ile bir kez daha denenir.
const RETRYABLE = new Set(["sira_eski", "nonce_tekrar"]);

export async function postJson(path, payload) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(path, { method: "POST", body: JSON.stringify(payload), signal: controller.signal });
    return { status: response.status, body: await response.json() };
  } finally {
    clearTimeout(timer);
  }
}

// İmzalı RPC istemcisi.
// - İstekler SIRAYLA gider: sunucu monoton sıra numarası ister; eşzamanlı istekler ters sırada
//   ulaşınca "sira_eski" 401'i gelir (eskiden bu eşleşmeyi siliyordu).
// - `auth` işaretli hata YALNIZ sunucu "cihaz_iptal" derse fırlar; diğer 401'ler geçici hatadır.
export function createApi(device, { fetchImpl = fetch, now = Date.now } = {}) {
  let lastSeq = 0;
  const queue = [];
  let busy = false;

  async function attempt(method, params) {
    lastSeq = Math.max(lastSeq + 1, now());
    const body = new TextEncoder().encode(JSON.stringify({ method, params }));
    const timestamp = Math.floor(now() / 1000);
    const nonce = crypto.randomUUID();
    const signature = await sign(device.key, "POST", "/v1/rpc", timestamp, nonce, lastSeq, body);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      return await fetchImpl("/v1/rpc", {
        method: "POST",
        body,
        signal: controller.signal,
        headers: {
          "x-fusion-device": device.deviceId,
          "x-fusion-ts": String(timestamp),
          "x-fusion-nonce": nonce,
          "x-fusion-seq": String(lastSeq),
          "x-fusion-sig": signature,
        },
      });
    } finally {
      clearTimeout(timer);
    }
  }

  async function run(method, params) {
    let response = await attempt(method, params);
    if (response.status === 401) {
      const reason = (await response.clone().json().catch(() => ({}))).reason;
      if (reason === "cihaz_iptal") throw Object.assign(new Error("Eşleşme iptal edilmiş"), { auth: true });
      if (RETRYABLE.has(reason)) response = await attempt(method, params);
      if (response.status === 401) {
        const again = (await response.clone().json().catch(() => ({}))).reason;
        if (again === "cihaz_iptal") throw Object.assign(new Error("Eşleşme iptal edilmiş"), { auth: true });
        throw new Error(again === "zaman_asimi" ? "Telefon saati bilgisayarla uyumsuz." : "Kimlik doğrulanamadı; yeniden deneniyor.");
      }
    }
    if (response.status === 429) throw new Error("Çok fazla deneme; biraz bekle.");
    if (response.status >= 500) throw new Error("Bilgisayar yanıt vermiyor.");
    return response.json();
  }

  function pump() {
    if (busy || queue.length === 0) return;
    busy = true;
    const urgent = queue.findIndex((item) => item.method === "tasks.events" || item.method.startsWith("approvals."));
    const item = queue.splice(urgent < 0 ? 0 : urgent, 1)[0];
    // İmza sırası yalnız gönderim sırasında üretilir; öncelik tek uçuş kuralını bozmaz.
    void run(item.method, item.params).then(item.resolve, item.reject).finally(() => { busy = false; pump(); });
  }

  return function rpc(method, params = {}) {
    return new Promise((resolve, reject) => {
      queue.push({ method, params, resolve, reject });
      queueMicrotask(pump);
    });
  };
}
