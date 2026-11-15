import { parentOrigins } from '../scheduled-delivery-bridge';
import type { ListenHandlers, VoiceEngine } from './engine';

/** Kits ↔ Fusion ses köprüsü (Fusion tarafı: `app/src/kits/kitsVoiceHost.ts`).
 * İstek ve yanıt yalnız izinli ebeveyn kökeninden, aynı pencereden ve aynı
 * nonce ile eşleşir. Ses ve tanınan metin Mac'ten dışarı çıkmaz. */
export const VOICE_REQUEST = 'fusion-kits-voice';
export const VOICE_RESULT = 'fusion-kits-voice-result';
export const VOICE_EVENT = 'fusion-kits-voice-event';
type Action = 'hello' | 'listen' | 'stop-listening' | 'speak' | 'stop-speaking';
type Api = <T>(path: string, method?: string, body?: unknown) => Promise<T>;
export interface BridgeView {
  parent: Window;
  self: Window;
  addEventListener(
    type: 'message',
    listener: (event: MessageEvent) => void,
  ): void;
  removeEventListener(
    type: 'message',
    listener: (event: MessageEvent) => void,
  ): void;
}
const HELLO_TIMEOUT_MS = 1_500;
const REQUEST_TIMEOUT_MS = 15_000;
/** Seslendirme cevabın uzunluğu kadar sürer. */
const SPEAK_TIMEOUT_MS = 180_000;

export class FusionVoiceEngine implements VoiceEngine {
  readonly kind = 'fusion' as const;
  private handlers?: ListenHandlers;
  private pending = new Map<
    string,
    { resolve: (ok: boolean) => void; reject: (error: Error) => void }
  >();
  private constructor(
    private view: BridgeView,
    private origins: string[],
    private nonce: () => string,
  ) {
    view.addEventListener('message', this.receive);
  }

  /** Fusion içinde değilse ya da Fusion ses köprüsünü bilmiyorsa `null`. */
  static async connect(
    view: BridgeView,
    api: Api,
    options: { nonce?: () => string; timeoutMs?: number } = {},
  ): Promise<FusionVoiceEngine | null> {
    if (view.parent === view.self) return null;
    let origins: string[];
    try {
      origins = await parentOrigins(api);
    } catch {
      return null;
    }
    if (!origins.length) return null;
    const engine = new FusionVoiceEngine(
      view,
      origins,
      options.nonce ?? (() => crypto.randomUUID()),
    );
    try {
      await engine.request(
        'hello',
        undefined,
        options.timeoutMs ?? HELLO_TIMEOUT_MS,
      );
      return engine;
    } catch {
      engine.close();
      return null;
    }
  }

  private receive = (event: MessageEvent) => {
    if (
      event.source !== this.view.parent ||
      !this.origins.includes(event.origin)
    )
      return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== 'object') return;
    if (data.type === VOICE_RESULT && typeof data.nonce === 'string') {
      const waiter = this.pending.get(data.nonce);
      if (!waiter) return;
      this.pending.delete(data.nonce);
      if (data.ok === true) waiter.resolve(true);
      else
        waiter.reject(
          new Error(
            typeof data.error === 'string' && data.error
              ? data.error
              : 'Fusion ses isteğini tamamlayamadı.',
          ),
        );
      return;
    }
    if (data.type !== VOICE_EVENT || !this.handlers) return;
    const text = typeof data.text === 'string' ? data.text.slice(0, 4000) : '';
    if (data.event === 'partial' && text) this.handlers.onPartial(text);
    if (data.event === 'final' && text) this.handlers.onFinal(text);
    if (data.event === 'error')
      this.handlers.onError(text || 'Fusion konuşmayı tanıyamadı.');
  };

  private request(
    action: Action,
    text?: string,
    timeoutMs = REQUEST_TIMEOUT_MS,
  ) {
    const nonce = this.nonce();
    return new Promise<boolean>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(nonce);
        reject(new Error('Fusion ses isteği süre içinde yanıt vermedi.'));
      }, timeoutMs);
      this.pending.set(nonce, {
        resolve: (ok) => {
          clearTimeout(timer);
          resolve(ok);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
      });
      for (const origin of this.origins)
        this.view.parent.postMessage(
          { type: VOICE_REQUEST, nonce, action, ...(text ? { text } : {}) },
          origin,
        );
    });
  }

  async listen(handlers: ListenHandlers) {
    this.handlers = handlers;
    await this.request('listen');
  }
  async stopListening() {
    this.handlers = undefined;
    await this.request('stop-listening').catch(() => false);
  }
  async speak(text: string) {
    await this.request('speak', text, SPEAK_TIMEOUT_MS);
  }
  async stopSpeaking() {
    await this.request('stop-speaking').catch(() => false);
  }
  close() {
    this.handlers = undefined;
    this.view.removeEventListener('message', this.receive);
    for (const waiter of this.pending.values())
      waiter.reject(new Error('Ses bağlantısı kapandı.'));
    this.pending.clear();
  }
}
