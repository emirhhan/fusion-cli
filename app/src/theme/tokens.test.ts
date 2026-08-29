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
    expect(css).toContain("--surface-accent-subtle: #ebebfa");
  });

  it("ölçülmüş kenar çubuğu genişliğini taşır", () => {
    expect(css).toContain("--kenar-cubugu-genislik: 281px");
  });

  it("ekranların kullandığı ana metin rengini tanımlar", () => {
    expect(css).toContain("--ana-metin:");
  });

  it("onay diyaloğunun tehlike ve ters metin renklerini tanımlar", () => {
    expect(css).toContain("--tehlike:");
    expect(css).toContain("--ters-metin:");
  });

  it("uygulama tipografisini ve sayfa sıfırlamasını sabitler", () => {
    expect(css).toContain("--font-sans: Inter");
    expect(css).toContain("margin: 0");
  });

  it("koyu tema ve azaltılmış hareket sözleşmelerini taşır", () => {
    expect(css).toContain(':root[data-theme="dark"]');
    expect(css).toContain("prefers-reduced-motion: reduce");
    expect(css).toContain("--focus-ring:");
  });
});
