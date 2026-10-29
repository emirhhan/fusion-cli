/** Gönderim callback'lerinin tek kabul adapter'ı. */
export interface SubmissionReceipt {
  requestId: string;
  sessionId: string;
  turnId: string | null;
  state: string;
  error: string | null;
}
export type SubmissionResult = void | boolean | SubmissionReceipt;
export function submissionAccepted(result: SubmissionResult): boolean {
  if (result === undefined) return true;
  if (typeof result === "boolean") return result;
  return ["queued", "accepted", "running", "completed"].includes(result.state);
}

/** Wire metadata yalnız burada normalized UI makbuzuna çevrilir. */
export function normalizeSubmissionReceipt(value: unknown): SubmissionReceipt | null {
  if (!value || typeof value !== "object") return null;
  const wire = value as Record<string, unknown>;
  if (typeof wire.gonderim_id !== "string" || typeof wire.oturum_id !== "string"
    || typeof wire.durum !== "string" || !["queued", "accepted", "running", "completed", "failed", "cancelled", "recoveryRequired"].includes(wire.durum)) return null;
  return {requestId: wire.gonderim_id, sessionId: wire.oturum_id,
    turnId: typeof wire.tur_id === "string" ? wire.tur_id : null,
    state: wire.durum, error: typeof wire.hata_kodu === "string" ? wire.hata_kodu : null};
}

/** `<gonderim_id>:<sayı>` — çekirdeğin tur kimliği biçimi (`memory/submission_store.py`). */
export function isOwnTurnId(requestId: string, turnId: string): boolean {
  return turnId.startsWith(`${requestId}:`) && /^\d+$/.test(turnId.slice(requestId.length + 1));
}

/**
 * Yeniden denemede çekirdeğin vereceği tur kimliği (`<id>:<önceki+1>`). Önceki tur
 * kimliği bu isteğe ait değil ya da sonek sayı değilse `undefined`: yanlış bir
 * beklenen kimlik makbuzu hiç eşleştirmez. Ölçüldü (29 Ekim): `Number("x")+1`
 * `"<id>:NaN"` üretiyordu.
 */
export function nextAttemptTurnId(requestId: string, previous: string | undefined): string | undefined {
  if (!previous || !isOwnTurnId(requestId, previous)) return undefined;
  const attempt = Number(previous.slice(requestId.length + 1));
  return Number.isSafeInteger(attempt) ? `${requestId}:${attempt + 1}` : undefined;
}
