import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = (path: string) => readFileSync(resolve(process.cwd(), "src", path), "utf8");

/* Ölçüldü (31 Ekim, 900/1280/1600 px, açık/koyu, yüksek kontrast + "Çok büyük" yazı):
   Kontrol Paneli'nde gövde 760 px'te sola yaslanıp başlıktan kopuyor, rol kartları
   190 px'te "Gemini · 3.6 Flas…" diye kesiliyordu; Ayarlar'da seçim kutusu 190 px'te
   "Fusion (camgöbe" diye kırpılıyordu; koyu yüksek kontrastta kapalı anahtar görünmüyordu. */
describe("boyut ve yüksek kontrast regresyonları", () => {
  it("Kontrol Paneli gövdesi başlıkla aynı sayfa sütununda ortalanır", () => {
    const panel = css("control/ControlPanel.css");
    expect(panel).toMatch(/\.control-panel__layout \{[^}]*margin: 0 auto;[^}]*max-width: var\(--page-max-width\)/);
    expect(panel).not.toMatch(/\.control-panel__section \{[^}]*max-width: 760px/);
  });

  it("rol ve sağlayıcı kartlarının en küçük genişliği yazıyla ölçeklenir ve taşmaz", () => {
    expect(css("settings/sections/RoleModels.css")).toContain(".rm__roles { grid-template-columns: repeat(auto-fill, minmax(min(100%, 14rem), 1fr)); }");
    expect(css("control/ProviderList.css")).toContain("minmax(min(100%, 11rem), 1fr)");
  });

  it("Ayarlar seçim kutusu sabit 190 px ile kırpılmaz; satır etiketleri yazı ölçeğine uyar", () => {
    const settings = css("settings/Settings.css");
    expect(settings).not.toContain("max-width: 190px");
    expect(settings).toContain("max-width: min(55%, 18rem)");
    expect(settings).toContain(".settings__panel .settings__row > span { color: var(--settings-text); font-size: var(--text-sm); }");
  });

  it("yüksek kontrastta kapalı anahtar kenar çizgili koyu zemin alır", () => {
    const a11y = css("theme/accessibility.css");
    expect(a11y).toContain(':root[data-contrast="high"] .settings__row--check input[type="checkbox"]:not(:checked)');
    expect(a11y).toContain(':root[data-contrast="high"] .rm__switch input:not(:checked) + .rm__switch-ui');
    expect(a11y).toMatch(/box-shadow: inset 0 0 0 2px var\(--border-strong\)/);
  });
});
