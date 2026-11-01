/**
 * "İzinleri atla kipine izin ver" anahtarı (#442).
 *
 * Claude Code Desktop: Bypass permissions ancak Settings › Code › "Allow bypass permissions
 * mode" açıldıktan sonra seçilebilir. Anahtar kapalıyken mod menüsünde görünmez. Değer bu
 * bilgisayarın tarayıcı deposundadır; okunamazsa kapalı sayılır (güvenli taraf).
 */
const KEY = "fusion.allowBypassPermissionsMode";
const EVENT = "fusion:bypass-gate";

export function bypassAllowed(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "true";
  } catch {
    return false;
  }
}

export function setBypassAllowed(allowed: boolean): void {
  try {
    window.localStorage.setItem(KEY, allowed ? "true" : "false");
  } catch {
    return;
  }
  window.dispatchEvent(new Event(EVENT));
}

export function onBypassGateChange(listener: () => void): () => void {
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
