/**
 * "İzinleri atla kipine izin ver" anahtarı (#442).
 *
 * Claude Code Desktop: Bypass permissions ancak Settings › Code › "Allow bypass permissions
 * mode" açıldıktan sonra seçilebilir. Anahtar kapalıyken mod menüsünde görünmez. Değer bu
 * bilgisayarın tarayıcı deposundadır; okunamazsa kapalı sayılır (güvenli taraf).
 *
 * Team/Enterprise'daki kurum politikasının karşılığı: çekirdek `oturum.durum.bypass_kapali`
 * ile bildirir (bir Claude ayar dosyasında `disableBypassPermissionsMode: "disable"`). O
 * zaman anahtar ne olursa olsun Bypass seçilemez ve Ayarlar'daki anahtar kilitlenir.
 */
const KEY = "fusion.allowBypassPermissionsMode";
const EVENT = "fusion:bypass-gate";
let policyDisabled = false;

/** Ayar/kurum politikası Bypass'ı kapattı mı (çekirdekten gelen son değer). */
export function bypassPolicyDisabled(): boolean {
  return policyDisabled;
}

export function setBypassPolicyDisabled(disabled: boolean): void {
  if (policyDisabled === disabled) return;
  policyDisabled = disabled;
  window.dispatchEvent(new Event(EVENT));
}

export function bypassAllowed(): boolean {
  if (policyDisabled) return false;
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
