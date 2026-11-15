/** App ve Kits makbuzları aynı normalized alanları taşır. */
export interface SubmissionReceipt {
  requestId: string;
  sessionId: string;
  turnId: string | null;
  state: string;
  error: string | null;
}
export function submissionReceipt(value: unknown): SubmissionReceipt | null {
  if (!value || typeof value !== 'object') return null;
  const wire = value as Record<string, unknown>;
  if (
    typeof wire.gonderim_id !== 'string' ||
    typeof wire.oturum_id !== 'string' ||
    typeof wire.durum !== 'string' ||
    ![
      'queued',
      'accepted',
      'running',
      'completed',
      'failed',
      'cancelled',
      'recoveryRequired',
    ].includes(wire.durum)
  )
    return null;
  return {
    requestId: wire.gonderim_id,
    sessionId: wire.oturum_id,
    turnId: typeof wire.tur_id === 'string' ? wire.tur_id : null,
    state: wire.durum,
    error: typeof wire.hata_kodu === 'string' ? wire.hata_kodu : null,
  };
}
