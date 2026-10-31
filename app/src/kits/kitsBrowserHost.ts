import { redactSecrets } from "../feedback/report";

/** Kits'in "kullanıcının Chrome'unu kullan" (`fusion_browser`) isteğini karşılar (P-063).
 *
 * Kimlik ve kapsam iframe'den gelmez: kaynak bu iframe penceresi, köken Kits adresidir.
 * Her istek önce kullanıcıya sorulur; okuma eylemleri (read/find/text/tabs/scroll) bu host
 * yaşadıkça (Kits iframe'i açıkken) bir kez onaylanır, etkileşim eylemleri
 * (navigate/click/type/key) her seferinde sorulur. Onaylanan komut etkin Fusion oturumunun
 * `chrome.kit_komut` RPC'sine gider; dönen metin sırlardan arındırılıp yalnız iframe'e döner.
 * Chrome eklentisinin native hostu Kit sürecine açılmaz. */
interface MessageHost {
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  removeEventListener(type: "message", listener: (event: MessageEvent) => void): void;
}
interface FrameWindow {
  postMessage(message: unknown, targetOrigin: string): void;
}
export type HostRequest = (name: string, data: Record<string, unknown>) => Promise<Record<string, unknown>>;
/** `interactive` true ise eylem sayfayı değiştirebilir ve her seferinde sorulmalıdır. */
export type ConfirmBrowser = (summary: string, interactive: boolean) => Promise<boolean>;

export const KITS_BROWSER_RPC = "chrome.kit_komut";
/** Kits'e dönen metnin üst sınırı. */
export const BROWSER_TEXT_LIMIT = 20_000;
const REASON_LIMIT = 300;
const VALUE_LIMIT = 16_000;
const READ_ACTIONS = new Set(["read", "find", "text", "tabs", "scroll"]);
const INTERACT_ACTIONS = new Set(["navigate", "click", "type", "key"]);
const SUMMARIES: Record<string, string> = {
  read: "açık sekmeyi okumak",
  find: "sayfada öğe aramak",
  text: "sayfa metnini okumak",
  tabs: "açık sekmeleri listelemek",
  scroll: "sayfayı kaydırmak",
  navigate: "bir adrese gitmek",
  click: "bir öğeye tıklamak",
  type: "bir alana yazmak",
  key: "bir tuşa basmak",
};

export interface BrowserRequestInput {
  action: string;
  ref?: string;
  value?: string;
  url?: string;
  reason?: string;
}

/** İstek yükünü doğrula; geçersizse `null`. Bilinmeyen alanlar taşınmaz. */
export function parseBrowserInput(raw: unknown): BrowserRequestInput | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  const action = data.action;
  if (typeof action !== "string" || !(READ_ACTIONS.has(action) || INTERACT_ACTIONS.has(action))) return null;
  const text = (key: string, limit: number) => {
    const value = data[key];
    if (value === undefined) return undefined;
    return typeof value === "string" && value.length <= limit ? value : null;
  };
  const ref = text("ref", 100);
  const value = text("value", VALUE_LIMIT);
  const url = text("url", 2048);
  const reason = text("reason", REASON_LIMIT);
  if (ref === null || value === null || url === null || reason === null) return null;
  return {
    action,
    ...(ref !== undefined ? { ref } : {}),
    ...(value !== undefined ? { value } : {}),
    ...(url !== undefined ? { url } : {}),
    ...(reason !== undefined ? { reason } : {}),
  };
}

/** Kullanıcıya gösterilen tek cümle: ne yapmak istiyor, hangi hedefte, Kit'in gerekçesi. */
export function describeBrowserRequest(input: BrowserRequestInput): string {
  const target = input.action === "navigate" && input.url ? ` (${input.url.slice(0, 200)})` : "";
  const reason = input.reason?.trim() ? ` Kit'in gerekçesi (Fusion doğrulamaz): ${input.reason.trim()}` : "";
  return `Kits Chrome'unda ${SUMMARIES[input.action] ?? input.action}${target} istiyor.${reason}`;
}

export class KitsBrowserHost {
  private readonly origin: string;
  private busy = false;
  private closed = false;
  private readAllowed = false;
  constructor(
    private readonly host: MessageHost,
    private readonly frame: FrameWindow,
    url: string,
    private readonly request: HostRequest,
    private readonly confirm: ConfirmBrowser,
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
      this.frame.postMessage({ type: "fusion-browser-result", nonce, ...result }, this.origin);
    } catch {
      // iframe kapandıysa yanıt verilecek yer yoktur.
    }
  }
  private receive = (event: MessageEvent) => {
    if (this.closed || event.source !== this.frame || event.origin !== this.origin) return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== "object" || data.type !== "fusion-browser-request") return;
    if (typeof data.nonce !== "string" || !data.nonce || data.nonce.length > 100) return;
    const nonce = data.nonce;
    const input = parseBrowserInput(data.input);
    if (!input) {
      this.reply(nonce, { status: "failed", text: "Tarayıcı isteği geçersiz." });
      return;
    }
    if (this.busy) {
      this.reply(nonce, { status: "busy", text: "Önceki Chrome isteği sürüyor." });
      return;
    }
    this.busy = true;
    void this.run(nonce, input).finally(() => {
      this.busy = false;
    });
  }
  private async run(nonce: string, input: BrowserRequestInput) {
    const interactive = INTERACT_ACTIONS.has(input.action);
    let allowed = !interactive && this.readAllowed;
    if (!allowed) {
      try {
        allowed = await this.confirm(describeBrowserRequest(input), interactive);
      } catch {
        allowed = false;
      }
      if (allowed && !interactive) this.readAllowed = true;
    }
    if (!allowed) {
      this.reply(nonce, { status: "denied", text: "Kullanıcı bu Chrome isteğini reddetti." });
      return;
    }
    try {
      const { reason: _reason, ...command } = input;
      const sonuc = await this.request(KITS_BROWSER_RPC, { ...command });
      const status = typeof sonuc.status === "string" ? sonuc.status : sonuc.ok ? "ok" : "failed";
      // Sayfadaki parola/anahtar benzeri metinler Kits'e (ve onun modeline) gitmez.
      const text = typeof sonuc.text === "string" ? redactSecrets(sonuc.text.slice(0, BROWSER_TEXT_LIMIT)) : "";
      this.reply(nonce, { status, text: text || (typeof sonuc.metin === "string" ? sonuc.metin : "") });
    } catch {
      this.reply(nonce, { status: "unavailable", text: "Fusion oturumu bağlı değil; bir sohbet sekmesi aç." });
    }
  }
}
