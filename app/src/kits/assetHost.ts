/** Kits yalnız bir asset kimliği çözebilir; iframe dosya yolu öneremez. */
interface MessageHost {
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
  removeEventListener(type: "message", listener: (event: MessageEvent) => void): void;
}
interface FrameWindow { postMessage(message: unknown, targetOrigin: string): void }
type Request = (name: string, data: Record<string, unknown>) => Promise<Record<string, unknown>>;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const fields = ["asset_id", "metadata_version", "kind", "mime", "relative_path", "created_at", "created_by_task_id", "parent_asset_ids", "width", "height", "alpha", "model", "seed", "available"];
function reference(raw: unknown): Record<string, unknown> | null {
  if (!raw || typeof raw !== "object") return null;
  const asset = raw as Record<string, unknown>;
  if (typeof asset.asset_id !== "string" || !UUID.test(asset.asset_id) || asset.metadata_version !== 1 || typeof asset.available !== "boolean") return null;
  return Object.fromEntries(fields.map(field => [field, asset[field]]));
}
function validCursor(raw: unknown): boolean {
  return raw == null || (Array.isArray(raw) && raw.length === 2 && typeof raw[0] === "number" && Number.isFinite(raw[0]) && raw[0] >= 0 && typeof raw[1] === "string" && UUID.test(raw[1]));
}
export class AssetHost {
  private readonly origin: string;
  private readonly pending = new Map<string, ReturnType<typeof setTimeout>>();
  private closed = false;
  constructor(private readonly host: MessageHost, private readonly frame: FrameWindow, url: string,
    private readonly request: Request, private readonly timeoutMs = 20000) {
    this.origin = new URL(url).origin;
    host.addEventListener("message", this.receive);
  }
  close() {
    this.closed = true;
    this.host.removeEventListener("message", this.receive);
    for (const timer of this.pending.values()) clearTimeout(timer);
    this.pending.clear();
  }
  private reply(nonce: string, result: Record<string, unknown>) {
    if (this.closed) return;
    try { this.frame.postMessage({ type: "fusion-asset-result", nonce, ...result }, this.origin); }
    catch { /* Kapanmış iframe'in sonucu teslim edilemez. */ }
  }
  private receive = (event: MessageEvent) => {
    if (this.closed || event.source !== this.frame || event.origin !== this.origin) return;
    const data = event.data as Record<string, unknown> | null;
    if (!data || typeof data !== "object" ||
      typeof data.type !== "string" || !["fusion-asset-resolve", "fusion-asset-list", "fusion-asset-preview"].includes(data.type) ||
      typeof data.nonce !== "string" || !/^[A-Za-z0-9_-]{1,100}$/.test(data.nonce)) return;
    const listing = data.type === "fusion-asset-list";
    if (listing ? !validCursor(data.cursor) : typeof data.asset_id !== "string" || !UUID.test(data.asset_id)) return;
    const nonce = data.nonce;
    if (this.pending.has(nonce)) return;
    if (this.pending.size >= 16) { this.reply(nonce, { ok: false, metin: "Çok fazla dosya isteği bekliyor." }); return; }
    const timer = setTimeout(() => {
      if (this.pending.get(nonce) !== timer) return;
      this.pending.delete(nonce);
      this.reply(nonce, { ok: false, metin: "Dosya kimliği süre içinde doğrulanamadı." });
    }, this.timeoutMs);
    this.pending.set(nonce, timer);
    const finish = (result: Record<string, unknown>) => {
      if (this.closed || this.pending.get(nonce) !== timer) return;
      clearTimeout(timer); this.pending.delete(nonce); this.reply(nonce, result);
    };
    let pending: Promise<Record<string, unknown>>;
    try {
      pending = listing
        ? this.request("artefakt.liste", { sinir: 50, cursor: data.cursor ?? null })
        : this.request(data.type === "fusion-asset-preview" ? "artefakt.onizle" : "artefakt.coz", { asset_id: data.asset_id });
    }
    catch { finish({ ok: false, metin: "Fusion dosya oturumu bağlı değil." }); return; }
    void pending.then(result => {
      if (result.ok !== true) { finish({ ok: false, metin: "Dosya bu kapsamda doğrulanamadı." }); return; }
      if (listing) {
        if (!Array.isArray(result.items) || result.items.length > 50 || !validCursor(result.next_cursor)) { finish({ ok: false, metin: "Dosya sayfası geçersiz." }); return; }
        const items = result.items.map(reference);
        if (items.some(item => item === null)) { finish({ ok: false, metin: "Dosya kimliği geçersiz." }); return; }
        finish({ ok: true, items, next_cursor: result.next_cursor ?? null }); return;
      }
      if (data.type === "fusion-asset-preview") {
        if (result.asset_id !== data.asset_id || typeof result.data_url !== "string" || result.data_url.length > 1500022 || !/^data:image\/png;base64,[A-Za-z0-9+/]+=*$/.test(result.data_url) || !Number.isSafeInteger(result.width) || Number(result.width) <= 0 || !Number.isSafeInteger(result.height) || Number(result.height) <= 0 || typeof result.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(result.sha256)) {
          finish({ ok: false, metin: "Görsel önizlemesi doğrulanamadı." }); return;
        }
        finish({ ok: true, asset_id: result.asset_id, data_url: result.data_url, width: result.width, height: result.height, sha256: result.sha256 }); return;
      }
      const asset = reference(result.asset);
      if (!asset || asset.asset_id !== data.asset_id) {
        finish({ ok: false, metin: "Dosya kimliği bu kapsamda doğrulanamadı." }); return;
      }
      finish({ ok: true, asset });
    }, () => finish({ ok: false, metin: "Dosya kimliği okunamadı." }));
  };
}
