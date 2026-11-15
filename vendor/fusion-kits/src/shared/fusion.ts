import type { SubmissionReceipt } from './submission.js';
export type FusionStatus =
  'idle' | 'running' | 'waiting' | 'completed' | 'failed' | 'cancelled';
/** Fusion turunun doğrulama kanıtı (Fusion `kanit` alanından). */
export interface FusionEvidence {
  /** null: değişiklik yok, doğrulanacak bir şey yok. */
  verified: boolean | null;
  blocking: boolean;
  falseClaim: boolean;
  changed: string[];
  problems: string[];
}
export interface FusionModelReceipt {
  callId: string;
  requestedModel: string;
  observedModel: string | null;
  appliedModel: string;
  requestedEffort: string | null;
  appliedEffort: string | null;
  effortReason: string | null;
}
export interface FusionSnapshot {
  modelReceipts?: FusionModelReceipt[];
  receipt?: SubmissionReceipt;
  configured: boolean;
  root?: string;
  runId: string | null;
  status: FusionStatus;
  text: string;
  error: string | null;
  events: string[];
  question: { id: string; data: Record<string, unknown> } | null;
  evidence?: FusionEvidence | null;
}

/** Olay kimliği makbuzu birleştirir; gözlem yokken istenen kimlik uydurulmaz. */
export function modelReceipt(
  data: Record<string, unknown>,
): FusionModelReceipt | null {
  if (
    data.olay !== 'ModelCallFinished' ||
    data.background === true ||
    (typeof data.agent_id === 'string' && data.agent_id !== '')
  )
    return null;
  const result = data.result as Record<string, unknown> | undefined;
  if (!result || result.ok !== true || typeof result.model !== 'string')
    return null;
  const stringOrNull = (value: unknown): string | null =>
    typeof value === 'string' && value ? value : null;
  return {
    callId:
      stringOrNull(data.call_id) ??
      stringOrNull(data.event_id) ??
      `legacy:${JSON.stringify([
        data.session_id ?? null,
        data.turn_id ?? null,
        data.sequence ?? data.seq ?? null,
        data.requested_model ?? null,
        result.model,
        result.served_by ?? null,
        result.requested_effort ?? null,
        result.applied_effort ?? null,
      ])}`,
    requestedModel: stringOrNull(data.requested_model) ?? result.model,
    appliedModel: result.model,
    observedModel: stringOrNull(result.served_by),
    requestedEffort: stringOrNull(result.requested_effort),
    appliedEffort: stringOrNull(result.applied_effort),
    effortReason: stringOrNull(result.effort_reason),
  };
}
