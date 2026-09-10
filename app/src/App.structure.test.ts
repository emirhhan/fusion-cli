import { describe, expect, it } from "vitest";
import appSource from "./App.tsx?raw";

describe("App modül sınırı", () => {
  it("giriş dosyasını ince bir çalışma zamanı kabuğu olarak tutar", () => {
    const lines = appSource.trim().split("\n");

    expect(lines.length).toBeLessThanOrEqual(80);
    expect(appSource).toContain("useRuntime");
    expect(appSource).toContain("SessionUygulama");
  });
});
