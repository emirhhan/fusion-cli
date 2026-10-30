import type { DictationRuntime } from "../voice/useDictation";
import type { HostRequest } from "./localComputerHost";

/** Kits'in sesli konuşmasına Fusion'ın yerel sesini verir (Kits tarafı:
 * `fusion-kits/src/client/local-voice/fusion-bridge.ts`).
 *
 * Tanıma cihaz içi `fusion-listen` yardımcısıyla, seslendirme oturumun
 * `ses.konus` RPC'siyle (macOS `say`/EMA) yapılır: anahtar istemez, ses ve
 * metin Mac'ten çıkmaz. İstek yalnız bu iframe penceresinden ve Kits kökeninden
 * kabul edilir; Kits yalnız dinle/dur/seslendir isteyebilir. Mikrofon ilk
 * `listen`de Fusion'ın kendi penceresiyle sorulur; izin pencere ömrü boyunca
 * hatırlanır (U6-15). */
export const VOICE_REQUEST = "fusion-kits-voice";
export const VOICE_RESULT = "fusion-kits-voice-result";
export const VOICE_EVENT = "fusion-kits-voice-event";
const ACTIONS = ["hello", "listen", "stop-listening", "speak", "stop-speaking"] as const;
type Action = (typeof ACTIONS)[number];
/** Tek seferde seslendirilecek metnin üst sınırı (Kits cümle cümle gönderir). */
export const SPEAK_TEXT_LIMIT = 2_000;
/** `ses.bekle` yanıtı için üst sınır: çekirdek yanıt vermezse Kits "konuşuyor"da takılı kalmasın. */
export const SPEAK_WAIT_LIMIT_MS = 180_000;

/** Kits ilk kez mikrofon istediğinde kullanıcıya sorar (U6-15). */
export type ConfirmMicrophone = () => Promise<boolean>;
/** Reddedilen izin bu süre boyunca yeniden sorulmaz: Kits'in yeniden deneme döngüsü pencere yağdırmasın. */
export const MICROPHONE_DENY_MEMORY_MS = 30_000;

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
  /** Aynı anda süren seslendirme turları (art arda `speak` biri ötekini sahipsiz bırakmasın). */
  private readonly speechTurns = new Set<string>();
  /** Dinleme başlat/durdur işlemleri sırayla çalışır; eşzamanlı iki `listen` oturum sızdırmasın. */
  private listenQueue: Promise<void> = Promise.resolve();
  /** Kullanıcı bu pencere ömrü boyunca mikrofona izin verdiyse true ("bu oturumda hatırla"). */
  private microphoneGranted = false;
  private microphoneDeniedAt = 0;
  constructor(
    private readonly host: MessageHost,
    private readonly frame: FrameWindow,
    url: string,
    private readonly request: HostRequest,
    private readonly runtime: DictationRuntime,
    private readonly confirmMicrophone: ConfirmMicrophone,
  ) {
    this.origin = new URL(url).origin;
    host.addEventListener("message", this.receive);
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this.host.removeEventListener("message", this.receive);
    this.reset();
  }

  /** iframe yeniden yüklenince önceki sayfanın dinleme/seslendirme işleri sahipsiz kalmasın. */
  reset() {
    void this.enqueueListen(() => this.stopListening()).catch(() => undefined);
    void this.stopSpeaking().catch(() => undefined);
  }

  private enqueueListen(task: () => Promise<void>): Promise<void> {
    const run = this.listenQueue.then(task);
    this.listenQueue = run.catch(() => undefined);
    return run;
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
    if (action === "listen") {
      return this.enqueueListen(async () => {
        await this.requireMicrophone();
        await this.startListening();
      });
    }
    if (action === "stop-listening") return this.enqueueListen(() => this.stopListening());
    if (action === "speak") return this.speak(text);
    return this.stopSpeaking();
  }

  /** Mikrofon, Kits iframe'i (üçüncü taraf içerik) için ilk kullanımda Fusion içi onayla açılır. */
  private async requireMicrophone() {
    if (this.microphoneGranted) return;
    const denied = new Error("Mikrofon izni verilmedi. Kits'in sesli konuşması için Fusion'ın sorusunda İzin ver'i seç.");
    if (this.microphoneDeniedAt && Date.now() - this.microphoneDeniedAt < MICROPHONE_DENY_MEMORY_MS) throw denied;
    let allowed = false;
    try { allowed = await this.confirmMicrophone(); } catch { allowed = false; }
    if (!allowed) {
      this.microphoneDeniedAt = Date.now();
      throw denied;
    }
    this.microphoneGranted = true;
    this.microphoneDeniedAt = 0;
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
    this.speechTurns.add(turn);
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error("Seslendirme zaman aşımına uğradı.")), SPEAK_WAIT_LIMIT_MS);
    });
    try {
      await Promise.race([this.request("ses.bekle", { tur_id: turn }), timeout]);
    } catch (error) {
      if (this.speechTurns.has(turn)) await this.request("ses.durdur", { tur_id: turn }).catch(() => undefined);
      throw error;
    } finally {
      clearTimeout(timer);
      this.speechTurns.delete(turn);
    }
  }

  private async stopSpeaking() {
    const turns = [...this.speechTurns];
    this.speechTurns.clear();
    await Promise.all(turns.map((turn) => this.request("ses.durdur", { tur_id: turn }).catch(() => undefined)));
  }
}
