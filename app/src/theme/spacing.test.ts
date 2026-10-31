import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = (path: string) => readFileSync(resolve(process.cwd(), "src", path), "utf8");

/** Bir seçicinin (ilk) kural gövdesini döndürür. */
function rule(source: string, selector: string): string {
  const start = source.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`kural yok: ${selector}`);
  return source.slice(start, source.indexOf("}", start));
}

/* Ölçüldü (1 Kasım, 1280 px koyu): profil menüsünde "Dil" ile "Yardım" arasında görünmeyen
   ayraç yüzünden açıklamasız boşluk; Ayarlar › Bu bilgisayar'da çerçeveli grubun içindeki
   seçim kartları, notlar ve boş durum metinleri çerçeveye yapışık. */
describe("boşluk ve çerçeve regresyonları", () => {
  it("profil menüsü ayracı menü zemininden ayırt edilir (koyu temada --border-subtle menü zeminine eşitti)", () => {
    const separator = rule(css("screens/Sidebar.css"), ".sidebar__profile-separator");
    expect(separator).not.toContain("var(--border-subtle)");
    expect(separator).toContain("color-mix(in srgb, var(--text-primary)");
  });
});
