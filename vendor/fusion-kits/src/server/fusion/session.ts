import type { FusionTransport } from './transport.js';
import { ComputeBudget } from './budget.js';

type Payload = Record<string, unknown>;
const object = (value: unknown): value is Payload =>
  !!value && typeof value === 'object' && !Array.isArray(value);
export class FusionSession {
  private counter = 0;
  private closed = false;
  private pending = new Map<
    string,
    {
      resolve: (value: Payload) => void;
      reject: (error: Error) => void;
      budget: ComputeBudget;
      name: string;
    }
  >();
  private events = new Set<(data: Payload) => void>();
  private questions = new Set<(id: string, data: Payload) => void>();
  private questionIds = new Set<string>();
  private unsubscribers: (() => void)[];
  constructor(
    private transport: FusionTransport,
    private timeoutMs: number,
  ) {
    this.unsubscribers = [
      transport.subscribe((line) => this.receive(line)),
      transport.onFailure((error) => this.fail(error)),
    ];
  }
  request(name: string, data: Payload): Promise<Payload> {
    if (this.closed)
      return Promise.reject(new Error('Fusion bağlantısı kapandı.'));
    const id = String(++this.counter);
    return new Promise((resolve, reject) => {
      const budget = new ComputeBudget(this.timeoutMs, () => {
        this.pending.delete(id);
        reject(new Error('Fusion isteği süre sınırını aştı.'));
        this.fail(
          new Error('Fusion protokol oturumu süre aşımı nedeniyle kapandı.'),
        );
      });
      this.pending.set(id, { resolve, reject, budget, name });
      if (name === 'tur.calistir' && this.questionIds.size) budget.pause();
      try {
        this.transport.send(
          JSON.stringify({ tip: 'istek', id, ad: name, veri: data }),
        );
      } catch (error) {
        this.fail(
          error instanceof Error ? error : new Error('Fusion gönderme hatası.'),
        );
      }
    });
  }
  reply(id: string, data: Payload) {
    if (this.closed || !this.questionIds.has(id))
      throw new Error('Fusion sorusu artık beklemiyor.');
    this.transport.send(JSON.stringify({ tip: 'cevap', id, veri: data }));
    this.questionIds.delete(id);
    if (!this.questionIds.size)
      for (const entry of this.pending.values()) entry.budget.resume();
  }
  onEvent(listener: (data: Payload) => void) {
    this.events.add(listener);
    return () => this.events.delete(listener);
  }
  onQuestion(listener: (id: string, data: Payload) => void) {
    this.questions.add(listener);
    return () => this.questions.delete(listener);
  }
  private receive(line: string) {
    if (this.closed) return;
    let message: unknown;
    try {
      message = JSON.parse(line);
    } catch {
      this.fail(new Error('Fusion protokol JSON hatası.'));
      return;
    }
    if (
      !object(message) ||
      !object(message.veri) ||
      !['olay', 'sonuc', 'soru'].includes(String(message.tip)) ||
      (message.tip !== 'olay' &&
        (typeof message.id !== 'string' || !message.id))
    ) {
      this.fail(new Error('Fusion protokol zarfı geçersiz.'));
      return;
    }
    if (message.tip === 'olay')
      this.events.forEach((listener) => listener(message.veri as Payload));
    if (message.tip === 'soru') {
      this.questionIds.add(message.id as string);
      for (const entry of this.pending.values())
        if (entry.name === 'tur.calistir') entry.budget.pause();
      this.questions.forEach((listener) =>
        listener(message.id as string, message.veri as Payload),
      );
    }
    if (message.tip === 'sonuc') {
      const entry = this.pending.get(message.id as string);
      if (!entry) return;
      entry.budget.close();
      this.pending.delete(message.id as string);
      entry.resolve(message.veri);
    }
  }
  private fail(error: Error) {
    this.closed = true;
    for (const entry of this.pending.values()) {
      entry.budget.close();
      entry.reject(error);
    }
    this.pending.clear();
    this.questionIds.clear();
  }
  async close() {
    this.fail(new Error('Fusion bağlantısı kapandı.'));
    this.unsubscribers.forEach((unsubscribe) => unsubscribe());
    this.events.clear();
    this.questions.clear();
    await this.transport.close();
  }
}
