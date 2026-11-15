import { redactSecrets } from "../feedback/report";

/** Kits'in "kullanıcının Chrome'unu kullan" (`fusion_browser`) isteğini karşılar (P-063).
 *
 * Kimlik ve kapsam iframe'den gelmez: kaynak bu iframe penceresi, köken Kits adresidir.
 * Her istek önce etkin oturumun `chrome.kit_tarif` RPC'sine gider: kapalı araç
 * (`runtime.disabled_tools`) ya da bağlı olmayan oturum kullanıcıya hiç sorulmadan döner;
 * etkileşim eylemleri için hedef öğenin adı ve riski (gönder/sil/satın al) alınır.
 * Sonra kullanıcıya sorulur: okuma eylemleri Kit ve gruba (sayfa / sekmeler) göre
 * `READ_GRANT_TTL_MS` boyunca bir kez, etkileşim eylemleri (navigate/click/type/key) her
 * seferinde. Onaylanan komut `chrome.kit_komut` RPC'sine gider; dönen metin sırlardan
 * arındırılıp yalnız iframe'e döner. Chrome eklentisinin native hostu Kit sürecine açılmaz.
 *
 * Ölçüldü (31 Ekim, inceleme): onay penceresi "bir öğeye tıklamak" diyor, hangi Kit'in
 * hangi düğmeyi istediğini göstermiyordu; tek okuma onayı bütün Kit'lere süresiz geçiyordu. */
interface MessageHost {
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  removeEventListener(type: "message", listener: (event: MessageEvent) => void): void;
}
interface FrameWindow {
  postMessage(message: unknown, targetOrigin: string): void;
}
export type HostRequest = (name: string, data: Record<string, unknown>) => Promise<Record<string, unknown>>;
/** `interactive` true ise eylem sayfayı değiştirebilir ve her seferinde sorulmalıdır;
 * `risky` true ise hedef gönder/sil/satın al gibi geri alınamaz bir iş yapabilir. */
export type ConfirmBrowser = (summary: string, interactive: boolean, risky?: boolean) => Promise<boolean>;

export const KITS_BROWSER_RPC = "chrome.kit_komut";
export const KITS_BROWSER_DESCRIBE_RPC = "chrome.kit_tarif";
/** Kits'e dönen metnin üst sınırı. */
export const BROWSER_TEXT_LIMIT = 20_000;
/** Okuma izninin ömrü (Kit + grup başına); dolunca yeniden sorulur. */
export const READ_GRANT_TTL_MS = 30 * 60_000;
const REASON_LIMIT = 300;
const VALUE_LIMIT = 16_000;
const KIT_NAME_LIMIT = 60;
const KIT_ID_LIMIT = 100;
/** Onay penceresinde gösterilen yazılacak metnin uzunluğu. */
const VALUE_PREVIEW = 60;
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
const RISK_NOTE = " DİKKAT: bu eylem gönderme, satın alma ya da silme gibi geri alınamayan bir işlem yapabilir.";
// Kontrol karakterleri ve satır sonları penceredeki metni bozmasın.
const CONTROL_CHARS = /[\u0000-\u001f\u007f]+/g;

export interface BrowserRequestInput {
  action: string;
  ref?: string;
  value?: string;
  url?: string;
  reason?: string;
}

/** İsteği yapan Kit (Kits uygulaması bildirir; Kit'in modeli değil). */
export interface KitIdentity {
  id: string;
  name: string;
}

/** Onay penceresine giren ek bilgi: Kit, hedef öğenin adı, riskli mi. */
export interface RequestDetail {
  kit?: KitIdentity | null;
  target?: string;
  risky?: boolean;
}

function clean(value: string, limit: number): string {
  return value.replace(CONTROL_CHARS, " ").trim().slice(0, limit);
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

/** Kit kimliğini doğrula; yoksa ya da bozuksa `null` (istek yine işlenir, pencere "Kits" der). */
export function parseKitIdentity(raw: unknown): KitIdentity | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (typeof data.id !== "string" || typeof data.name !== "string") return null;
  const id = clean(data.id, KIT_ID_LIMIT);
  const name = clean(data.name, KIT_NAME_LIMIT);
  return id && name ? { id, name } : null;
}

function quoted(value: string): string {
  return `«${clean(redactSecrets(value), VALUE_PREVIEW)}»`;
}

function actionPhrase(input: BrowserRequestInput, detail: RequestDetail): string {
  const target = detail.target?.trim() ? quoted(detail.target) : "";
  const ref = input.ref ? ` (${clean(input.ref, 40)})` : "";
  switch (input.action) {
    case "navigate":
      return `bir adrese gitmek${input.url ? ` (${input.url.slice(0, 200)})` : ""}`;
    case "click":
      return target ? `${target} öğesine tıklamak` : `adı okunamayan bir öğeye${ref} tıklamak`;
    case "type": {
      const text = input.value ?? "";
      const preview = clean(redactSecrets(text), VALUE_PREVIEW) + (text.length > VALUE_PREVIEW ? "…" : "");
      return `${target ? `${target} alanına` : `bir alana${ref}`} "${preview}" yazmak`;
    }
    case "key": {
      const key = input.value?.trim() ? clean(input.value, 40) : "Enter";
      return `${target ? `${target} alanında ` : ""}${key} tuşuna basmak`;
    }
    default:
      return SUMMARIES[input.action] ?? input.action;
  }
}

/** Kullanıcıya gösterilen metin: hangi Kit, ne yapmak istiyor, hangi hedefte, riskli mi, gerekçesi. */
export function describeBrowserRequest(input: BrowserRequestInput, detail: RequestDetail = {}): string {
  const who = detail.kit ? `${quoted(detail.kit.name)} Kit'i Chrome'unda` : "Kits Chrome'unda";
  const risk = detail.risky ? RISK_NOTE : "";
  const reason = input.reason?.trim() ? ` Kit'in gerekçesi (Fusion doğrulamaz): ${clean(input.reason, REASON_LIMIT)}` : "";
  return `${who} ${actionPhrase(input, detail)} istiyor.${risk}${reason}`;
}

/** Okuma izninin anahtarı: Kit ve grup (sekme listesi ayrı sorulur; sayfa okuma/arama/kaydırma birlikte). */
export function readGrantKey(action: string, kit: KitIdentity | null): string {
  const group = action === "tabs" ? "sekmeler" : "sayfa";
  return `${kit?.id ?? ""}|${group}`;
}

export class KitsBrowserHost {
  private readonly origin: string;
  private busy = false;
  private closed = false;
  private readonly readGrants = new Map<string, number>();
  constructor(
    private readonly host: MessageHost,
    private readonly frame: FrameWindow,
    url: string,
    private readonly request: HostRequest,
    private readonly confirm: ConfirmBrowser,
    private readonly now: () => number = Date.now,
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
    void this.run(nonce, input, parseKitIdentity(data.kit)).finally(() => {
      this.busy = false;
    });
  }
  private hasGrant(key: string): boolean {
    const until = this.readGrants.get(key);
    if (until === undefined) return false;
    if (until > this.now()) return true;
    this.readGrants.delete(key);
    return false;
  }
  private async run(nonce: string, input: BrowserRequestInput, kit: KitIdentity | null) {
    const interactive = INTERACT_ACTIONS.has(input.action);
    const { reason: _reason, ...command } = input;
    // Önce tarif: kapalı araç ya da bağlı olmayan oturum kullanıcıya sorulmadan döner;
    // etkileşimde hedef öğenin adı ve riski pencereye girer.
    let detail: RequestDetail = { kit };
    try {
      const tarif = await this.request(KITS_BROWSER_DESCRIBE_RPC, { ...command });
      if (tarif.status !== "ok") {
        const status = typeof tarif.status === "string" ? tarif.status : "failed";
        this.reply(nonce, { status, text: typeof tarif.text === "string" ? tarif.text : "" });
        return;
      }
      detail = { kit, target: typeof tarif.hedef === "string" ? tarif.hedef : "", risky: tarif.riskli === true };
    } catch {
      this.reply(nonce, { status: "unavailable", text: "Fusion oturumu bağlı değil; bir sohbet sekmesi aç." });
      return;
    }
    const grant = readGrantKey(input.action, kit);
    let allowed = !interactive && this.hasGrant(grant);
    if (!allowed) {
      try {
        allowed = await this.confirm(describeBrowserRequest(input, detail), interactive, detail.risky === true);
      } catch {
        allowed = false;
      }
      if (allowed && !interactive) this.readGrants.set(grant, this.now() + READ_GRANT_TTL_MS);
    }
    if (!allowed) {
      this.reply(nonce, { status: "denied", text: "Kullanıcı bu Chrome isteğini reddetti." });
      return;
    }
    try {
      const sonuc = await this.request(KITS_BROWSER_RPC, { ...command });
      const status = typeof sonuc.status === "string" ? sonuc.status : sonuc.ok ? "ok" : "failed";
      // Sayfadaki parola/anahtar benzeri metinler Kits'e (ve onun modeline) gitmez.
      // Önce gizle, sonra kes: sınırda yarım kalan anahtar desene uymaz ve sızardı.
      const text = typeof sonuc.text === "string" ? redactSecrets(sonuc.text).slice(0, BROWSER_TEXT_LIMIT) : "";
      this.reply(nonce, { status, text: text || (typeof sonuc.metin === "string" ? sonuc.metin : "") });
    } catch {
      this.reply(nonce, { status: "unavailable", text: "Fusion oturumu bağlı değil; bir sohbet sekmesi aç." });
    }
  }
}
