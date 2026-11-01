/**
 * Auto kipinin ayarla kapatılması (#85).
 *
 * Claude Code: bir ayar dosyasında `disableAutoMode: "disable"` (ya da
 * `permissions.disableAutoMode`) auto kipini engeller ve kip seçicisinden çıkarır. Çekirdek
 * bunu `oturum.durum.auto_kapali` ile bildirir; değer gelmediyse auto açık sayılır (çekirdek
 * yine de seçimi reddeder).
 */
const EVENT = "fusion:auto-gate";
let disabled = false;

export function autoPolicyDisabled(): boolean {
  return disabled;
}

export function setAutoPolicyDisabled(next: boolean): void {
  if (disabled === next) return;
  disabled = next;
  window.dispatchEvent(new Event(EVENT));
}

/** Çekirdek yanıtındaki `auto_kapali` alanını uygula; alan yoksa dokunma. */
export function readAutoGate(result: Record<string, unknown>): void {
  if (typeof result.auto_kapali === "boolean") setAutoPolicyDisabled(result.auto_kapali);
}

export function onAutoGateChange(listener: () => void): () => void {
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
