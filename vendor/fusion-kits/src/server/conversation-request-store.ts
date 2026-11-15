import { createHash, randomUUID } from 'node:crypto';
import type { DatabaseSync } from 'node:sqlite';
import type { Conversation } from '../shared/types.js';

export class ConversationRequestError extends Error {
  constructor(
    message: string,
    readonly status: 400 | 403 | 409 | 503 = 409,
  ) {
    super(message);
  }
}
export interface ConversationRequestReceipt {
  requestId: string;
  threadId: string;
  dotId: string;
  fingerprint: string;
  state: 'accepted' | 'completed';
}
const identifier = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const fingerprint = (dotId: string, title: string) =>
  createHash('sha256')
    .update(JSON.stringify([dotId, title.trim()]))
    .digest('hex');

/** WorkspaceStore ile aynı bağlantı: kabul ve sohbet bağı tek transaction. */
export class ConversationRequestStore {
  constructor(
    private readonly db: DatabaseSync,
    private readonly ownerId: string,
    private readonly dotExists: (id: string) => boolean,
    private readonly binding: (id: string) => Conversation | undefined,
    private readonly bind: (
      id: string,
      dotId: string,
      title: string,
    ) => Conversation,
    private readonly createId: () => string = randomUUID,
  ) {
    db.exec(
      'CREATE TABLE IF NOT EXISTS conversation_requests (ownerId TEXT NOT NULL, requestId TEXT NOT NULL, schemaVersion INTEGER NOT NULL, threadId TEXT NOT NULL UNIQUE, dotId TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL, PRIMARY KEY(ownerId, requestId))',
    );
  }
  lookup(requestId: string): ConversationRequestReceipt | null {
    if (!identifier.test(requestId))
      throw new ConversationRequestError('Sohbet istek kimliği geçersiz.', 400);
    const row = this.db
      .prepare(
        'SELECT * FROM conversation_requests WHERE ownerId=? AND requestId=?',
      )
      .get(this.ownerId, requestId);
    if (!row) return null;
    if (
      row.schemaVersion !== 1 ||
      typeof row.threadId !== 'string' ||
      !identifier.test(row.threadId) ||
      typeof row.dotId !== 'string' ||
      !row.dotId ||
      typeof row.fingerprint !== 'string' ||
      !/^[a-f0-9]{64}$/.test(row.fingerprint) ||
      (row.state !== 'accepted' && row.state !== 'completed')
    ) {
      throw new ConversationRequestError(
        'Sohbet kabul kaydı doğrulanamadı; oluşturma tekrarlanmadı.',
      );
    }
    const receipt: ConversationRequestReceipt = {
      requestId,
      threadId: row.threadId,
      dotId: row.dotId,
      fingerprint: row.fingerprint,
      state: row.state,
    };
    if (receipt.state === 'completed') this.requireBinding(receipt);
    return receipt;
  }
  claim(
    requestId: string,
    dotId: string,
    title: string,
  ): { owner: boolean; receipt: ConversationRequestReceipt } {
    if (
      !identifier.test(requestId) ||
      !title.trim() ||
      title.trim().length > 120
    )
      throw new ConversationRequestError(
        'Sohbet istek kimliği veya başlığı geçersiz.',
        400,
      );
    if (!this.dotExists(dotId))
      throw new ConversationRequestError('Kit bulunamadı.', 403);
    return this.transaction(() => {
      const current = this.lookup(requestId);
      const digest = fingerprint(dotId, title);
      if (current) {
        if (current.fingerprint !== digest || current.dotId !== dotId)
          throw new ConversationRequestError(
            'Aynı sohbet isteği değişmiş girdilerle kullanılamaz.',
          );
        return { owner: false, receipt: current };
      }
      const receipt: ConversationRequestReceipt = {
        requestId,
        threadId: this.createId(),
        dotId,
        fingerprint: digest,
        state: 'accepted',
      };
      if (!identifier.test(receipt.threadId))
        throw new ConversationRequestError(
          'Ayrılan sohbet kimliği doğrulanamadı.',
        );
      this.db
        .prepare(
          'INSERT INTO conversation_requests (ownerId,requestId,schemaVersion,threadId,dotId,fingerprint,state) VALUES (?,?,1,?,?,?,?)',
        )
        .run(
          this.ownerId,
          requestId,
          receipt.threadId,
          dotId,
          digest,
          receipt.state,
        );
      return { owner: true, receipt };
    });
  }
  complete(requestId: string, title: string): Conversation {
    return this.transaction(() => {
      const receipt = this.lookup(requestId);
      if (!receipt || receipt.fingerprint !== fingerprint(receipt.dotId, title))
        throw new ConversationRequestError(
          'Sohbet kabulü veya başlık doğrulanamadı.',
        );
      if (receipt.state === 'completed') return this.requireBinding(receipt);
      if (!this.dotExists(receipt.dotId))
        throw new ConversationRequestError(
          'Kit erişimi değişti; sohbet bağlanmadı.',
          403,
        );
      const existing = this.binding(receipt.threadId);
      const conversation = existing
        ? this.requireBinding(receipt)
        : this.bind(receipt.threadId, receipt.dotId, title.trim());
      if (
        conversation.id !== receipt.threadId ||
        conversation.ownerId !== this.ownerId ||
        conversation.dotId !== receipt.dotId
      )
        throw new ConversationRequestError(
          'Sohbetin sahiplik kapsamı doğrulanamadı.',
          403,
        );
      this.db
        .prepare(
          "UPDATE conversation_requests SET state='completed' WHERE ownerId=? AND requestId=? AND state='accepted'",
        )
        .run(this.ownerId, requestId);
      return conversation;
    });
  }
  private requireBinding(receipt: ConversationRequestReceipt): Conversation {
    const conversation = this.binding(receipt.threadId);
    if (
      !conversation ||
      conversation.ownerId !== this.ownerId ||
      conversation.dotId !== receipt.dotId
    )
      throw new ConversationRequestError(
        'Sohbet bağı ile kabul kaydı eşleşmiyor.',
      );
    return conversation;
  }
  private transaction<T>(operation: () => T): T {
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const result = operation();
      this.db.exec('COMMIT');
      return result;
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }
}
