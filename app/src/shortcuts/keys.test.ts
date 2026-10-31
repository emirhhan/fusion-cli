import { describe, expect, it } from "vitest";
import {
  DEFAULT_BINDINGS, effectiveBindings, eventToKey, formatKey, isMacPlatform, keyProblem, keymapFromPayload, normalizeKey,
} from "./keys";

const press = (key: string, code: string, mods: Partial<Record<"metaKey" | "ctrlKey" | "altKey" | "shiftKey", boolean>> = {}) => ({
  key, code, metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, ...mods,
});

describe("masaüstü tuş yazımı (Python normalize_desktop_key ile aynı)", () => {
  it.each([
    ["Mod+K", "mod+k"], ["shift+mod+p", "mod+shift+p"], ["alt+ctrl+mod+1", "mod+ctrl+alt+1"], ["mod+,", "mod+,"],
    ["mod++", "mod++"], ["mod+shift+/", "mod+/"], ["F5", "f5"], ["mod+ArrowUp", "mod+arrowup"],
    ["mod+", null], ["mod+mod+k", null], ["super+k", null], ["mod+kk", null], ["", null],
  ])("%s → %s", (raw, expected) => {
    expect(normalizeKey(raw)).toBe(expected);
  });

  it("değiştiricisiz ve sistem tuşlarını reddeder", () => {
    expect(keyProblem("k")).toBeTruthy();
    expect(keyProblem("shift+k")).toBeTruthy();
    expect(keyProblem("mod+c")).toBeTruthy();
    expect(keyProblem("f5")).toBeNull();
    expect(keyProblem("mod+k")).toBeNull();
  });

  it("varsayılanlar paylaşılan veri dosyasından gelir", () => {
    expect(DEFAULT_BINDINGS["mod+k"]).toBe("palet");
    expect(DEFAULT_BINDINGS["mod+j"]).toBe("terminal");
    expect(DEFAULT_BINDINGS["mod+9"]).toBe("sohbet_9");
  });
});

describe("klavye olayı → tuş", () => {
  it("macOS'ta ⌘ mod, ⌃ ctrl olur; ⌥ ile rakam fiziksel tuştan okunur", () => {
    expect(eventToKey(press("k", "KeyK", { metaKey: true }), true)).toBe("mod+k");
    expect(eventToKey(press("P", "KeyP", { metaKey: true, shiftKey: true }), true)).toBe("mod+shift+p");
    expect(eventToKey(press("1", "Digit1", { metaKey: true }), true)).toBe("mod+1");
    expect(eventToKey(press("¡", "Digit1", { metaKey: true, altKey: true }), true)).toBe("mod+alt+1");
    expect(eventToKey(press("!", "Digit1", { metaKey: true, shiftKey: true }), true)).toBe("mod+!");
    expect(eventToKey(press("k", "KeyK", { ctrlKey: true }), true)).toBe("ctrl+k");
  });

  it("⌥ ile özel karaktere dönen harf fiziksel tuştan alınır", () => {
    expect(eventToKey(press("∫", "KeyB", { metaKey: true, altKey: true }), true)).toBe("mod+alt+b");
  });

  it("Türkçe Q'da Shift+7 ile gelen / noktalama olduğu için shift düşer", () => {
    expect(eventToKey(press("/", "Digit7", { metaKey: true, shiftKey: true }), true)).toBe("mod+/");
    expect(eventToKey(press(",", "Backslash", { metaKey: true }), true)).toBe("mod+,");
  });

  it("Windows/Linux'ta Ctrl mod olur; Windows tuşu ve tek değiştirici yok sayılır", () => {
    expect(eventToKey(press("k", "KeyK", { ctrlKey: true }), false)).toBe("mod+k");
    expect(eventToKey(press("k", "KeyK", { metaKey: true }), false)).toBeNull();
    expect(eventToKey(press("Meta", "MetaLeft", { metaKey: true }), true)).toBeNull();
  });

  it("Windows'ta dosyadaki ctrl+ bağı mod+ olarak eşleşir", () => {
    const table = effectiveBindings({ "ctrl+t": "terminal", "mod+k": "palet" }, false);
    expect(table.get("mod+t")).toBe("terminal");
    expect(table.get("mod+k")).toBe("palet");
    expect(effectiveBindings({ "ctrl+t": "terminal" }, true).get("ctrl+t")).toBe("terminal");
  });
});

describe("gösterim ve yük doğrulama", () => {
  it("platforma göre tuşu yazar", () => {
    expect(formatKey("mod+shift+p", true)).toBe("⌘⇧P");
    expect(formatKey("mod+shift+p", false)).toBe("Ctrl+Shift+P");
    expect(formatKey("mod+,", true)).toBe("⌘,");
    expect(isMacPlatform({ platform: "MacIntel", userAgent: "" })).toBe(true);
    expect(isMacPlatform({ platform: "Win32", userAgent: "" })).toBe(false);
  });

  it("bozuk ya da başarısız yükü kabul etmez", () => {
    expect(keymapFromPayload({ ok: false })).toBeNull();
    expect(keymapFromPayload(null)).toBeNull();
    const keymap = keymapFromPayload({ ok: true, baglar: { "mod+k": "palet", x: 3 }, eylemler: [{ ad: "palet", etiket: "Palet" }], uyarilar: ["u", 2], yol: "/k.json" });
    expect(keymap).toEqual({ baglar: { "mod+k": "palet" }, etiketler: expect.objectContaining({ palet: "Palet" }), uyarilar: ["u"], yol: "/k.json" });
  });
});
