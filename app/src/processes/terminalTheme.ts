/**
 * xterm.js'in ihtiyaç duyduğu ölçülebilir yazı tipi ve pencere sınırları.
 *
 * Neden ayrı bir modül: xterm karakter genişliğini canvas'a yazarak ÖLÇER.
 * Ölçüme `var(--font-mono)` gibi bir CSS değişkeni verilirse tarayıcı onu o
 * bağlamda çözemez; genişlik yanlış hesaplanır, `fit` yanlış sütun/satır
 * bulur ve ekran yazdıkça beklenmedik biçimde kayar. Ölçülen hata buydu.
 */

/** Değişken çözülemezse kullanılacak yığın. `tokens.css` ile aynı sırada. */
export const FALLBACK_MONO = '"SFMono-Regular", Consolas, "Liberation Mono", monospace';

/**
 * Geriye kaydırma tamponu (satır).
 *
 * "Gerçek ama ufak" bir terminal isteniyor: sınırsız tampon bellek şişirir,
 * xterm'in varsayılan 1000'i ise uzun bir `git log` çıktısını yutar.
 */
export const SCROLLBACK_LINES = 5_000;

/**
 * CSS özel değişkenini GERÇEK yazı tipi yığınına çöz.
 *
 * `element` verilmezse belge kökünden okunur. Değişken tanımsızsa ya da
 * ortamda `getComputedStyle` yoksa (test ortamı) yedeğe düşülür.
 */
export function resolveMonoFont(element?: Element | null): string {
  if (typeof globalThis.getComputedStyle !== "function") return FALLBACK_MONO;
  const target = element ?? globalThis.document?.documentElement;
  if (!target) return FALLBACK_MONO;
  const value = globalThis.getComputedStyle(target).getPropertyValue("--font-mono").trim();
  return value || FALLBACK_MONO;
}

/** xterm.js'in anladığı tema alt kümesi (tokens.css'ten çözülür). */
export interface TerminalTheme {
  background: string;
  foreground: string;
  cursor: string;
  selectionBackground: string;
}

/** Değişkenler çözülemezse (test ortamı) eski sabit koyu tema. */
export const FALLBACK_TERMINAL_THEME: TerminalTheme = {
  background: "#0f1115",
  foreground: "#e6e6ea",
  cursor: "#e6e6ea",
  selectionBackground: "rgba(120, 160, 255, 0.35)",
};

/**
 * Terminal temasını uygulama token'larından çöz (P-065): açık temada açık zemin,
 * yüksek kontrastta güçlü metin. Ölçüldü (30 Ekim envanteri): terminal zemini
 * `#0f1115` sabitti; açık temada panel içinde kara bir kutu kalıyordu. xterm
 * `var()` çözemediği için değerler burada `getComputedStyle` ile gerçek renge çevrilir.
 */
export function resolveTerminalTheme(element?: Element | null): TerminalTheme {
  if (typeof globalThis.getComputedStyle !== "function") return FALLBACK_TERMINAL_THEME;
  const target = element ?? globalThis.document?.documentElement;
  if (!target) return FALLBACK_TERMINAL_THEME;
  const style = globalThis.getComputedStyle(target);
  const oku = (ad: string, yedek: string) => style.getPropertyValue(ad).trim() || yedek;
  const background = style.getPropertyValue("--surface-canvas").trim();
  if (!background) return FALLBACK_TERMINAL_THEME;
  const foreground = oku("--text-primary", FALLBACK_TERMINAL_THEME.foreground);
  return {
    background,
    foreground,
    cursor: oku("--accent", foreground),
    selectionBackground: oku("--selection-bg", FALLBACK_TERMINAL_THEME.selectionBackground),
  };
}
