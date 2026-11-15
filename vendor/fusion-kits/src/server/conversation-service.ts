import { randomUUID } from 'node:crypto';
import type { Conversation } from '../shared/types.js';
import type { WorkspaceStore } from './workspace.js';
import {
  ConversationRequestError,
  type ConversationRequestReceipt,
} from './conversation-request-store.js';
import { boundedIntelligence } from './intelligence-deadline.js';
import {
  verifiedThreadMetadata,
  type ThreadMetadata,
} from './thread-restore.js';

type ThreadInput = {
  threadId: string;
  userId: string;
  agentId: string;
  name: string;
};
export type ConversationAdapter =
  | { kind: 'local'; ensure: (id: string, dotId: string) => void }
  | {
      kind: 'remote';
      create: (input: ThreadInput) => Promise<unknown>;
      read: (input: {
        threadId: string;
        userId: string;
      }) => Promise<ThreadMetadata>;
    };

export class ConversationService {
  private pending = new Map<string, Promise<Conversation>>();
  private closed = false;
  constructor(
    private workspace: WorkspaceStore,
    private adapter: () => ConversationAdapter,
    private ready: () => void,
    private createId: () => string = randomUUID,
  ) {}
  async create(
    dotId: string,
    title: string,
    requestId = this.createId(),
  ): Promise<Conversation> {
    if (this.closed)
      throw new ConversationRequestError('Sohbet servisi kapandı.', 503);
    if (!this.workspace.conversationRequests.lookup(requestId)) this.ready();
    const claim = this.workspace.conversationRequests.claim(
      requestId,
      dotId,
      title,
    );
    if (claim.receipt.state === 'completed')
      return this.workspace.conversationRequests.complete(requestId, title);
    const current = this.pending.get(requestId);
    if (current) return current;
    const task = this.materialize(claim.receipt, title, claim.owner);
    this.pending.set(requestId, task);
    try {
      return await task;
    } finally {
      if (this.pending.get(requestId) === task) this.pending.delete(requestId);
    }
  }
  private async materialize(
    receipt: ConversationRequestReceipt,
    title: string,
    isOwner: boolean,
  ): Promise<Conversation> {
    if (
      this.workspace
        .conversations()
        .some((thread) => thread.id === receipt.threadId)
    )
      return this.workspace.conversationRequests.complete(
        receipt.requestId,
        title,
      );
    const adapter = this.adapter();
    if (adapter.kind === 'local') {
      adapter.ensure(receipt.threadId, receipt.dotId);
      return this.workspace.conversationRequests.complete(
        receipt.requestId,
        title,
      );
    }
    let acknowledged = !isOwner;
    if (isOwner) {
      try {
        await boundedIntelligence(
          adapter.create({
            threadId: receipt.threadId,
            userId: this.workspace.ownerId,
            agentId: receipt.dotId,
            name: title.trim(),
          }),
        );
        acknowledged = true;
      } catch {
        acknowledged = false;
      }
    }
    // Başlangıç cevabı kaybolsa da aynı önceden ayrılmış thread gözlemlenir.
    // accepted tekrarında create hiçbir zaman çağrılmaz.
    try {
      await verifiedThreadMetadata(
        this.workspace,
        receipt.threadId,
        receipt.dotId,
        adapter.read,
      );
    } catch (error) {
      if (error instanceof Error && 'status' in error && error.status === 403)
        throw new ConversationRequestError(error.message, 403);
      throw new ConversationRequestError(
        acknowledged
          ? 'Sohbetin uzak kaydı doğrulanamadı; aynı isteği kontrol et. Yeni sohbet oluşturulmadı.'
          : 'Sohbet oluşturma sonucu belirsiz; aynı isteğin durumunu kontrol et. Oluşturma tekrarlanmadı.',
        503,
      );
    }
    return this.workspace.conversationRequests.complete(
      receipt.requestId,
      title,
    );
  }
  async close(): Promise<void> {
    this.closed = true;
    await Promise.allSettled([...this.pending.values()]);
  }
}
