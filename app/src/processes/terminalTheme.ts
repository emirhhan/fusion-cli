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
