import { runtimeDefault, type DictationRuntime } from "../voice/useDictation";
import type { HostRequest } from "./localComputerHost";

/** Kits'in sesli konuşmasına Fusion'ın yerel sesini verir (Kits tarafı:
 * `fusion-kits/src/client/local-voice/fusion-bridge.ts`).
 *
 * Tanıma cihaz içi `fusion-listen` yardımcısıyla, seslendirme oturumun
 * `ses.konus` RPC'siyle (macOS `say`/Piper) yapılır: anahtar istemez, ses ve
 * metin Mac'ten çıkmaz. İstek yalnız bu iframe penceresinden ve Kits kökeninden
 * kabul edilir; Kits yalnız dinle/dur/seslendir isteyebilir. */
export const VOICE_REQUEST = "fusion-kits-voice";
export const VOICE_RESULT = "fusion-kits-voice-result";
export const VOICE_EVENT = "fusion-kits-voice-event";
const ACTIONS = ["hello", "listen", "stop-listening", "speak", "stop-speaking"] as const;
type Action = (typeof ACTIONS)[number];
/** Tek seferde seslendirilecek metnin üst sınırı (Kits cümle cümle gönderir). */
export const SPEAK_TEXT_LIMIT = 2_000;

interface MessageHost {
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  removeEventListener(type: "message", listener: (event: MessageEvent) => void): void;
}
interface FrameWindow {
  postMessage(message: unknown, targetOrigin: string): void;
}
interface HelperLine { tur?: string; metin?: string }

export class KitsVoiceHost {
  private readonly origin: string;
  private closed = false;
  private session: number | null = null;
  private unlisten: (() => void)[] = [];
  private speechTurn: string | null = null;
  constructor(
    private readonly host: MessageHost,
    private readonly frame: FrameWindow,
    url: string,
    private readonly request: HostRequest,
    private readonly runtime: DictationRuntime = runtimeDefault,
  ) {
    this.origin = new URL(url).origin;
    host.addEventListener("message", this.receive);
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this.host.removeEventListener("message", this.receive);
    void this.stopListening();
    void this.stopSpeaking();
  }

  private post(message: Record<string, unknown>) {
    if (this.closed) return;
    try {
      this.frame.postMessage(message, this.origin);
    } catch {
      // iframe kapandıysa yanıt verilecek yer yoktur.
    }
  }

  private receive = (event: MessageEvent) => {
    if (this.closed || event.source !== this.frame || event.origin !== this.origin) return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== "object" || data.type !== VOICE_REQUEST) return;
    if (typeof data.nonce !== "string" || !data.nonce || data.nonce.length > 100) return;
    if (!ACTIONS.includes(data.action as Action)) return;
    const nonce = data.nonce;
    const text = typeof data.text === "string" ? data.text.slice(0, SPEAK_TEXT_LIMIT) : "";
    void this.handle(data.action as Action, text).then(
      () => this.post({ type: VOICE_RESULT, nonce, ok: true }),
      (error: unknown) =>
        this.post({
          type: VOICE_RESULT,
          nonce,
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        }),
    );
  };

  private async handle(action: Action, text: string) {
    if (action === "hello") return;
    if (action === "listen") return this.startListening();
    if (action === "stop-listening") return this.stopListening();
    if (action === "speak") return this.speak(text);
    return this.stopSpeaking();
  }

  private async startListening() {
    await this.stopListening();
    const removeLine = await this.runtime.onLine((payload) => {
      if (payload.session !== this.session) return;
      let line: HelperLine;
      try { line = JSON.parse(payload.line) as HelperLine; } catch { return; }
      const words = line.metin?.trim();
      if (!words) return;
      if (line.tur === "kismi") this.post({ type: VOICE_EVENT, event: "partial", text: words });
      if (line.tur === "son") this.post({ type: VOICE_EVENT, event: "final", text: words });
    });
    const removeEnded = await this.runtime.onEnded((payload) => {
      if (payload.session !== this.session) return;
      this.session = null;
      this.post({
        type: VOICE_EVENT,
        event: "error",
        text: payload.stderr_summary?.message || "Konuşma tanıma durdu. Mikrofon ve konuşma izinlerini kontrol et.",
      });
    });
    this.unlisten = [removeLine, removeEnded];
    try {
      this.session = await this.runtime.start();
    } catch {
      await this.stopListening();
      throw new Error("Konuşma tanıma başlatılamadı. Sistem Ayarları'nda mikrofon ve konuşma tanıma iznini ver.");
    }
  }

  private async stopListening() {
    const wasListening = this.session !== null || this.unlisten.length > 0;
    this.unlisten.forEach((remove) => remove());
    this.unlisten = [];
    this.session = null;
    if (wasListening) await this.runtime.stop().catch(() => undefined);
  }

  private async speak(text: string) {
    if (!text.trim()) return;
    const started = await this.request("ses.konus", { metin: text });
    const turn = typeof started.tur_id === "string" ? started.tur_id : null;
    if (started.ok !== true || !turn) {
      throw new Error(typeof started.metin === "string" ? started.metin : "Fusion sesli yanıtı başlatamadı.");
    }
    this.speechTurn = turn;
    try {
      await this.request("ses.bekle", { tur_id: turn });
    } finally {
      if (this.speechTurn === turn) this.speechTurn = null;
    }
  }

  private async stopSpeaking() {
    const turn = this.speechTurn;
    this.speechTurn = null;
    if (turn) await this.request("ses.durdur", { tur_id: turn }).catch(() => undefined);
  }
}
