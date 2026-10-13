import type { SessionAttachment, VoiceTurnMetadata } from "./types";

export interface SubmissionSnapshot {
  requestId: string;
  sessionId: string;
  root: string;
  task: string;
  attachments: SessionAttachment[];
  voice?: VoiceTurnMetadata;
  state: string;
  turnId?: string;
}
const key = (sessionId: string) => `fusion.submissions:${sessionId}`;
export function loadSubmissions(sessionId: string): SubmissionSnapshot[] {
  const raw = localStorage.getItem(key(sessionId));
  if (!raw) return [];
  const parsed: unknown = JSON.parse(raw);
  if (!Array.isArray(parsed)) throw new Error("Gönderim kaydı okunamadı.");
  return parsed.filter((value): value is SubmissionSnapshot => {
    if (!value || typeof value !== "object") return false;
    const row = value as Record<string, unknown>;
    return typeof row.requestId === "string" && row.sessionId === sessionId
      && typeof row.root === "string" && typeof row.task === "string"
      && typeof row.state === "string" && Array.isArray(row.attachments);
  });
}
export function saveSubmission(snapshot: SubmissionSnapshot): void {
  const snapshots = loadSubmissions(snapshot.sessionId);
  const next = snapshots.filter((entry) => entry.requestId !== snapshot.requestId);
  localStorage.setItem(key(snapshot.sessionId), JSON.stringify([...next, {...snapshots.find((entry) => entry.requestId === snapshot.requestId), ...snapshot}]));
}
export function updateSubmission(sessionId: string, requestId: string, state: string, turnId?: string): void {
  const snapshots = loadSubmissions(sessionId);
  localStorage.setItem(key(sessionId), JSON.stringify(snapshots.map((entry) =>
    entry.requestId === requestId ? { ...entry, state, ...(turnId ? {turnId} : {}) } : entry)));
}
export function deleteSubmissions(sessionId: string): void {
  localStorage.removeItem(key(sessionId));
}
export function moveSubmissions(sessionId: string, source: string, target: string): void {
  const snapshots = loadSubmissions(sessionId);
  localStorage.setItem(key(sessionId), JSON.stringify(snapshots.map((entry) => entry.root === source ? { ...entry, root: target } : entry)));
}
