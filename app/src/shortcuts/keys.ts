import data from "../../../src/fusion_cli/config/data/masaustu-kisayollari.json";

/**
 * Masaüstü kısayol tuşları (P-046).
 *
 * Varsayılan tablo, eylem etiketleri ve ayrılmış tuşlar Python paket verisinden GELİR
 * (`config/data/masaustu-kisayollari.json`); kullanıcının `~/.fusion/keybindings.json`
 * `masaustu` bağlamı çekirdekten `kisayol.liste` ile okunur. Tuş yazımı Python'daki
 * `normalize_desktop_key` ile aynıdır: `mod+ctrl+alt+shift+<tuş>`, `mod` macOS'ta ⌘,
 * Windows/Linux'ta Ctrl.
 */

export const COMMAND_PREFIX = "komut:";
export const DEFAULT_BINDINGS: Readonly<Record<string, string>> = data.varsayilan;
export const ACTION_LABELS: Readonly<Record<string, string>> = data.eylemler;
const RESERVED = new Set<string>(data.ayrilmis);
const NAMED_KEYS = new Set<string>(data.adli_tuslar);
const MODIFIERS = ["mod", "ctrl", "alt", "shift"] as const;
type Modifier = (typeof MODIFIERS)[number];

export interface Keymap {
  baglar: Record<string, string>;
  etiketler: Record<string, string>;
  uyarilar: string[];
  yol: string | null;
}

export const DEFAULT_KEYMAP: Keymap = {
  baglar: { ...DEFAULT_BINDINGS },
  etiketler: { ...ACTION_LABELS },
  uyarilar: [],
  yol: null,
};

export function isMacPlatform(nav: Pick<Navigator, "platform" | "userAgent"> = navigator): boolean {
  return /mac|iphone|ipad/i.test(nav.platform || nav.userAgent);
}

function split(text: string): [string[], string] {
  if (text === "+") return [[], "+"];
  if (text.endsWith("++")) return [text.slice(0, -2).split("+").filter(Boolean), "+"];
  const index = text.lastIndexOf("+");
  return [text.slice(0, Math.max(index, 0)).split("+").filter(Boolean), text.slice(index + 1)];
}

const isPunctuation = (key: string) => key.length === 1 && !/[\p{L}\p{N}]/u.test(key);

function compose(parts: readonly string[], key: string): string {
  const kept = isPunctuation(key) ? parts.filter((part) => part !== "shift") : parts;
  return [...MODIFIERS.filter((modifier) => kept.includes(modifier)), key].join("+");
}

/** `Mod+Shift+P` → `mod+shift+p`; geçersiz yazımda `null` (Python ile aynı kurallar). */
export function normalizeKey(raw: string): string | null {
  const text = raw.trim().toLowerCase();
  if (!text) return null;
  const [parts, key] = split(text);
  if (parts.some((part) => !MODIFIERS.includes(part as Modifier)) || new Set(parts).size !== parts.length) return null;
  const printable = key.length === 1 && key.trim() !== "";
  if (!printable && !NAMED_KEYS.has(key)) return null;
  return compose(parts, key);
}

/** Bağlanamayan tuşun nedeni; bağlanabiliyorsa `null`. */
export function keyProblem(key: string): string | null {
  if (RESERVED.has(key)) return "Bu sistem kısayolu (kopyala, yapıştır, kapat…) bağlanamaz.";
  const [parts, final] = split(key);
  const hasModifier = parts.some((part) => part === "mod" || part === "ctrl" || part === "alt");
  if (!hasModifier && !/^f\d{1,2}$/.test(final)) return "⌘/Ctrl, ⌃ ya da ⌥ ile birlikte basmalısın (yalnız F1-F12 tek başına olur).";
  return null;
}

interface KeyLike {
  key: string;
  code: string;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
}

/**
 * Klavye olayını kanonik tuşa çevir; yalnız değiştiriciye basıldıysa `null`.
 *
 * Karakter önce `event.key`'den okunur: Türkçe Q'da Shift+7 `/` verir ve `mod+/` bağına uyar
 * (noktalamada shift düşer). ⌥ ile harf/rakam özel karaktere dönerse (macOS ⌥B → `∫`) fiziksel
 * tuş (`KeyB`, `Digit1`) kullanılır.
 */
export function eventToKey(event: KeyLike, mac: boolean): string | null {
  if (["Meta", "Control", "Alt", "Shift", "AltGraph", "CapsLock", "Dead", "Process"].includes(event.key)) return null;
  if (!mac && event.metaKey) return null; // Windows tuşu işletim sistemine aittir.
  const parts: string[] = [];
  if (mac ? event.metaKey : event.ctrlKey) parts.push("mod");
  if (mac && event.ctrlKey) parts.push("ctrl");
  if (event.altKey) parts.push("alt");
  if (event.shiftKey) parts.push("shift");
  const digit = /^Digit(\d)$/.exec(event.code)?.[1];
  const letter = /^Key([A-Z])$/.exec(event.code)?.[1]?.toLowerCase();
  let key: string;
  if (digit && (event.altKey || /^\d$/.test(event.key))) key = digit;
  else if (letter && (event.altKey || !/^[\p{L}]$/u.test(event.key))) key = letter;
  else if (event.key === " ") key = "space";
  else if (event.key.length === 1) key = event.key.toLowerCase();
  else key = event.key.toLowerCase();
  if (key.length > 1 && !NAMED_KEYS.has(key)) return null;
  return compose(parts, key);
}

/** Dosyadaki bağları bu platformda eşleşecek biçime getir (Windows/Linux'ta `ctrl` = `mod`). */
export function effectiveBindings(baglar: Record<string, string>, mac: boolean): Map<string, string> {
  const table = new Map<string, string>();
  for (const [spec, action] of Object.entries(baglar)) {
    const canonical = normalizeKey(spec);
    if (!canonical) continue;
    if (mac) { table.set(canonical, action); continue; }
    const [parts, key] = split(canonical);
    const mapped = [...new Set(parts.map((part) => (part === "ctrl" ? "mod" : part)))];
    table.set(compose(mapped, key), action);
  }
  return table;
}

/** Eyleme bağlı tuşlar (tablo sırasıyla). */
export function keysForAction(baglar: Record<string, string>, action: string): string[] {
  return Object.entries(baglar).filter(([, value]) => value === action).map(([key]) => key);
}

const MAC_SYMBOLS: Record<string, string> = { mod: "⌘", ctrl: "⌃", alt: "⌥", shift: "⇧" };
const OTHER_SYMBOLS: Record<string, string> = { mod: "Ctrl", ctrl: "Ctrl", alt: "Alt", shift: "Shift" };
const KEY_NAMES: Record<string, string> = {
  escape: "Esc", enter: "↩", tab: "Tab", space: "Boşluk", backspace: "⌫", delete: "⌦",
  arrowup: "↑", arrowdown: "↓", arrowleft: "←", arrowright: "→", home: "Home", end: "End",
  pageup: "PgUp", pagedown: "PgDn",
};

/** Kullanıcıya göster: macOS'ta `⌘⇧P`, diğerlerinde `Ctrl+Shift+P`. */
export function formatKey(key: string, mac: boolean): string {
  const [parts, final] = split(key);
  const name = KEY_NAMES[final] ?? final.toLocaleUpperCase("tr");
  const symbols = mac ? MAC_SYMBOLS : OTHER_SYMBOLS;
  const labels = [...new Set(parts.map((part) => symbols[part] ?? part))];
  return mac ? [...labels, name].join("") : [...labels, name].join("+");
}

/** Eylemin okunur adı: `komut:status` → `/status komutu`. */
export function actionLabel(action: string, etiketler: Record<string, string> = ACTION_LABELS): string {
  if (action.startsWith(COMMAND_PREFIX)) return `/${action.slice(COMMAND_PREFIX.length)} komutu`;
  return etiketler[action] ?? action;
}

/** `kisayol.*` yanıtını doğrula; tanınmıyorsa `null` (eski çekirdek, bozuk yük). */
export function keymapFromPayload(payload: unknown): Keymap | null {
  if (!payload || typeof payload !== "object") return null;
  const raw = payload as Record<string, unknown>;
  if (raw.ok !== true || !raw.baglar || typeof raw.baglar !== "object") return null;
  const baglar = Object.fromEntries(
    Object.entries(raw.baglar as Record<string, unknown>).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  );
  const etiketler = { ...ACTION_LABELS };
  if (Array.isArray(raw.eylemler)) {
    for (const item of raw.eylemler as { ad?: unknown; etiket?: unknown }[]) {
      if (typeof item?.ad === "string" && typeof item.etiket === "string") etiketler[item.ad] = item.etiket;
    }
  }
  const uyarilar = Array.isArray(raw.uyarilar) ? raw.uyarilar.filter((item): item is string => typeof item === "string") : [];
  return { baglar, etiketler, uyarilar, yol: typeof raw.yol === "string" ? raw.yol : null };
}
