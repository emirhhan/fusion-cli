import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Tanımsız token kullanımı sessiz bir hatadır.
 *
 * `var(--olmayan)` yazıldığında tarayıcı özelliği hiç uygulamaz: kenarlık,
 * zemin ve yazı rengi SESSİZCE kaybolur. Ekran görüntüsünde ölçüldü — yeni
 * sağlayıcı listesi ve panel araması `--surface`/`--hairline` gibi var olmayan
 * adlar kullandığı için kutu kenarları hiç çizilmiyordu.
 *
 * Yedekli kullanım (`var(--x, #fff)`) kabul edilir: orada niyet açıktır.
 */

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = join(__dirname, "..");

function cssDosyalari(dizin: string): string[] {
  return readdirSync(dizin).flatMap((ad) => {
    const yol = join(dizin, ad);
    if (statSync(yol).isDirectory()) return cssDosyalari(yol);
    return ad.endsWith(".css") ? [yol] : [];
  });
}

describe("token kullanımı", () => {
  const tokenCss = readFileSync(join(__dirname, "tokens.css"), "utf8");
  const tanimli = new Set(
    [...tokenCss.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((eslesme) => eslesme[1]),
  );

  it("her var(--x) ya tanımlıdır ya da yedeklidir", () => {
    const eksikler: string[] = [];
    for (const dosya of cssDosyalari(SRC)) {
      // Yorumlar çıkarılır: kaldırılmış bir hileyi ANLATAN yorum da eşleşiyordu.
      const css = readFileSync(dosya, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
      for (const eslesme of css.matchAll(/var\(\s*(--[a-z0-9-]+)\s*([,)])/g)) {
        const [, ad, ayrac] = eslesme;
        if (ayrac === ",") continue; // yedekli
        if (tanimli.has(ad)) continue;
        eksikler.push(`${dosya.slice(SRC.length + 1)} → ${ad}`);
      }
    }
    expect(eksikler).toEqual([]);
  });
});
