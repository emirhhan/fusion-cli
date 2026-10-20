import { describe, expect, it } from "vitest";

type Outcome = (injection: unknown, after?: string) => unknown;
type PageAction = (operation: string, args: Record<string, unknown>) => unknown;

async function load() {
  return (await import("../../../chrome-extension/core.js")) as { injectionOutcome: Outcome; pageAction: PageAction };
}

describe("injectionOutcome", () => {
  it("sayfadaki işlemin sonucunu olduğu gibi verir", async () => {
    const { injectionOutcome } = await load();
    expect(injectionOutcome({ result: { clicked: "e4" } }, "http://a/")).toEqual({ clicked: "e4" });
    expect(injectionOutcome({ result: false })).toBe(false);
  });

  it("sayfa hatasını yutmaz", async () => {
    const { injectionOutcome } = await load();
    expect(() => injectionOutcome({ result: { __hata: "Seçim kutusu için chrome_select kullanın." } }))
      .toThrow("Seçim kutusu için chrome_select kullanın.");
    expect(() => injectionOutcome({ error: "öğe bulunamadı" })).toThrow("öğe bulunamadı");
  });

  it("boş sonuç bağlamın kapandığını gösterir: tıklama sayfayı değiştirdi", async () => {
    const { injectionOutcome } = await load();
    expect(injectionOutcome({ result: null }, "http://a/gonder")).toEqual({ navigated: true, url: "http://a/gonder" });
  });
});

describe("pageAction hata döndürme kipi", () => {
  it("hatayı fırlatmak yerine veri olarak döndürür; kipsiz çağrı eskisi gibi fırlatır", async () => {
    const { pageAction } = await load();
    document.body.innerHTML = "<p>boş</p>";
    const result = pageAction("click", { ref: "yok", __hataDondur: true }) as { __hata?: string };
    expect(typeof result.__hata).toBe("string");
    expect(() => pageAction("click", { ref: "yok" })).toThrow();
  });
});
