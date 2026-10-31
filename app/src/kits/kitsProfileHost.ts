import { redactSecrets } from "../feedback/report";

/** Kits'in "Fusion tarayıcı profilini Kit tarayıcısına yükle" (`fusion_profile`) isteği (P-023).
 *
 * Kit'in Node/Playwright tarayıcısı şifreli profili okuyamaz; anahtar Fusion'dadır. Akış
 * Chrome köprüsüyle (`kitsBrowserHost.ts`) aynı güven modelidir: istek yalnız bu iframe
 * penceresinden ve Kits kökeninden kabul edilir; önce `tarayici.profil_tarif` kapıları ve
 * kapsamı çıkarır (kapalı araç, profil yok, onay dışı alan adı kullanıcıya sorulmadan döner);
 * sonra kullanıcıya HER istekte Kit adı, profil ve alan adlarıyla sorulur (hatırlanan izin
 * yok); onaylanırsa `tarayici.profil_disa_aktar`'ın `storage_state`'i yalnız bu iframe'e
 * bellek içi gönderilir. Kits sunucusu onu kalıcı olmayan bir bağlama verir, diske yazmaz;
 * Kit'in modeli yalnız özet metni görür. Bu sınıf hiçbir şey loglamaz. */
interface MessageHost {
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  removeEventListener(type: "message", listener: (event: MessageEvent) => void): void;
}
interface FrameWindow {
  postMessage(message: unknown, targetOrigin: string): void;
}
export type HostRequest = (name: string, data: Record<string, unknown>) => Promise<Record<string, unknown>>;
export type ConfirmProfile = (summary: string) => Promise<boolean>;

export const KITS_PROFILE_DESCRIBE_RPC = "tarayici.profil_tarif";
export const KITS_PROFILE_EXPORT_RPC = "tarayici.profil_disa_aktar";
export const MAX_PROFILE_DOMAINS = 20;
const PROFILE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;
const DOMAIN_LIMIT = 253;
const REASON_LIMIT = 300;
const KIT_NAME_LIMIT = 60;
const KIT_ID_LIMIT = 100;
const LIST_LIMIT = 8;
// Kontrol karakterleri ve satır sonları penceredeki metni bozmasın.
const CONTROL_CHARS = /[\u0000-\u001f\u007f]+/g;
const HAS_CONTROL = /[\u0000-\u001f\u007f]/;
const STATUSES = new Set(["ok", "denied", "busy", "failed", "unavailable"]);
const UNAVAILABLE = "Fusion oturumu bağlı değil; bir sohbet sekmesi aç.";

export interface ProfileRequestInput {
  profile: string;
  domains: string[];
  reason?: string;
}
export interface KitIdentity {
  id: string;
  name: string;
}

function clean(value: string, limit: number): string {
  return value.replace(CONTROL_CHARS, " ").trim().slice(0, limit);
}

/** İstek yükünü doğrula; geçersizse `null`. Bilinmeyen alanlar taşınmaz. */
export function parseProfileInput(raw: unknown): ProfileRequestInput | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (typeof data.profile !== "string" || !PROFILE_PATTERN.test(data.profile)) return null;
  if (!Array.isArray(data.domains) || data.domains.length === 0 || data.domains.length > MAX_PROFILE_DOMAINS) return null;
  const domains: string[] = [];
  for (const item of data.domains) {
    if (typeof item !== "string" || !item.trim() || item.length > DOMAIN_LIMIT || HAS_CONTROL.test(item)) return null;
    domains.push(item.trim().toLowerCase());
  }
  if (data.reason !== undefined && (typeof data.reason !== "string" || data.reason.length > REASON_LIMIT)) return null;
  return { profile: data.profile, domains, ...(typeof data.reason === "string" ? { reason: data.reason } : {}) };
}

export function parseKitIdentity(raw: unknown): KitIdentity | null {
  if (!raw || typeof raw !== "object") return null;
  const data = raw as Record<string, unknown>;
  if (typeof data.id !== "string" || typeof data.name !== "string") return null;
  const id = clean(data.id, KIT_ID_LIMIT);
  const name = clean(data.name, KIT_NAME_LIMIT);
  return id && name ? { id, name } : null;
}

function list(values: string[]): string {
  const shown = values.slice(0, LIST_LIMIT).map((item) => clean(item, 80)).join(", ");
  return values.length > LIST_LIMIT ? `${shown} +${values.length - LIST_LIMIT}` : shown;
}

/** Onay penceresinin metni: hangi Kit, hangi profil, hangi siteler, ne olacağı, Kit'in gerekçesi. */
export function describeProfileRequest(
  input: ProfileRequestInput,
  scope: { domains: string[]; profileDomains: string[] },
  kit: KitIdentity | null,
): string {
  const who = kit ? `«${clean(redactSecrets(kit.name), KIT_NAME_LIMIT)}» Kit'i` : "Kits";
  const reason = input.reason?.trim() ? ` Kit'in gerekçesi (Fusion doğrulamaz): ${clean(redactSecrets(input.reason), REASON_LIMIT)}` : "";
  return (
    `${who}, Fusion'daki «${clean(input.profile, 64)}» tarayıcı profilinin şu sitelerdeki oturumunu kendi tarayıcısına yüklemek istiyor: ${list(scope.domains)}` +
    ` (profilde: ${list(scope.profileDomains)}). Kit bu sitelerde senin adına girişli gezinebilir ve işlem yapabilir.${reason}`
  );
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export class KitsProfileHost {
  private readonly origin: string;
  private busy = false;
  private closed = false;
  constructor(
    private readonly host: MessageHost,
    private readonly frame: FrameWindow,
    url: string,
    private readonly request: HostRequest,
    private readonly confirm: ConfirmProfile,
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
      this.frame.postMessage({ type: "fusion-profile-result", nonce, ...result }, this.origin);
    } catch {
      // iframe kapandıysa yanıt verilecek yer yoktur.
    }
  }
  private receive = (event: MessageEvent) => {
    if (this.closed || event.source !== this.frame || event.origin !== this.origin) return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== "object" || data.type !== "fusion-profile-request") return;
    if (typeof data.nonce !== "string" || !data.nonce || data.nonce.length > 100) return;
    const nonce = data.nonce;
    const input = parseProfileInput(data.input);
    if (!input) {
      this.reply(nonce, { status: "failed", text: "Profil isteği geçersiz: profil adı ve 1-20 alan adı gerekli." });
      return;
    }
    if (this.busy) {
      this.reply(nonce, { status: "busy", text: "Önceki profil isteği sürüyor." });
      return;
    }
    this.busy = true;
    void this.run(nonce, input, parseKitIdentity(data.kit)).finally(() => {
      this.busy = false;
    });
  };
  private async run(nonce: string, input: ProfileRequestInput, kit: KitIdentity | null) {
    const query = { ad: input.profile, alanlar: input.domains };
    let tarif: Record<string, unknown>;
    try {
      tarif = await this.request(KITS_PROFILE_DESCRIBE_RPC, query);
    } catch {
      this.reply(nonce, { status: "unavailable", text: UNAVAILABLE });
      return;
    }
    if (tarif.status !== "ok") {
      const status = typeof tarif.status === "string" && STATUSES.has(tarif.status) ? tarif.status : "failed";
      this.reply(nonce, { status, text: typeof tarif.text === "string" ? tarif.text : "" });
      return;
    }
    const scope = { domains: strings(tarif.alan_adlari), profileDomains: strings(tarif.profil_alanlari) };
    let allowed = false;
    try {
      allowed = await this.confirm(describeProfileRequest(input, scope, kit));
    } catch {
      allowed = false;
    }
    if (!allowed) {
      this.reply(nonce, { status: "denied", text: "Kullanıcı profil isteğini reddetti." });
      return;
    }
    let sonuc: Record<string, unknown>;
    try {
      sonuc = await this.request(KITS_PROFILE_EXPORT_RPC, query);
    } catch {
      this.reply(nonce, { status: "unavailable", text: UNAVAILABLE });
      return;
    }
    const state = sonuc.storage_state;
    if (sonuc.status !== "ok" || !state || typeof state !== "object") {
      const status = typeof sonuc.status === "string" && STATUSES.has(sonuc.status) ? sonuc.status : "failed";
      this.reply(nonce, { status, text: typeof sonuc.text === "string" ? sonuc.text : "Profil verilemedi." });
      return;
    }
    const count = typeof sonuc.cerez_sayisi === "number" ? sonuc.cerez_sayisi : 0;
    this.reply(nonce, {
      status: "ok",
      text: `«${input.profile}» profili: ${count} çerez, alan adları: ${list(scope.domains)}.`,
      profile: input.profile,
      domains: scope.domains,
      state,
    });
  }
}
