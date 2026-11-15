/**
 * Komut paleti öğeleri, sorgu önekleri, puanlama ve "son kullanılanlar" (P-046).
 *
 * Önekler (VS Code / Claude Code alışkanlığı): `>` eylem ve ekran, `/` slash komutu, `@` dosya,
 * `#` sohbet, `?` ayar. Öneksiz sorgu her türde arar. Puanlama Türkçe harfleri katlar
 * ("cubugu" "çubuğu"yu bulur): önce baştan eşleşme, sonra sözcük başı, sonra içerir, en son
 * sırayla harf eşleşmesi.
 */

export type PaletteKind = "eylem" | "ekran" | "sohbet" | "dosya" | "komut" | "ayar";

export interface PaletteItem {
  id: string;
  kind: PaletteKind;
  label: string;
  detail?: string;
  keywords?: string;
  shortcut?: string;
  run: () => void;
}

export const KIND_LABELS: Record<PaletteKind, string> = {
  eylem: "Eylemler",
  ekran: "Ekranlar",
  sohbet: "Sohbetler",
  dosya: "Dosyalar",
  komut: "Komutlar",
  ayar: "Ayarlar",
};

/** Grupların gösterim sırası. */
export const KIND_ORDER: PaletteKind[] = ["eylem", "ekran", "sohbet", "dosya", "komut", "ayar"];

const PREFIXES: Record<string, PaletteKind[]> = {
  ">": ["eylem", "ekran"],
  "/": ["komut"],
  "@": ["dosya"],
  "#": ["sohbet"],
  "?": ["ayar"],
};

export const RECENT_KEY = "fusion.palet.son";
const RECENT_LIMIT = 8;
const RESULT_LIMIT = 60;

export interface ParsedQuery {
  text: string;
  kinds: PaletteKind[] | null;
}

export function parseQuery(raw: string): ParsedQuery {
  const kinds = PREFIXES[raw.charAt(0)];
  return kinds ? { text: raw.slice(1).trim(), kinds } : { text: raw.trim(), kinds: null };
}

const FOLD: Record<string, string> = { ç: "c", ğ: "g", ı: "i", İ: "i", ö: "o", ş: "s", ü: "u", â: "a", î: "i", û: "u" };

export function fold(text: string): string {
  return text.toLocaleLowerCase("tr").replace(/[çğıİöşüâîû]/gu, (char) => FOLD[char] ?? char);
}

/** Sorgu metne ne kadar uyuyor? Eşleşmezse -1. */
export function score(query: string, text: string): number {
  const needle = fold(query.trim());
  if (!needle) return 0;
  const hay = fold(text);
  if (hay.startsWith(needle)) return 1000 - hay.length;
  const wordStart = hay.search(new RegExp(`(^|[\\s/._-])${needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`, "u"));
  if (wordStart >= 0) return 800 - wordStart;
  const index = hay.indexOf(needle);
  if (index >= 0) return 600 - index;
  let position = -1, gaps = 0;
  for (const char of needle) {
    const next = hay.indexOf(char, position + 1);
    if (next < 0) return -1;
    gaps += position < 0 ? next : next - position - 1;
    position = next;
  }
  return Math.max(1, 300 - gaps);
}

/**
 * Sorguya göre süz ve sırala. Boş sorguda önce son kullanılanlar, sonra öğeler verilen sırada
 * (dosyalar boş sorguda gelmez: proje ağacı palette yer kaplamasın).
 */
export function rankItems(items: readonly PaletteItem[], raw: string, recent: readonly string[] = []): PaletteItem[] {
  const { text, kinds } = parseQuery(raw);
  const allowed = items.filter((item) => !kinds || kinds.includes(item.kind));
  if (!text) {
    const byId = new Map(allowed.map((item) => [item.id, item]));
    const recents = recent.flatMap((id) => byId.get(id) ?? []);
    const rest = allowed.filter((item) => !recent.includes(item.id) && (kinds || item.kind !== "dosya"));
    return [...recents, ...rest].slice(0, RESULT_LIMIT);
  }
  return allowed
    .map((item) => ({ item, value: Math.max(score(text, item.label), score(text, `${item.label} ${item.keywords ?? ""} ${item.detail ?? ""}`) - 200) }))
    .filter((entry) => entry.value >= 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, RESULT_LIMIT)
    .map((entry) => entry.item);
}

export function readRecent(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string").slice(0, RECENT_LIMIT) : [];
  } catch {
    return [];
  }
}

export function rememberRecent(id: string): string[] {
  const next = [id, ...readRecent().filter((item) => item !== id)].slice(0, RECENT_LIMIT);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // Depo yazılamıyorsa liste bu oturumda boş kalır; palet yine çalışır.
  }
  return next;
}
