// İmza sözleşmesi sunucudaki `remote/signing.py` ile birebir aynıdır.
export const RPC_VERSION = "v1";

const encoder = new TextEncoder();

function toHex(buffer) {
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function fromHex(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i += 1) bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return bytes;
}

export async function sha256Hex(bytes) {
  return toHex(await crypto.subtle.digest("SHA-256", bytes));
}

export async function canonicalString(method, path, timestamp, nonce, sequence, bodyBytes) {
  const digest = await sha256Hex(bodyBytes);
  return [RPC_VERSION, method.toUpperCase(), path, String(timestamp), nonce, String(sequence), digest].join("\n");
}

export async function importKey(secretHex) {
  // extractable=false: sır tarayıcıdan geri okunamaz, yalnız imzalamada kullanılır.
  return crypto.subtle.importKey("raw", fromHex(secretHex), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
}

export async function sign(key, method, path, timestamp, nonce, sequence, bodyBytes) {
  const message = await canonicalString(method, path, timestamp, nonce, sequence, bodyBytes);
  return toHex(await crypto.subtle.sign("HMAC", key, encoder.encode(message)));
}
