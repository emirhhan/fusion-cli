/** Kits'in "bilgisayarıma bak" isteğini karşılar: her istekte kullanıcıya sorar, izin
 * verilirse Fusion oturumundan salt okunur gözlem alıp yalnız Kits iframe'ine döner.
 *
 * Kimlik ve kapsam iframe'den gelmez: kaynak bu iframe penceresi, köken Kits adresidir,
 * gözlem oturumun kendi kök/konuşma bağıyla alınır (bkz. `local_computer_routes.py`). */
interface MessageHost {
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  removeEventListener(type: "message", listener: (event: MessageEvent) => void): void;
}
interface FrameWindow {
  postMessage(message: unknown, targetOrigin: string): void;
}
export type HostRequest = (name: string, data: Record<string, unknown>) => Promise<Record<string, unknown>>;
export type ConfirmComputer = (reason: string) => Promise<boolean>;

/** Kits'e dönen metnin üst sınırı (erişilebilirlik ağacı uzun olabilir). */
export const COMPUTER_TEXT_LIMIT = 8_000;
const REASON_LIMIT = 300;

export class LocalComputerHost {
  private readonly origin: string;
  private busy = false;
  private closed = false;
  constructor(
    private readonly host: MessageHost,
    private readonly frame: FrameWindow,
    url: string,
    private readonly request: HostRequest,
    private readonly confirm: ConfirmComputer,
  ) {
    this.origin = new URL(url).origin;
    host.addEventListener("message", this.receive);
  }
  close() {
    this.closed = true;
    this.host.removeEventListener("message", this.receive);
  }
  private reply(nonce: string, result: Record<string, unknown>) {
    if (this.closed) return;
    try {
      this.frame.postMessage({ type: "fusion-computer-result", nonce, ...result }, this.origin);
    } catch {
      // iframe kapandıysa yanıt verilecek yer yoktur.
    }
  }
  private receive = (event: MessageEvent) => {
    if (this.closed || event.source !== this.frame || event.origin !== this.origin) return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== "object" || data.type !== "fusion-computer-request") return;
    if (typeof data.nonce !== "string" || !data.nonce || data.nonce.length > 100) return;
    const nonce = data.nonce;
    if (this.busy) {
      this.reply(nonce, { status: "busy" });
      return;
    }
    const reason = typeof data.reason === "string" ? data.reason.slice(0, REASON_LIMIT) : "";
    this.busy = true;
    void this.observe(nonce, reason).finally(() => {
      this.busy = false;
    });
  };
  private async observe(nonce: string, reason: string) {
    let allowed = false;
    try {
      allowed = await this.confirm(reason);
    } catch {
      allowed = false;
    }
    if (!allowed) {
      this.reply(nonce, { status: "denied" });
      return;
    }
    try {
      const sonuc = await this.request("bilgisayar.snapshot", {});
      const text = typeof sonuc.text === "string" ? sonuc.text.slice(0, COMPUTER_TEXT_LIMIT) : "";
      this.reply(nonce, {
        status: typeof sonuc.status === "string" ? sonuc.status : "unavailable",
        snapshotId: typeof sonuc.snapshot_id === "string" ? sonuc.snapshot_id : null,
        text: text || (typeof sonuc.metin === "string" ? sonuc.metin : ""),
      });
    } catch {
      this.reply(nonce, { status: "unavailable", text: "Fusion oturumu bağlı değil." });
    }
  }
}
