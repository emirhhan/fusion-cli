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

  it("varsayılanlar paylaşılan veri dosyasından gelir ve Claude Desktop tablosudur (#444)", () => {
    expect(DEFAULT_BINDINGS["mod+/"]).toBe("kisayollar");
    expect(DEFAULT_BINDINGS["mod+w"]).toBe("oturumu_kapat");
    expect(DEFAULT_BINDINGS["ctrl+tab"]).toBe("sonraki_oturum");
    expect(DEFAULT_BINDINGS["ctrl+shift+tab"]).toBe("onceki_oturum");
    expect(DEFAULT_BINDINGS["mod+shift+d"]).toBe("fark_paneli");
    expect(DEFAULT_BINDINGS["ctrl+`"]).toBe("terminal");
    expect(DEFAULT_BINDINGS["mod+\\"]).toBe("paneli_kapat");
    for (const removed of ["mod+k", "mod+p", "mod+b", "mod+j", "mod+alt+b", "mod+1", "mod+9"]) {
      expect(DEFAULT_BINDINGS[removed]).toBeUndefined();
    }
    expect(keyProblem("mod+w")).toBeNull();
  });

  it("⌘⇧] / ⌘⇧[ oturum değiştirir; düzen ] tuşunu kaydırılmamış bildirse de eşleşir (#444)", () => {
    expect(DEFAULT_BINDINGS["mod+}"]).toBe("sonraki_oturum");
    expect(DEFAULT_BINDINGS["mod+{"]).toBe("onceki_oturum");
    expect(eventToKey(press("}", "BracketRight", { metaKey: true, shiftKey: true }), true)).toBe("mod+}");
    expect(eventToKey(press("]", "BracketRight", { metaKey: true, shiftKey: true }), true)).toBe("mod+}");
    expect(eventToKey(press("[", "BracketLeft", { ctrlKey: true, shiftKey: true }), false)).toBe("mod+{");
    expect(eventToKey(press("]", "BracketRight", { metaKey: true }), true)).toBe("mod+]");
    expect(formatKey("mod+}", true)).toBe("⌘⇧]");
    expect(formatKey("mod+{", false)).toBe("Ctrl+Shift+[");
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

  it("Türkçe büyük İ tek harfe (i) iner; kayıt ve eşleşme çalışır", () => {
    // Ölçüldü (31 Ekim): "İ".toLowerCase() iki karakterdir (i + U+0307); olay `null` dönüyordu.
    expect(eventToKey(press("İ", "Quote", { metaKey: true, shiftKey: true }), true)).toBe("mod+shift+i");
    expect(normalizeKey("Mod+Shift+İ")).toBe("mod+shift+i");
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

  it("ctrl+ yazımı sistem tuşu korumasını aşamaz (Windows'ta Ctrl+C kopyalamadır)", () => {
    // Ölçüldü (31 Ekim): `ctrl+c` ayrılmış listede yoktu; Windows'ta mod+c'ye eşlenip yutuluyordu.
    expect(keyProblem("ctrl+c")).toBeTruthy();
    expect(keyProblem("ctrl+v")).toBeTruthy();
    expect(keyProblem("ctrl+k")).toBeNull();
    expect(effectiveBindings({ "ctrl+c": "terminal", "ctrl+k": "palet" }, false).has("mod+c")).toBe(false);
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
