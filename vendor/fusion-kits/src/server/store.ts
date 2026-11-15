import {
  stageRecord,
  activateRecord,
  deliveryRecord,
  migrateDeliveryScope,
  type AcceptedDelivery,
} from './scheduled-delivery-store.js';
import type {
  StagedDelivery,
  ScheduleDeliveryReceipt,
} from './scheduled-delivery.js';
import { DatabaseSync } from 'node:sqlite';
import { randomUUID } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import type {
  Action,
  Detail,
  Memory,
  Result,
  Run,
  Settings,
  Task,
  TaskIntent,
  TaskEvent,
} from '../shared/types.js';

/** Devam notuna taşınan en fazla ilerleme kaydı. */
const RESUME_EVENTS = 20;
/** Çalışanın kendi yaşam döngüsü kayıtları; işin ilerlemesi değil. */
const SYSTEM_EVENTS = new Set([
  'Araştırma çalışanı başladı.',
  'Sunucu duruyor; yeniden başlatma için sıraya alındı.',
  'Önceki çalışanın kirası doldu; güvenle yeniden deneniyor.',
  'Bu görev kendi Intelligence sohbetinde çalıştırılıyor.',
]);
export type Claim = Task & { lease: string };
const defaults: Settings = {
  name: 'Kit',
  paused: false,
  researchAllowed: true,
  memoryAllowed: true,
};
export class Store {
  private db: DatabaseSync;
  constructor(path: string) {
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, prompt TEXT NOT NULL, status TEXT NOT NULL, intervalSeconds INTEGER, nextRunAt INTEGER, createdAt INTEGER NOT NULL, updatedAt INTEGER NOT NULL, error TEXT, lease TEXT, leaseUntil INTEGER);
      CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, taskId TEXT NOT NULL, status TEXT NOT NULL, startedAt INTEGER NOT NULL, finishedAt INTEGER, result TEXT, error TEXT);
      CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, taskId TEXT NOT NULL, runId TEXT, text TEXT NOT NULL, createdAt INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, text TEXT NOT NULL, createdAt INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS schedule_deliveries (occurrenceId TEXT PRIMARY KEY, taskId TEXT UNIQUE NOT NULL, digest TEXT NOT NULL, prompt TEXT NOT NULL, activated INTEGER NOT NULL DEFAULT 0, root TEXT, threadId TEXT);
      CREATE TABLE IF NOT EXISTS fusion_projects (name TEXT PRIMARY KEY, path TEXT NOT NULL, createdAt INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS tasks_due ON tasks(status, nextRunAt);
      CREATE INDEX IF NOT EXISTS runs_task ON runs(taskId, startedAt);
      CREATE INDEX IF NOT EXISTS events_task ON events(taskId, id);`);
    const taskColumns = this.db.prepare('PRAGMA table_info(tasks)').all();
    if (!taskColumns.some((column) => column.name === 'intent'))
      this.db.exec(
        "ALTER TABLE tasks ADD COLUMN intent TEXT NOT NULL DEFAULT 'user_requested' CHECK(intent IN ('user_requested', 'proactive_research'))",
      );
    migrateDeliveryScope(this.db);
    this.db
      .prepare('INSERT OR IGNORE INTO settings VALUES (1, ?)')
      .run(JSON.stringify(defaults));
  }
  close() {
    this.db.close();
  }
  private transaction<T>(fn: () => T): T {
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const value = fn();
      this.db.exec('COMMIT');
      return value;
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }
  settings(): Settings {
    const row = this.db
      .prepare('SELECT value FROM settings WHERE id=1')
      .get() as { value: string };
    return JSON.parse(row.value) as Settings;
  }
  updateSettings(patch: Partial<Settings>): Settings {
    return this.transaction(() => {
      const previous = this.settings();
      const settings = { ...previous, ...patch };
      this.db
        .prepare('UPDATE settings SET value=? WHERE id=1')
        .run(JSON.stringify(settings));
      if (
        (!previous.paused && settings.paused) ||
        (previous.researchAllowed && !settings.researchAllowed) ||
        (previous.memoryAllowed && !settings.memoryAllowed)
      ) {
        const running = this.tasks().filter((t) => t.status === 'running');
        for (const task of running) {
          this.invalidate(
            task,
            'queued',
            'Ayarlar değiştiği için çalıştırma durduruldu.',
          );
        }
      }
      return settings;
    });
  }
  tasks(): Task[] {
    return this.db
      .prepare('SELECT * FROM tasks ORDER BY createdAt DESC')
      .all() as unknown as Task[];
  }
  task(id: string): Task | undefined {
    return this.db
      .prepare('SELECT * FROM tasks WHERE id=?')
      .get(id) as unknown as Task | undefined;
  }
  createTask(prompt: string, intervalSeconds: number | null = null): Task {
    return this.createTaskWithIntent(prompt, intervalSeconds, 'user_requested');
  }
  /** Trusted host entry only; public routes never accept an execution intent. */
  createProactiveResearchTask(
    prompt: string,
    intervalSeconds: number | null = null,
  ): Task {
    return this.createTaskWithIntent(
      prompt,
      intervalSeconds,
      'proactive_research',
    );
  }
  private createTaskWithIntent(
    prompt: string,
    intervalSeconds: number | null,
    intent: TaskIntent,
  ): Task {
    const now = Date.now();
    const id = randomUUID();
    this.db
      .prepare(
        "INSERT INTO tasks (id, prompt, status, intervalSeconds, nextRunAt, createdAt, updatedAt, error, lease, leaseUntil, intent) VALUES (?, ?, 'queued', ?, NULL, ?, ?, NULL, NULL, NULL, ?)",
      )
      .run(id, prompt, intervalSeconds, now, now, intent);
    this.event(id, null, 'Görev araştırma kuyruğuna eklendi.');
    return this.task(id)!;
  }
  taskForRun(runId: string): Task | undefined {
    return this.db
      .prepare(
        'SELECT tasks.* FROM tasks JOIN runs ON runs.taskId=tasks.id WHERE runs.id=?',
      )
      .get(runId) as unknown as Task | undefined;
  }
  stageDelivery(
    occurrenceId: string,
    digest: string,
    prompt: string,
    root: string,
    threadId: string,
  ): StagedDelivery {
    return this.transaction(() =>
      stageRecord(this.db, occurrenceId, digest, prompt, root, threadId),
    );
  }
  activateDelivery(
    occurrenceId: string,
    digest: string,
  ): ScheduleDeliveryReceipt {
    return this.transaction(() =>
      activateRecord(this.db, occurrenceId, digest, Date.now(), (taskId) =>
        this.event(
          taskId,
          null,
          'Zamanlanmış görev kalıcı sıraya teslim edildi.',
        ),
      ),
    );
  }
  scheduledDelivery(taskId: string): AcceptedDelivery | undefined {
    return deliveryRecord(this.db, taskId);
  }
  detail(id: string): Detail | undefined {
    const task = this.task(id);
    if (!task) return undefined;
    const rows = this.db
      .prepare(
        'SELECT * FROM runs WHERE taskId=? ORDER BY startedAt DESC, rowid DESC',
      )
      .all(id) as unknown as (Omit<Run, 'result'> & {
      result: string | null;
    })[];
    return {
      task,
      runs: rows.map((row) => ({
        ...row,
        result: row.result ? (JSON.parse(row.result) as Result) : null,
      })),
      events: this.db
        .prepare('SELECT * FROM events WHERE taskId=? ORDER BY id')
        .all(id) as unknown as TaskEvent[],
    };
  }
  event(taskId: string, runId: string | null, text: string) {
    this.db
      .prepare(
        'INSERT INTO events (taskId, runId, text, createdAt) VALUES (?, ?, ?, ?)',
      )
      .run(taskId, runId, text, Date.now());
  }
  private invalidate(task: Task, status: string, reason: string) {
    const now = Date.now();
    if (task.lease)
      this.db
        .prepare(
          "UPDATE runs SET status='interrupted', finishedAt=?, error=? WHERE id=? AND status='running'",
        )
        .run(now, reason, task.lease);
    this.db
      .prepare(
        'UPDATE tasks SET status=?, lease=NULL, leaseUntil=NULL, updatedAt=? WHERE id=?',
      )
      .run(status, now, task.id);
    this.event(task.id, task.lease, reason);
  }
  action(id: string, action: Action): Task | undefined {
    return this.transaction(() => {
      const task = this.task(id);
      if (!task) return undefined;
      if (action === 'run' && task.status === 'running') return task;
      const status =
        action === 'run'
          ? 'queued'
          : action === 'pause'
            ? 'paused'
            : 'cancelled';
      this.invalidate(
        task,
        status,
        action === 'run'
          ? 'Görev yeni bir çalıştırma için sıraya alındı.'
          : `Task ${status}.`,
      );
      this.db
        .prepare('UPDATE tasks SET error=NULL, nextRunAt=NULL WHERE id=?')
        .run(id);
      return this.task(id);
    });
  }
  schedule(id: string, intervalSeconds: number | null): Task | undefined {
    const task = this.task(id);
    if (!task) return undefined;
    const next =
      intervalSeconds && task.status === 'completed'
        ? Date.now() + intervalSeconds * 1000
        : null;
    this.db
      .prepare(
        'UPDATE tasks SET intervalSeconds=?, nextRunAt=?, updatedAt=? WHERE id=?',
      )
      .run(intervalSeconds, next, Date.now(), id);
    this.event(
      id,
      null,
      intervalSeconds
        ? `Başarılı bir çalıştırmadan sonra her ${intervalSeconds / 60} dakikada bir tekrarlanır.`
        : 'Tekrar planı kaldırıldı.',
    );
    return this.task(id);
  }
  claim(now = Date.now()): Claim | null {
    return this.transaction(() => {
      const settings = this.settings();
      if (settings.paused || !settings.researchAllowed) return null;
      const expired = this.db
        .prepare("SELECT * FROM tasks WHERE status='running' AND leaseUntil<=?")
        .all(now) as unknown as Task[];
      for (const task of expired)
        this.invalidate(
          task,
          'queued',
          'Önceki çalışanın kirası doldu; güvenle yeniden deneniyor.',
        );
      const task = this.db
        .prepare(
          "SELECT * FROM tasks WHERE status='queued' OR (status='completed' AND nextRunAt IS NOT NULL AND nextRunAt<=?) ORDER BY createdAt LIMIT 1",
        )
        .get(now) as unknown as Task | undefined;
      if (!task) return null;
      const lease = randomUUID();
      this.db
        .prepare(
          "UPDATE tasks SET status='running', lease=?, leaseUntil=?, nextRunAt=NULL, error=NULL, updatedAt=? WHERE id=?",
        )
        .run(lease, now + 180_000, now, task.id);
      this.db
        .prepare(
          "INSERT INTO runs VALUES (?, ?, 'running', ?, NULL, NULL, NULL)",
        )
        .run(lease, task.id, now);
      this.event(task.id, lease, 'Araştırma çalışanı başladı.');
      return { ...this.task(task.id)!, lease };
    });
  }
  /** Aktif çalışan yalnız kendi lease'ini uzatır; iptal edilen görevi diriltmez. */
  heartbeat(claim: Claim, now = Date.now()): boolean {
    return (
      this.db
        .prepare(
          "UPDATE tasks SET leaseUntil=? WHERE id=? AND lease=? AND status='running'",
        )
        .run(now + 180_000, claim.id, claim.lease).changes === 1
    );
  }
  owns(claim: Claim): boolean {
    const task = this.task(claim.id);
    return task?.status === 'running' && task.lease === claim.lease;
  }
  finish(claim: Claim, result: Result, now = Date.now()): boolean {
    return this.transaction(() => {
      if (!this.owns(claim)) return false;
      const task = this.task(claim.id)!;
      this.db
        .prepare(
          "UPDATE runs SET status='completed', finishedAt=?, result=? WHERE id=?",
        )
        .run(now, JSON.stringify(result), claim.lease);
      this.db
        .prepare(
          "UPDATE tasks SET status='completed', lease=NULL, leaseUntil=NULL, updatedAt=?, nextRunAt=? WHERE id=?",
        )
        .run(
          now,
          task.intervalSeconds ? now + task.intervalSeconds * 1000 : null,
          claim.id,
        );
      this.event(
        claim.id,
        claim.lease,
        result.sample ? 'Kurgusal örnek özet hazır.' : 'Araştırma özeti hazır.',
      );
      return true;
    });
  }
  /**
   * Önceki deneme yarıda kesildiyse (kapanış, lease süresi) onun ilerleme
   * kayıtları; yeni deneme işi baştan değil kaldığı yerden sürdürsün diye.
   */
  resumeNote(claim: Claim): string | undefined {
    const previous = this.db
      .prepare(
        'SELECT id, status FROM runs WHERE taskId=? AND id<>? ORDER BY startedAt DESC, rowid DESC LIMIT 1',
      )
      .get(claim.id, claim.lease) as { id: string; status: string } | undefined;
    if (previous?.status !== 'interrupted') return undefined;
    const lines = (
      this.db
        .prepare(
          'SELECT text FROM events WHERE runId=? ORDER BY id DESC LIMIT ?',
        )
        .all(previous.id, RESUME_EVENTS) as { text: string }[]
    )
      .map((row) => row.text)
      .filter((text) => !SYSTEM_EVENTS.has(text))
      .reverse();
    return lines.length ? lines.join('\n') : undefined;
  }
  fusionProjects(): Record<string, string> {
    const rows = this.db
      .prepare('SELECT name, path FROM fusion_projects ORDER BY createdAt')
      .all() as { name: string; path: string }[];
    return Object.fromEntries(rows.map((row) => [row.name, row.path]));
  }
  saveFusionProject(name: string, path: string) {
    this.db
      .prepare(
        'INSERT INTO fusion_projects VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET path=excluded.path',
      )
      .run(name, path, Date.now());
  }
  deleteFusionProject(name: string): boolean {
    return (
      this.db.prepare('DELETE FROM fusion_projects WHERE name=?').run(name)
        .changes === 1
    );
  }
  release(claim: Claim, reason: string) {
    this.transaction(() => {
      if (this.owns(claim)) this.invalidate(claim, 'queued', reason);
    });
  }
  fail(claim: Claim, error: string) {
    this.transaction(() => {
      if (!this.owns(claim)) return;
      const now = Date.now();
      this.db
        .prepare(
          "UPDATE runs SET status='failed', finishedAt=?, error=? WHERE id=?",
        )
        .run(now, error, claim.lease);
      this.db
        .prepare(
          "UPDATE tasks SET status='failed', lease=NULL, leaseUntil=NULL, error=?, updatedAt=? WHERE id=?",
        )
        .run(error, now, claim.id);
      this.event(claim.id, claim.lease, error);
    });
  }
  memories(): Memory[] {
    return this.db
      .prepare('SELECT * FROM memories ORDER BY createdAt DESC')
      .all() as unknown as Memory[];
  }
  saveMemory(text: string, id: string = randomUUID()): Memory {
    this.db
      .prepare(
        'INSERT INTO memories VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET text=excluded.text',
      )
      .run(id, text, Date.now());
    return this.db
      .prepare('SELECT * FROM memories WHERE id=?')
      .get(id) as unknown as Memory;
  }
  deleteMemory(id: string): boolean {
    return (
      this.db.prepare('DELETE FROM memories WHERE id=?').run(id).changes > 0
    );
  }
}
