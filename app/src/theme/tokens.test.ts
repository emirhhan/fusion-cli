import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";

/** Ölçülmüş değerler sessizce değişmemeli; değişirse referanstan sapılmış olur. */
describe("tasarım token'ları", () => {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  const css = readFileSync(join(__dirname, "./tokens.css"), "utf8");

  it("ölçülmüş renkleri taşır", () => {
    expect(css).toContain("--surface-canvas: #ffffff");
    expect(css).toContain("--surface-sidebar: #f9f9fa");
    expect(css).toContain("--surface-selected: #efeff0");
    expect(css).toContain("--surface-message-user: #f5f5f5");
    // Vurgu tonu BİLEREK referanstan ayrıldı: mor, markanın rengi değil.
    // Yeşil vurgunun açık temadaki sakin karşılığı bu.
    expect(css).toContain("--surface-accent-subtle: #eef7dc");
  });

  it("marka paletini tek kaynakta tanımlar", () => {
    expect(css).toContain("--brand-obsidian: #0b0a0d");
    expect(css).toContain("--brand-carbon: #14181d");
    expect(css).toContain("--brand-soft-white: #f3f5f6");
    expect(css).toContain("--brand-signal: #a8ff3e");
    expect(css).toContain("--brand-signal-deep: #446b00");
  });

  it("Signal Green'i açık temada METİN olarak kullanmaz", () => {
    // #a8ff3e beyaz üstünde 1.23:1 verir; metin olarak okunamaz. Açık temada
    // vurgulu metin koyu yeşile düşer, vurgu rengi yalnız dolgudur.
    const acikTema = css.slice(0, css.indexOf(':root[data-theme="dark"]'));
    expect(acikTema).toContain("--accent-text: var(--brand-signal-deep)");
    expect(acikTema).toContain("--focus-ring: var(--brand-signal-deep)");
  });

  it("koyu temayı marka yüzeylerine bağlar", () => {
    const koyuTema = css.slice(css.indexOf(':root[data-theme="dark"]'));
    expect(koyuTema).toContain("--surface-canvas: #050505");
    expect(koyuTema).toContain("--surface-sidebar: #111111");
    expect(koyuTema).toContain("--text-primary: #f3f5f6");
    expect(koyuTema).toContain("--focus-ring: var(--brand-signal)");
  });

  it("ölçülmüş kenar çubuğu genişliğini taşır", () => {
    expect(css).toContain("--kenar-cubugu-genislik: 260px");
  });

  it("ekranların kullandığı ana metin rengini tanımlar", () => {
    expect(css).toContain("--ana-metin:");
  });

  it("onay diyaloğunun tehlike ve ters metin renklerini tanımlar", () => {
    expect(css).toContain("--tehlike:");
    expect(css).toContain("--ters-metin:");
  });

  it("uygulama tipografisini ve sayfa sıfırlamasını sabitler", () => {
    expect(css).toContain("--font-sans: Satoshi");
    expect(css).toContain("margin: 0");
  });

  it("koyu tema ve azaltılmış hareket sözleşmelerini taşır", () => {
    expect(css).toContain(':root[data-theme="dark"]');
    expect(css).toContain("prefers-reduced-motion: reduce");
    expect(css).toContain("--focus-ring:");
  });

  /* Bkz. bug: metin seçildiğinde çıkan yeşil `::selection` rengi koyu temada
     neredeyse görünmüyordu — eskiden `--surface-accent-subtle` kullanıyordu
     ve koyu karşılığı (#1e2a12) neredeyse siyah zeminden (#050505) ayırt
     edilmiyordu. Artık iki temada da ÖLÇÜLÜ, yüksek kontrastlı marka
     çiftleri kullanılır (bkz. "Signal Green/Obsidian 16.02:1" ölçümü). */
  it("::selection her iki temada da yüksek kontrastlı, ayrı bir token kullanır", () => {
    expect(css).toMatch(/::selection\s*{\s*background:\s*var\(--selection-bg\);\s*color:\s*var\(--selection-text\);\s*}/);

    const acikTema = css.slice(0, css.indexOf(':root[data-theme="dark"]'));
    expect(acikTema).toContain("--selection-bg: var(--brand-signal-deep)");
    expect(acikTema).toContain("--selection-text: var(--text-inverse)");

    const koyuTema = css.slice(css.indexOf(':root[data-theme="dark"]'));
    expect(koyuTema).toContain("--selection-bg: var(--brand-signal)");
    expect(koyuTema).toContain("--selection-text: var(--text-inverse)");
  });
});
