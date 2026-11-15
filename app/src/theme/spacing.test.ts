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

  it("çerçeveli grup gövdesindeki satır dışı çocuklar (seçim kartları, alanlar, notlar) iç boşluk alır", () => {
    const panels = css("settings/Panels.css");
    expect(rule(panels, ".px-group__body")).toContain("--px-pad-x: var(--space-5)");
    expect(panels).toContain(".px-group__body > :where(:not(.px-row, .px-item, .px-steps)) { margin: 0; padding: var(--px-pad-y, var(--space-4)) var(--px-pad-x, var(--space-5)); }");
    // Ayraç kuralı fieldset'in `border: 0` sıfırlamasından SONRA gelmeli; yoksa seçim kartlarının üstünde çizgi kaybolur.
    expect(panels.lastIndexOf(".px-group__body > * + *")).toBeGreaterThan(panels.indexOf(".px-choices { border: 0"));
    // legend yüzer: fieldset'in iç boşluğu legend'ın üstüne de uygulanır.
    expect(rule(panels, ".px-choices legend")).toContain("float: left");
  });

  it("Bu bilgisayar listeleri gövde iç boşluğuyla hizalı; giriş + düğme satırı aynı yükseklikte", () => {
    const computer = css("settings/sections/Computer.css");
    expect(rule(computer, ".computer-settings__list li")).toContain("padding: var(--space-3) var(--px-pad-x, 0)");
    expect(computer).toContain(".computer-settings__add > * { min-height: 40px; }");
  });

  it("izin tablosunda yalnız silme düğmeli son sütun dardır; klasör dışı anahtarları çerçeveli grupta durur", () => {
    const permissions = css("settings/sections/Permissions.css");
    expect(permissions).not.toMatch(/\.permissions__table td:last-child \{[^}]*width: 44px/);
    expect(permissions).toContain(".permissions__table td:last-child:has(> button)");
    expect(rule(permissions, ".permissions__blocks")).toContain("border: 1px solid var(--settings-border)");
  });

  it("etiket + açıklama + kart ızgarası aralığı paragraf kenar boşluğuna değil ızgara gap'ine bağlıdır", () => {
    // `.control-panel__section p { margin: 0 }` açıklamanın alt boşluğunu sıfırlıyor, kartlar yapışıyordu.
    expect(rule(css("control/ProviderList.css"), ".pv-group")).toContain("gap: var(--space-3)");
    expect(rule(css("control/ProviderList.css"), ".pv-group__title p")).toContain("margin: 0");
    expect(rule(css("settings/sections/RoleModels.css"), ".rm__sub")).toContain("display: grid");
  });

  it("Ayarlar'da anahtar satırının çizgisinden sonra gelen içerik çizgiye yapışmaz", () => {
    expect(css("settings/Settings.css")).toContain(".settings__panel .settings__row + :not(.settings__row, .settings__row-group) { margin-top: var(--space-3); }");
  });

  it("Ayarlar tabloları ve listeleri başlıkla hizalı; liste sonunda çift çizgi yok", () => {
    expect(css("settings/sections/Shortcuts.css")).toContain(".shortcuts__table :is(th, td):first-child { padding-inline-start: 0; }");
    expect(css("settings/Settings.css")).toContain(".settings__panel .settings__list li:last-child { border-bottom: 0; }");
  });
});
