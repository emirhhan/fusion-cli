/**
 * Görev durumu ve olay sözleşmesi — `core/task_protocol.py` ile aynı (WP07).
 *
 * Ortak kaynak `fixtures/task-contract.json`; Python ve TypeScript testleri aynı
 * dosyayı okur. Tel sınırında gelen olay burada doğrulanır: bilinmeyen durum ya da
 * eksik alan sessizce "başarı" sayılmaz.
 */

export const TASK_SCHEMA_VERSION = 1;

export const RUN_STATUSES = [
  "queued",
  "dispatching",
  "running",
  "waiting_user",
  "paused",
  "cancelling",
  "succeeded",
  "failed",
  "cancelled",
  "needs_reconciliation",
] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];

export const TERMINAL_STATUSES: ReadonlySet<RunStatus> = new Set(["succeeded", "failed", "cancelled"]);

export const OPERATION_OUTCOMES = ["succeeded", "failed", "denied", "blocked", "cancelled", "unknown"] as const;
export type OperationOutcome = (typeof OPERATION_OUTCOMES)[number];

export interface RunEvent {
  schema_version: number;
  event_id: string;
  run_id: string;
  seq: number;
  kind: string;
  at: number;
  payload: Record<string, unknown>;
}

export function isRunStatus(value: unknown): value is RunStatus {
  return typeof value === "string" && (RUN_STATUSES as readonly string[]).includes(value);
}

/** Tel olayını doğrula; sözleşmeye uymuyorsa `null` (çağıran snapshot ister). */
export function parseRunEvent(value: unknown): RunEvent | null {
  if (!value || typeof value !== "object") return null;
  const event = value as Record<string, unknown>;
  const valid =
    event.schema_version === TASK_SCHEMA_VERSION &&
    typeof event.event_id === "string" &&
    typeof event.run_id === "string" &&
    Number.isInteger(event.seq) &&
    (event.seq as number) > 0 &&
    typeof event.kind === "string" &&
    typeof event.at === "number" &&
    !!event.payload &&
    typeof event.payload === "object" &&
    !Array.isArray(event.payload);
  return valid ? (event as unknown as RunEvent) : null;
}

/** Sıra boşluğu var mı? Varsa istemci olayları ya da snapshot'ı yeniden istemeli. */
export function hasSequenceGap(lastSeenSeq: number, events: readonly RunEvent[]): boolean {
  let expected = lastSeenSeq + 1;
  for (const event of events) {
    if (event.seq < expected) continue; // Tekrar eden olay atlanır.
    if (event.seq !== expected) return true;
    expected += 1;
  }
  return false;
}
