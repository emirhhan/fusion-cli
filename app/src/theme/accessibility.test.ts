import { afterEach, describe, expect, it } from "vitest";
import {
  ACCESSIBILITY_STORAGE_KEY,
  VARSAYILAN_ERISILEBILIRLIK,
  applyAccessibility,
  getAccessibilityPreferences,
  parseAccessibilityPreferences,
  readAccessibilityPreferences,
  resetAccessibilityCache,
  setAccessibilityPreference,
} from "./accessibility";

afterEach(() => {
  localStorage.clear();
  resetAccessibilityCache();
  applyAccessibility(VARSAYILAN_ERISILEBILIRLIK);
});

describe("erişilebilirlik tercihleri (P-065)", () => {
  it("bozuk ya da eksik değer varsayılana düşer; bilinen alanlar korunur", () => {
    expect(parseAccessibilityPreferences("{bozuk")).toEqual(VARSAYILAN_ERISILEBILIRLIK);
    expect(parseAccessibilityPreferences(JSON.stringify({ fontScale: "dev", motion: "reduce", accent: "violet", highContrast: "evet" })))
      .toEqual({ fontScale: "normal", highContrast: false, motion: "reduce", accent: "violet" });
  });

  it("varsayılan tercih belge köküne hiç öznitelik bırakmaz (eski CSS birebir çalışır)", () => {
    applyAccessibility(VARSAYILAN_ERISILEBILIRLIK);
    const root = document.documentElement;
    expect(root.dataset.fontScale).toBeUndefined();
    expect(root.dataset.contrast).toBeUndefined();
    expect(root.dataset.motion).toBeUndefined();
    expect(root.dataset.accent).toBeUndefined();
    expect(root.style.getPropertyValue("--font-scale")).toBe("");
  });

  it("yazı ölçeği öznitelik ve CSS değişkeni olarak uygulanır", () => {
    applyAccessibility({ ...VARSAYILAN_ERISILEBILIRLIK, fontScale: "large" });
    expect(document.documentElement.dataset.fontScale).toBe("large");
    expect(document.documentElement.style.getPropertyValue("--font-scale")).toBe("1.125");
    applyAccessibility({ ...VARSAYILAN_ERISILEBILIRLIK, fontScale: "normal" });
    expect(document.documentElement.dataset.fontScale).toBeUndefined();
  });

  it("kontrast, hareket ve vurgu öznitelikleri yazılır", () => {
    applyAccessibility({ fontScale: "normal", highContrast: true, motion: "reduce", accent: "blue" });
    const root = document.documentElement;
    expect(root.dataset.contrast).toBe("high");
    expect(root.dataset.motion).toBe("reduce");
    expect(root.dataset.accent).toBe("blue");
  });

  it("değişiklik kalıcılaşır, uygulanır ve yeniden okunur", () => {
    setAccessibilityPreference("motion", "allow");
    expect(getAccessibilityPreferences().motion).toBe("allow");
    expect(document.documentElement.dataset.motion).toBe("allow");
    expect(JSON.parse(localStorage.getItem(ACCESSIBILITY_STORAGE_KEY) ?? "{}").motion).toBe("allow");
    resetAccessibilityCache();
    expect(readAccessibilityPreferences().motion).toBe("allow");
  });

  it("depo erişimi düşerse varsayılanla sürer", () => {
    expect(readAccessibilityPreferences({ getItem: () => { throw new Error("SecurityError"); } })).toEqual(VARSAYILAN_ERISILEBILIRLIK);
  });
});
