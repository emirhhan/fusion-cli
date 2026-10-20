/** Kits'in "proje klasörü seç" isteğini yerel klasör seçiciyle karşılar.
 *
 * Yol iframe'e yalnız kullanıcı pencerede bir klasör SEÇERSE döner; iframe yol
 * öneremez ya da dosya sistemi okuyamaz. Kaynak bu iframe penceresi, köken Kits
 * adresidir (bkz. `localComputerHost.ts`). */
interface MessageHost {
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  removeEventListener(type: "message", listener: (event: MessageEvent) => void): void;
}
interface FrameWindow {
  postMessage(message: unknown, targetOrigin: string): void;
}
export type PickFolder = () => Promise<string | null>;

export class FolderPickHost {
  private readonly origin: string;
  private busy = false;
  private closed = false;
  constructor(
    private readonly host: MessageHost,
    private readonly frame: FrameWindow,
    url: string,
    private readonly pick: PickFolder,
  ) {
    this.origin = new URL(url).origin;
    host.addEventListener("message", this.receive);
  }
  close() {
    this.closed = true;
    this.host.removeEventListener("message", this.receive);
  }
  private reply(nonce: string, path: string | null) {
    if (this.closed) return;
    try {
      this.frame.postMessage({ type: "fusion-folder-result", nonce, path }, this.origin);
    } catch {
      // iframe kapandıysa yanıt verilecek yer yoktur.
    }
  }
  private receive = (event: MessageEvent) => {
    if (this.closed || event.source !== this.frame || event.origin !== this.origin) return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== "object" || data.type !== "fusion-folder-request") return;
    if (typeof data.nonce !== "string" || !data.nonce || data.nonce.length > 100) return;
    const nonce = data.nonce;
    if (this.busy) {
      this.reply(nonce, null);
      return;
    }
    this.busy = true;
    void this.pick()
      .catch(() => null)
      .then((path) => this.reply(nonce, typeof path === "string" && path ? path : null))
      .finally(() => {
        this.busy = false;
      });
  };
}
