import { describe, expect, it, vi } from "vitest";
import { cuesEnabled, playCue } from "./cues";

describe("seslendirme ipuçları", () => {
  it("ses aygıtı yoksa çökmez", () => {
    const kayit = window.AudioContext;
    // jsdom'da AudioContext yoktur; sessizce geçmeli.
    expect(() => playCue("listen-start")).not.toThrow();
    window.AudioContext = kayit;
  });

  it("azaltılmış hareket tercihinde kapanır", () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce") }));
    expect(cuesEnabled()).toBe(false);
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    expect(cuesEnabled()).toBe(true);
    vi.unstubAllGlobals();
  });
});
