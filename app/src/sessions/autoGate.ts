/**
 * Auto kipinin ayarla kapatılması (#85).
 *
 * Claude Code: bir ayar dosyasında `disableAutoMode: "disable"` (ya da
 * `permissions.disableAutoMode`) auto kipini engeller ve kip seçicisinden çıkarır. Çekirdek
 * bunu `oturum.durum.auto_kapali` ile bildirir; değer gelmediyse auto açık sayılır (çekirdek
 * yine de seçimi reddeder).
 *
 * Değer OTURUM başınadır: farklı projelerdeki sohbetlerin ayarı farklı olabilir. Kip
 * seçicisi etkin oturumun değerini okur; başka oturumdan geç gelen yanıt onu değiştirmez.
 */
const EVENT = "fusion:auto-gate";
/** Oturum kimliği verilmeyen çağrıların (eski çağıranlar, testler) anahtarı. */
const NO_SESSION = "";
let active = NO_SESSION;
let bySession: Readonly<Record<string, boolean>> = {};

export function autoPolicyDisabled(): boolean {
  return bySession[active] ?? false;
}

function notifyIfChanged(before: boolean): void {
  if (autoPolicyDisabled() !== before) window.dispatchEvent(new Event(EVENT));
}

/** Bir oturumun değerini yaz; oturum verilmezse etkin oturumunki. */
export function setAutoPolicyDisabled(next: boolean, sessionId: string = active): void {
  if (bySession[sessionId] === next) return;
  const before = autoPolicyDisabled();
  bySession = { ...bySession, [sessionId]: next };
  notifyIfChanged(before);
}

/** Kip seçicisinin izlediği etkin oturum (null: oturum yok). */
export function setAutoGateSession(sessionId: string | null): void {
  const next = sessionId ?? NO_SESSION;
  if (next === active) return;
  const before = autoPolicyDisabled();
  active = next;
  notifyIfChanged(before);
}

/** Çekirdek yanıtındaki `auto_kapali` alanını o oturuma uygula; alan yoksa dokunma. */
export function readAutoGate(result: Record<string, unknown>, sessionId?: string): void {
  if (typeof result.auto_kapali === "boolean") setAutoPolicyDisabled(result.auto_kapali, sessionId ?? active);
}

export function onAutoGateChange(listener: () => void): () => void {
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
