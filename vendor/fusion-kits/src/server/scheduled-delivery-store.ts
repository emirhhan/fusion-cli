import type { DatabaseSync } from 'node:sqlite';
import type {
  ScheduleDeliveryReceipt,
  StagedDelivery,
} from './scheduled-delivery.js';
export interface AcceptedDelivery extends StagedDelivery {
  root: string | null;
  threadId: string | null;
  activated: number;
}
export function deliveryRecord(
  db: DatabaseSync,
  taskId: string,
): AcceptedDelivery | undefined {
  return db
    .prepare('SELECT * FROM schedule_deliveries WHERE taskId=?')
    .get(taskId) as unknown as AcceptedDelivery | undefined;
}
export function stageRecord(
  db: DatabaseSync,
  occurrenceId: string,
  digest: string,
  prompt: string,
  root: string,
  threadId: string,
): StagedDelivery {
  const taskId = `schedule-${occurrenceId}`;
  db.prepare(
    'INSERT OR IGNORE INTO schedule_deliveries (occurrenceId,taskId,digest,prompt,root,threadId) VALUES (?,?,?,?,?,?)',
  ).run(occurrenceId, taskId, digest, prompt, root, threadId);
  const row = deliveryRecord(db, taskId);
  if (
    !row ||
    row.digest !== digest ||
    row.prompt !== prompt ||
    row.root !== root ||
    row.threadId !== threadId
  )
    throw new Error(
      'Teslim kimliği farklı veya eksik görev girdileriyle tekrar kullanıldı.',
    );
  return { occurrenceId, taskId, digest, prompt };
}
export function activateRecord(
  db: DatabaseSync,
  occurrenceId: string,
  digest: string,
  now: number,
  event: (taskId: string) => void,
): ScheduleDeliveryReceipt {
  const row = db
    .prepare('SELECT * FROM schedule_deliveries WHERE occurrenceId=?')
    .get(occurrenceId) as unknown as AcceptedDelivery | undefined;
  if (!row || row.digest !== digest || !row.root || !row.threadId)
    throw new Error('Kalıcı teslim kaydı eşleşmiyor veya kapsamı eksik.');
  if (!row.activated) {
    db.prepare(
      "INSERT INTO tasks (id, prompt, status, intervalSeconds, nextRunAt, createdAt, updatedAt, error, lease, leaseUntil) VALUES (?, ?, 'queued', NULL, NULL, ?, ?, NULL, NULL, NULL)",
    ).run(row.taskId, row.prompt, now, now);
    db.prepare(
      'UPDATE schedule_deliveries SET activated=1 WHERE occurrenceId=?',
    ).run(occurrenceId);
    event(row.taskId);
  }
  return { occurrenceId, taskId: row.taskId, status: 'queued' };
}
/** Önceki eksik kapsam kayıtlarına root uydurulmaz; yürütme kapısı bunları reddeder. */
export function migrateDeliveryScope(db: DatabaseSync): void {
  const columns = db.prepare('PRAGMA table_info(schedule_deliveries)').all();
  if (!columns.some((column) => column.name === 'root'))
    db.exec('ALTER TABLE schedule_deliveries ADD COLUMN root TEXT');
  if (!columns.some((column) => column.name === 'threadId'))
    db.exec('ALTER TABLE schedule_deliveries ADD COLUMN threadId TEXT');
}
