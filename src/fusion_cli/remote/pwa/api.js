import { sign } from "./signing.js";

export async function postJson(path, payload) {
  const response = await fetch(path, { method: "POST", body: JSON.stringify(payload) });
  return { status: response.status, body: await response.json() };
}

// İmzalı RPC istemcisi. Ağ hatası fırlatır (çağıran yeniden dener); 401 `auth` işaretli hata verir.
export function createApi(device) {
  let lastSeq = 0;
  return async function rpc(method, params = {}) {
    lastSeq = Math.max(lastSeq + 1, Date.now());
    const body = new TextEncoder().encode(JSON.stringify({ method, params }));
    const timestamp = Math.floor(Date.now() / 1000);
    const nonce = crypto.randomUUID();
    const signature = await sign(device.key, "POST", "/v1/rpc", timestamp, nonce, lastSeq, body);
    const response = await fetch("/v1/rpc", {
      method: "POST",
      body,
      headers: {
        "x-fusion-device": device.deviceId,
        "x-fusion-ts": String(timestamp),
        "x-fusion-nonce": nonce,
        "x-fusion-seq": String(lastSeq),
        "x-fusion-sig": signature,
      },
    });
    if (response.status === 401) throw Object.assign(new Error("Eşleşme geçersiz"), { auth: true });
    if (response.status === 429) throw new Error("Çok fazla deneme; biraz bekle.");
    if (response.status >= 500) throw new Error("Bilgisayar yanıt vermiyor.");
    return response.json();
  };
}
