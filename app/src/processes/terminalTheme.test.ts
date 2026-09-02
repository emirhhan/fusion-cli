import { afterEach, describe, expect, it } from "vitest";
import { FALLBACK_MONO, SCROLLBACK_LINES, resolveMonoFont } from "./terminalTheme";

afterEach(() => {
  document.documentElement.style.removeProperty("--font-mono");
});

describe("resolveMonoFont", () => {
  it("CSS değişkenini gerçek yazı tipi yığınına çözer", () => {
    document.documentElement.style.setProperty("--font-mono", "Menlo, monospace");
    expect(resolveMonoFont()).toBe("Menlo, monospace");
  });

  it("değişken tanımsızsa yedeğe düşer; xterm'e asla var() verilmez", () => {
    expect(resolveMonoFont()).toBe(FALLBACK_MONO);
    expect(resolveMonoFont()).not.toContain("var(");
  });

  it("geriye kaydırma tamponu sınırlıdır", () => {
    expect(SCROLLBACK_LINES).toBeGreaterThan(1000);
    expect(Number.isFinite(SCROLLBACK_LINES)).toBe(true);
  });
});
