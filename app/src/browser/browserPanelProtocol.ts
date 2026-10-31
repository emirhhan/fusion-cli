/**
 * Tarayıcı paneli (P-045) ile çekirdek arasındaki `tarayici_panel.*` yüklerinin çözümü ve
 * klavye eşlemesi. Bileşenden ayrıdır: saf işlevler doğrudan sınanır.
 */

export const BROWSER_RPC = "tarayici_panel.";
/** Görüntü çekme aralığı (ms). Çekirdek yalnız sayfa değişince yeni kare verir; boşta yük yok. */
export const FRAME_POLL_MS = 200;
/** Öğe seçicide imleç hareketinin en sık gönderilme aralığı (ms). */
export const HOVER_THROTTLE_MS = 120;
/** Fare tekerleğinin biriktirilip tek istekte gönderilme aralığı (ms). */
export const SCROLL_FLUSH_MS = 80;

export interface BrowserTab { no: number; baslik: string; url: string; etkin: boolean }
export interface BrowserFrame { base64: string; mime: string; genislik: number; yukseklik: number }

export interface BrowserState {
  acik: boolean;
  profil: string;
  kullaniciProfili: string;
  denetim: "kullanici" | "ajan";
  /** Ajanın tarayıcı aracı kullanıcının denetimi bırakmasını bekliyor. */
  ajanBekliyor: boolean;
  ajanPaylasir: boolean;
  profilOnayi: boolean;
  ajanGoruyor: boolean;
  turSuruyor: boolean;
}

export interface BrowserSnapshot extends BrowserState {
  seq: number;
  url: string;
  baslik: string;
  sekmeler: BrowserTab[];
  kare: BrowserFrame | null;
}

export interface PickedElement { secici: string; etiket: string; metin: string; yol: string; kutu: Box | null }
export interface Box { x: number; y: number; w: number; h: number }

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function errorText(payload: Record<string, unknown>, fallback: string): string {
  return typeof payload.metin === "string" && payload.metin ? payload.metin : fallback;
}

export function decodeState(payload: Record<string, unknown>): BrowserState {
  return {
    acik: payload.acik === true,
    profil: text(payload.profil),
    kullaniciProfili: text(payload.kullanici_profili),
    denetim: payload.denetim === "kullanici" ? "kullanici" : "ajan",
    ajanBekliyor: payload.ajan_bekliyor === true,
    ajanPaylasir: payload.ajan_paylasir !== false,
    profilOnayi: payload.profil_onayi === true,
    ajanGoruyor: payload.ajan_goruyor === true,
    turSuruyor: payload.tur_suruyor === true,
  };
}

export function decodeSnapshot(payload: Record<string, unknown>): BrowserSnapshot {
  const tabs = (Array.isArray(payload.sekmeler) ? payload.sekmeler : []).flatMap((item) => {
    const row = item as Record<string, unknown>;
    if (!row || typeof row.no !== "number") return [];
    return [{ no: row.no, baslik: text(row.baslik), url: text(row.url), etkin: row.etkin === true }];
  });
  const raw = payload.kare as Record<string, unknown> | undefined;
  const kare = raw && typeof raw.base64 === "string" && raw.base64
    ? {
      base64: raw.base64,
      mime: typeof raw.mime === "string" ? raw.mime : "image/jpeg",
      genislik: typeof raw.genislik === "number" ? raw.genislik : 0,
      yukseklik: typeof raw.yukseklik === "number" ? raw.yukseklik : 0,
    }
    : null;
  return {
    ...decodeState(payload),
    seq: typeof payload.seq === "number" ? payload.seq : 0,
    url: text(payload.url),
    baslik: text(payload.baslik),
    sekmeler: tabs,
    kare,
  };
}

export function decodeBox(value: unknown): Box | null {
  const box = value as Record<string, unknown> | null;
  if (!box || ![box.x, box.y, box.w, box.h].every((part) => typeof part === "number")) return null;
  return { x: box.x as number, y: box.y as number, w: box.w as number, h: box.h as number };
}

export function decodePick(payload: Record<string, unknown>): PickedElement {
  if (payload.ok !== true || typeof payload.secici !== "string") {
    throw new Error(errorText(payload, "Öğe seçilemedi."));
  }
  return {
    secici: payload.secici,
    etiket: text(payload.etiket),
    metin: text(payload.metin),
    yol: text(payload.yol),
    kutu: decodeBox(payload.kutu),
  };
}

/** Görüntü üstündeki imleç konumunu sayfanın 0..1 koordinatına çevir. */
export function normalizedPoint(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
): { x: number; y: number } | null {
  if (rect.width <= 0 || rect.height <= 0) return null;
  const x = (clientX - rect.left) / rect.width;
  const y = (clientY - rect.top) / rect.height;
  if (x < 0 || x > 1 || y < 0 || y > 1) return null;
  return { x, y };
}

const SPECIAL_KEYS = new Set([
  "Enter", "Tab", "Escape", "Backspace", "Delete", "Insert", "Home", "End", "PageUp", "PageDown",
  "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
  "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
]);

export type KeyAction = { tur: "yaz"; metin: string } | { tur: "tus"; tus: string } | null;

/**
 * Klavye olayını çekirdeğe gidecek eyleme çevir. Değiştiricisiz yazılabilir karakter metin
 * olarak yazılır (Türkçe harfler dahil); kısayollar ve özel tuşlar Playwright adıyla basılır.
 * Kopyala/yapıştır gibi uygulama kısayolları (Cmd+C/V) yakalanmaz: yapıştırma `paste` ile gider.
 */
export function keyAction(event: {
  key: string; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; metaKey: boolean;
}): KeyAction {
  const { key } = event;
  const command = event.ctrlKey || event.metaKey;
  if (!command && key.length === 1) return { tur: "yaz", metin: key };
  if (command && ["c", "v", "x"].includes(key.toLowerCase())) return null;
  const isSpecial = SPECIAL_KEYS.has(key);
  const isCombo = command && /^[A-Za-z0-9]$/.test(key);
  if (!isSpecial && !isCombo) return null;
  const mods = [
    event.ctrlKey ? "Control" : "",
    event.altKey ? "Alt" : "",
    event.shiftKey && (isSpecial || isCombo) ? "Shift" : "",
    event.metaKey ? "Meta" : "",
  ].filter(Boolean);
  return { tur: "tus", tus: [...mods, key].join("+") };
}

/** Panel adres çubuğu için: şemasız adres `https://` (yerel ise `http://`) alır. */
export function addressFromInput(value: string): string {
  const raw = value.trim();
  if (!raw) return "";
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(raw)) return raw;
  return /^(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i.test(raw) ? `http://${raw}` : `https://${raw}`;
}

/** Görünüm seçenekleri: ajanın ve kullanıcının gördüğü sayfa ölçüsü (CSS piksel). */
export const BROWSER_VIEWPORTS = [
  { id: "desktop", label: "Masaüstü · 1280", width: 1280, height: 800 },
  { id: "laptop", label: "1440", width: 1440, height: 900 },
  { id: "tablet", label: "Tablet · 768", width: 768, height: 1024 },
  { id: "mobile", label: "Mobil · 375", width: 375, height: 812 },
] as const;
