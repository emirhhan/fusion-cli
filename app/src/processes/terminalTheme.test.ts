import { afterEach, describe, expect, it } from "vitest";
import { FALLBACK_MONO, FALLBACK_TERMINAL_THEME, SCROLLBACK_LINES, resolveMonoFont, resolveTerminalTheme } from "./terminalTheme";

afterEach(() => {
  document.documentElement.style.removeProperty("--font-mono");
  for (const ad of ["--surface-canvas", "--text-primary", "--accent", "--selection-bg"]) document.documentElement.style.removeProperty(ad);
});

describe("resolveTerminalTheme (P-065)", () => {
  it("terminal zemin ve metin rengini uygulama token'larından alır", () => {
    document.documentElement.style.setProperty("--surface-canvas", "#f9f9fa");
    document.documentElement.style.setProperty("--text-primary", "#111111");
    document.documentElement.style.setProperty("--accent", "#0066ff");
    const tema = resolveTerminalTheme();
    expect(tema.background).toBe("#f9f9fa");
    expect(tema.foreground).toBe("#111111");
    expect(tema.cursor).toBe("#0066ff");
  });

  it("token'lar yokken eski sabit koyu temaya düşer; xterm'e var() gitmez", () => {
    expect(resolveTerminalTheme()).toEqual(FALLBACK_TERMINAL_THEME);
    expect(FALLBACK_TERMINAL_THEME.background).not.toContain("var(");
  });
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
