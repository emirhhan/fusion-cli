import { describe, expect, it } from "vitest";
import { allConnectors, featuredConnectors, requiredRunner } from "./catalog";

describe("bağlantı kataloğu", () => {
  it("npm'de desteklenmeyen ya da hiç olmayan paketleri içermez", () => {
    // 18 Eylül 2026 `npm view`: puppeteer/gdrive/slack deprecated, gmail 404.
    const removed = ["server-puppeteer", "server-gdrive", "server-gmail", "server-slack"];
    for (const entry of allConnectors) {
      for (const name of removed) expect(entry.command ?? "").not.toContain(name);
    }
  });

  it("uzak girişler Streamable HTTP uç noktasını kullanır, SSE adresini değil", () => {
    for (const entry of allConnectors.filter((e) => e.transport === "streamable_http")) {
      expect(entry.url ?? "").not.toMatch(/\/sse$/);
    }
  });

  it("tam 3 öne çıkan giriş vardır ve kimlikler benzersizdir", () => {
    expect(featuredConnectors).toHaveLength(3);
    expect(new Set(allConnectors.map((e) => e.id)).size).toBe(allConnectors.length);
  });

  it("gereken çalıştırıcıyı komuttan türetir", () => {
    const byId = (id: string) => allConnectors.find((e) => e.id === id)!;
    expect(requiredRunner(byId("fetch"))).toBe("uvx");
    expect(requiredRunner(byId("playwright"))).toBe("npx");
    expect(requiredRunner(byId("notion"))).toBeNull();
  });
});
