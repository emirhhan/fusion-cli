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
