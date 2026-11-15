import { ComputeBudget } from './fusion/budget.js';
import { Store } from './store.js';
import type { Result, Memory } from '../shared/types.js';
import type { Claim } from './store.js';
import { research, type Config } from './research.js';
export class Runner {
  private timer?: ReturnType<typeof setInterval>;
  private active = new Map<string, AbortController>();
  constructor(
    private store: Store,
    private config: Config,
    private execute?: (
      claim: Claim,
      memories: Memory[],
      signal: AbortSignal,
      progress: (text: string) => void,
    ) => Promise<Result>,
    private waiting?: (claim: Claim) => boolean,
  ) {}
  start() {
    if (!this.timer) {
      this.timer = setInterval(() => void this.tick(), 1000);
      void this.tick();
    }
  }
  stop() {
    clearInterval(this.timer);
    this.timer = undefined;
    for (const task of this.store.tasks()) {
      if (this.active.has(task.id) && task.lease)
        this.store.release(
          { ...task, lease: task.lease },
          'Sunucu duruyor; yeniden başlatma için sıraya alındı.',
        );
    }
    this.abortAll();
  }
  abort(id: string) {
    this.active.get(id)?.abort(new Error('Çalıştırma durduruldu.'));
  }
  abortAll() {
    for (const controller of this.active.values())
      controller.abort(
        new Error('Ayarlar değiştiği için çalıştırma durduruldu.'),
      );
  }
  async tick() {
    if (this.active.size) return;
    const claim = this.store.claim();
    if (!claim) return;
    const controller = new AbortController();
    this.active.set(claim.id, controller);
    let lastHeartbeat = Date.now();
    const ownershipCheck = setInterval(() => {
      if (this.waiting?.(claim)) timeout.pause();
      else timeout.resume();
      if (Date.now() - lastHeartbeat >= 30_000) {
        this.store.heartbeat(claim);
        lastHeartbeat = Date.now();
      }
      if (!this.store.owns(claim))
        controller.abort(
          new Error('Çalıştırma izni veya kirası iptal edildi.'),
        );
    }, 100);
    const timeout = new ComputeBudget(90_000, () =>
      controller.abort(new Error('Araştırma 90 saniyelik süre sınırını aştı.')),
    );
    try {
      const settings = this.store.settings();
      const memories = settings.memoryAllowed ? this.store.memories() : [];
      const progress = (text: string) => {
        if (!this.store.owns(claim))
          controller.abort(
            new Error('Çalıştırma izni veya kirası iptal edildi.'),
          );
        controller.signal.throwIfAborted();
        this.store.event(claim.id, claim.lease, text);
      };
      const result = this.execute
        ? await this.execute(claim, memories, controller.signal, progress)
        : await research(
            claim.prompt,
            memories,
            this.config,
            controller.signal,
            progress,
          );
      controller.signal.throwIfAborted();
      this.store.finish(claim, result);
    } catch (error) {
      this.store.fail(
        claim,
        error instanceof Error
          ? error.message
          : 'Beklenmeyen araştırma hatası.',
      );
    } finally {
      clearInterval(ownershipCheck);
      timeout.close();
      this.active.delete(claim.id);
    }
  }
}
