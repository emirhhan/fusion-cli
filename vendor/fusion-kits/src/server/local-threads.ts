import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { Observable, concat, defer, from } from 'rxjs';
import { finalize, shareReplay, switchMap, tap } from 'rxjs/operators';
import {
  EventType,
  compactEvents,
  type BaseEvent,
  type Message,
} from '@ag-ui/client';
import {
  AgentRunner,
  InMemoryAgentRunner,
  type AgentRunnerConnectRequest,
  type AgentRunnerIsRunningRequest,
  type AgentRunnerRunRequest,
  type AgentRunnerStopRequest,
} from '@copilotkit/runtime/v2';

export interface LocalThreadRecord {
  id: string;
  name: string | null;
  agentId: string;
  organizationId: string;
  createdById: string;
  archived: boolean;
  createdAt: string;
  updatedAt: string;
}

type Row = Record<string, unknown>;

/** Önceki koşularda görülmüş mesaj kimlikleri: yeniden kaydedilen girdide ayıklanır. */
function knownMessageIds(events: BaseEvent[]): Set<string> {
  const ids = new Set<string>();
  for (const event of events) {
    const record = event as unknown as Record<string, unknown>;
    if (typeof record.messageId === 'string') ids.add(record.messageId);
    if (event.type === EventType.RUN_STARTED) {
      const input = record.input as { messages?: { id: string }[] } | undefined;
      for (const message of input?.messages ?? []) ids.add(message.id);
    }
  }
  return ids;
}

/** Süreç yeniden başladığında bellek deposu boştur; koşu başlangıcı bütün geçmişi
 * yeniden taşır. Diskte zaten duran mesajlar kayıttan düşürülür. */
export function withoutKnownInput(
  events: BaseEvent[],
  known: Set<string>,
): BaseEvent[] {
  return events.map((event) => {
    if (event.type !== EventType.RUN_STARTED) return event;
    const record = event as unknown as Record<string, unknown>;
    const input = record.input as { messages?: { id: string }[] } | undefined;
    if (!input?.messages) return event;
    return {
      ...record,
      input: {
        ...input,
        messages: input.messages.filter((message) => !known.has(message.id)),
      },
    } as unknown as BaseEvent;
  });
}

/**
 * Sohbetleri yerel SQLite dosyasında tutan koşucu. Dış bir sohbet servisi
 * gerektirmez: canlı koşu bellekteki koşucuya devredilir, biten her koşunun
 * olayları ve mesaj dökümü diske yazılır, yeniden bağlanan istemciye diskten verilir.
 */
export class LocalThreadRunner extends AgentRunner {
  readonly ɵsupportsLocalThreadEndpoints = true as const;
  private db: DatabaseSync;
  private live = new InMemoryAgentRunner();
  private submissions = new Map<string, Observable<BaseEvent>>();
  constructor(
    path: string,
    private ownerId: string,
    private threadName: (threadId: string) => string | null = () => null,
  ) {
    super();
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS local_runs (threadId TEXT NOT NULL, runId TEXT NOT NULL, agentId TEXT NOT NULL, createdAt INTEGER NOT NULL, events TEXT NOT NULL, PRIMARY KEY (threadId, runId));
      CREATE TABLE IF NOT EXISTS local_submissions (owner TEXT, threadId TEXT, runId TEXT, state TEXT, PRIMARY KEY(owner,threadId,runId));
      CREATE TABLE IF NOT EXISTS local_threads (threadId TEXT PRIMARY KEY, agentId TEXT NOT NULL, createdAt INTEGER NOT NULL, updatedAt INTEGER NOT NULL, messages TEXT NOT NULL);`);
    this.db
      .exec(`CREATE TABLE IF NOT EXISTS local_runs_owned (owner TEXT NOT NULL, threadId TEXT NOT NULL, runId TEXT NOT NULL, agentId TEXT NOT NULL, createdAt INTEGER NOT NULL, events TEXT NOT NULL, PRIMARY KEY(owner,threadId,runId));
      CREATE TABLE IF NOT EXISTS local_threads_owned (owner TEXT NOT NULL, threadId TEXT NOT NULL, agentId TEXT NOT NULL, createdAt INTEGER NOT NULL, updatedAt INTEGER NOT NULL, messages TEXT NOT NULL, PRIMARY KEY(owner,threadId));
      CREATE TABLE IF NOT EXISTS local_owner_migration (id INTEGER PRIMARY KEY, owner TEXT NOT NULL);`);
    this.db.exec('BEGIN IMMEDIATE');
    try {
      if (
        !this.db
          .prepare('SELECT owner FROM local_owner_migration WHERE id=1')
          .get()
      ) {
        this.db
          .prepare(
            'INSERT INTO local_runs_owned SELECT ?,threadId,runId,agentId,createdAt,events FROM local_runs',
          )
          .run(this.ownerId);
        this.db
          .prepare(
            'INSERT INTO local_threads_owned SELECT ?,threadId,agentId,createdAt,updatedAt,messages FROM local_threads',
          )
          .run(this.ownerId);
        this.db
          .prepare('INSERT INTO local_owner_migration VALUES (1,?)')
          .run(this.ownerId);
      }
      this.db.exec('COMMIT');
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }
  run(request: AgentRunnerRunRequest): Observable<BaseEvent> {
    const key = JSON.stringify([
      this.ownerId,
      request.threadId,
      request.input.runId,
    ]);
    return defer(() => {
      const active = this.submissions.get(key);
      if (active) return active;
      this.db.exec('BEGIN IMMEDIATE');
      let claimed = false;
      try {
        const row = this.db
          .prepare(
            'SELECT state FROM local_submissions WHERE owner=? AND threadId=? AND runId=?',
          )
          .get(this.ownerId, request.threadId, request.input.runId) as
          Row | undefined;
        if (!row) {
          this.db
            .prepare("INSERT INTO local_submissions VALUES (?,?,?,'accepted')")
            .run(this.ownerId, request.threadId, request.input.runId);
          claimed = true;
        }
        this.db.exec('COMMIT');
      } catch (error) {
        this.db.exec('ROLLBACK');
        throw error;
      }
      if (!claimed) {
        const receipt = this.db
          .prepare(
            'SELECT state FROM local_submissions WHERE owner=? AND threadId=? AND runId=?',
          )
          .get(this.ownerId, request.threadId, request.input.runId) as Row;
        if (!['completed', 'failed'].includes(String(receipt.state)))
          throw new Error(
            'Bu gönderimin sonucu belirsiz; yeniden çalıştırmadan önce kurtarma gerekli.',
          );
        const row = this.db
          .prepare(
            'SELECT events FROM local_runs_owned WHERE owner=? AND threadId=? AND runId=?',
          )
          .get(this.ownerId, request.threadId, request.input.runId) as
          Row | undefined;
        if (row) return from(JSON.parse(String(row.events)) as BaseEvent[]);
        throw new Error(
          'Bu gönderimin sonucu belirsiz; yeniden çalıştırmadan önce kurtarma gerekli.',
        );
      }
      const collected: BaseEvent[] = [];
      let state = 'recoveryRequired';
      const stream = defer(() => this.live.run(request)).pipe(
        tap((event) => {
          collected.push(event);
          if (event.type === EventType.RUN_FINISHED) state = 'completed';
          if (event.type === EventType.RUN_ERROR) state = 'failed';
        }),
        finalize(() => {
          this.persist(request, collected);
          this.db
            .prepare(
              'UPDATE local_submissions SET state=? WHERE owner=? AND threadId=? AND runId=?',
            )
            .run(state, this.ownerId, request.threadId, request.input.runId);
          this.submissions.delete(key);
        }),
        shareReplay({ bufferSize: Infinity, refCount: false }),
      );
      this.submissions.set(key, stream);
      return stream;
    });
  }
  connect(request: AgentRunnerConnectRequest): Observable<BaseEvent> {
    return defer(() =>
      from(this.live.isRunning({ threadId: request.threadId })),
    ).pipe(
      switchMap((running) => {
        const stored = from(this.getThreadEvents(request.threadId));
        return running ? concat(stored, this.live.connect(request)) : stored;
      }),
    );
  }
  isRunning(request: AgentRunnerIsRunningRequest): Promise<boolean> {
    return this.live.isRunning(request);
  }
  stop(request: AgentRunnerStopRequest): Promise<boolean | undefined> {
    return this.live.stop(request);
  }
  ensureThread(threadId: string, agentId: string): void {
    const now = Date.now();
    this.db
      .prepare(
        'INSERT OR IGNORE INTO local_threads_owned (owner, threadId, agentId, createdAt, updatedAt, messages) VALUES (?, ?, ?, ?, ?, ?)',
      )
      .run(this.ownerId, threadId, agentId, now, now, '[]');
  }
  listThreads(): LocalThreadRecord[] {
    const rows = this.db
      .prepare(
        'SELECT * FROM local_threads_owned WHERE owner=? ORDER BY updatedAt DESC',
      )
      .all(this.ownerId) as Row[];
    return rows.map((row) => ({
      id: String(row.threadId),
      name: this.threadName(String(row.threadId)),
      agentId: String(row.agentId),
      organizationId: '',
      createdById: this.ownerId,
      archived: false,
      createdAt: new Date(Number(row.createdAt)).toISOString(),
      updatedAt: new Date(Number(row.updatedAt)).toISOString(),
    }));
  }
  getThreadMessages(threadId: string): Message[] {
    const row = this.db
      .prepare(
        'SELECT messages FROM local_threads_owned WHERE owner=? AND threadId=?',
      )
      .get(this.ownerId, threadId) as Row | undefined;
    return row ? (JSON.parse(String(row.messages)) as Message[]) : [];
  }
  getThreadEvents(threadId: string): BaseEvent[] {
    const rows = this.db
      .prepare(
        'SELECT events FROM local_runs_owned WHERE owner=? AND threadId=? ORDER BY createdAt, rowid',
      )
      .all(this.ownerId, threadId) as Row[];
    return compactEvents(
      rows.flatMap((row) => JSON.parse(String(row.events)) as BaseEvent[]),
    );
  }
  getThreadState(): Record<string, unknown> | null {
    return null;
  }
  clearThreads(): void {
    if (this.submissions.size)
      throw new Error('Çalışan gönderim bitmeden sohbetler temizlenemez.');
    this.db.exec('BEGIN IMMEDIATE');
    try {
      this.db
        .prepare('DELETE FROM local_runs_owned WHERE owner=?')
        .run(this.ownerId);
      this.db
        .prepare('DELETE FROM local_threads_owned WHERE owner=?')
        .run(this.ownerId);
      this.db
        .prepare('DELETE FROM local_submissions WHERE owner=?')
        .run(this.ownerId);
      this.db.exec('COMMIT');
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
    this.live.clearThreads();
  }

  close(): void {
    this.db.close();
  }
  private persist(request: AgentRunnerRunRequest, collected: BaseEvent[]) {
    if (!collected.length) return;
    const { threadId } = request;
    const agentId = request.agent.agentId ?? 'default';
    const events = withoutKnownInput(
      compactEvents(collected),
      knownMessageIds(this.getThreadEvents(threadId)),
    );
    const now = Date.now();
    this.ensureThread(threadId, agentId);
    this.db
      .prepare(
        'INSERT OR REPLACE INTO local_runs_owned (owner, threadId, runId, agentId, createdAt, events) VALUES (?, ?, ?, ?, ?, ?)',
      )
      .run(
        this.ownerId,
        threadId,
        request.input.runId,
        agentId,
        now,
        JSON.stringify(events),
      );
    const messages = Array.isArray(request.agent.messages)
      ? request.agent.messages
      : [];
    if (messages.length)
      this.db
        .prepare(
          'UPDATE local_threads_owned SET updatedAt=?, messages=? WHERE owner=? AND threadId=?',
        )
        .run(now, JSON.stringify(messages), this.ownerId, threadId);
    else
      this.db
        .prepare(
          'UPDATE local_threads_owned SET updatedAt=? WHERE owner=? AND threadId=?',
        )
        .run(now, this.ownerId, threadId);
  }
}
