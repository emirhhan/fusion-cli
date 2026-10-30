import { afterEach, describe, expect, it } from "vitest";
import { LANGUAGE_STORAGE_KEY, SOZLUK, getLanguage, readLanguage, resetLanguageCache, setLanguage, t } from "./language";

afterEach(() => {
  localStorage.clear();
  resetLanguageCache();
  document.documentElement.lang = "tr";
});

describe("arayüz dili (P-065)", () => {
  it("varsayılan Türkçe; geçersiz saklı değer Türkçe'ye düşer", () => {
    expect(readLanguage()).toBe("tr");
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "de");
    expect(readLanguage()).toBe("tr");
  });

  it("İngilizce sözlük Türkçe anahtarların tamamını karşılar (yarım kalan anahtar yok)", () => {
    expect(Object.keys(SOZLUK.en).sort()).toEqual(Object.keys(SOZLUK.tr).sort());
  });

  it("dil değişince html lang güncellenir ve t() o dilde çevirir", () => {
    setLanguage("en");
    expect(document.documentElement.lang).toBe("en");
    expect(getLanguage()).toBe("en");
    expect(t("gorunum.tema")).toBe("Theme");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");
    setLanguage("tr");
    expect(t("gorunum.tema")).toBe("Tema");
  });
});
