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

/** Bitmiş (kurtarma gerektirmeyen) gönderim durumları; bunlar sınırlı tutulur. */
const FINISHED_STATES = ["completed", "cancelled", "failed"];
/** Sohbet başına saklanan bitmiş gönderim sayısı (görev metni + ekler süresiz birikmesin). */
export const MAX_FINISHED_SUBMISSIONS = 20;

/** En yeni `MAX_FINISHED_SUBMISSIONS` bitmiş girdiyi ve tüm açık girdileri tutar. */
function pruneFinished(snapshots: SubmissionSnapshot[]): SubmissionSnapshot[] {
  let finished = snapshots.filter((entry) => FINISHED_STATES.includes(entry.state)).length;
  return snapshots.filter((entry) => {
    if (!FINISHED_STATES.includes(entry.state) || finished <= MAX_FINISHED_SUBMISSIONS) return true;
    finished -= 1;
    return false;
  });
}

/**
 * Yazma: önce sınırla; kota dolduysa bitmiş girdileri tamamen atıp BİR kez daha dene.
 * Yine olmazsa hata fırlar (gönderim taslağı sessizce kabul edilmez). Ölçüldü (29 Ekim):
 * girdiler hiç silinmediğinden 5 MB kotası dolunca `send` kalıcı kilitleniyordu.
 */
function persist(sessionId: string, snapshots: SubmissionSnapshot[]): void {
  try {
    localStorage.setItem(key(sessionId), JSON.stringify(pruneFinished(snapshots)));
  } catch (error) {
    const open = snapshots.filter((entry) => !FINISHED_STATES.includes(entry.state));
    if (open.length === snapshots.length) throw error;
    localStorage.setItem(key(sessionId), JSON.stringify(open));
  }
}

/**
 * Bozuk JSON (kısmi yazım, elle düzenleme) ya da dizi olmayan değer ATILIR ve anahtar
 * sıfırlanır. Ölçüldü (29 Ekim): `JSON.parse` korumasızdı, `send` içindeki saveSubmission her
 * seferinde fırlatıyor ve o sohbete hiçbir mesaj gönderilemiyordu.
 */
export function loadSubmissions(sessionId: string): SubmissionSnapshot[] {
  const raw = localStorage.getItem(key(sessionId));
  if (!raw) return [];
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { parsed = null; }
  if (!Array.isArray(parsed)) {
    try { localStorage.removeItem(key(sessionId)); } catch { /* Okuma yine boş döner. */ }
    return [];
  }
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
  persist(snapshot.sessionId, [...next, {...snapshots.find((entry) => entry.requestId === snapshot.requestId), ...snapshot}]);
}
export function updateSubmission(sessionId: string, requestId: string, state: string, turnId?: string): void {
  const snapshots = loadSubmissions(sessionId);
  persist(sessionId, snapshots.map((entry) =>
    entry.requestId === requestId ? { ...entry, state, ...(turnId ? {turnId} : {}) } : entry));
}
export function deleteSubmissions(sessionId: string): void {
  localStorage.removeItem(key(sessionId));
}
export function moveSubmissions(sessionId: string, source: string, target: string): void {
  const snapshots = loadSubmissions(sessionId);
  persist(sessionId, snapshots.map((entry) => entry.root === source ? { ...entry, root: target } : entry));
}
