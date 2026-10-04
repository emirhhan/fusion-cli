import { describe, expect, it } from "vitest";

type Outcome = (injection: unknown, before?: string, after?: string) => unknown;

async function load(): Promise<Outcome> {
  const core = (await import("../../../chrome-extension/core.js")) as { injectionOutcome: Outcome };
  return core.injectionOutcome;
}

describe("injectionOutcome", () => {
  it("sayfadaki işlemin sonucunu olduğu gibi verir", async () => {
    const outcome = await load();
    expect(outcome({ result: { clicked: "e4" } }, "http://a/", "http://a/")).toEqual({ clicked: "e4" });
    expect(outcome({ result: false })).toBe(false);
  });

  it("sayfa hatasını yutmaz", async () => {
    const outcome = await load();
    expect(() => outcome({ result: null, error: { message: "Seçim kutusu için chrome_select kullanın." } }))
      .toThrow("Seçim kutusu için chrome_select kullanın.");
    expect(() => outcome({ error: "öğe bulunamadı" })).toThrow("öğe bulunamadı");
  });

  it("boş sonucu başarı saymaz, ne yapılacağını söyler", async () => {
    const outcome = await load();
    expect(() => outcome({ result: null }, "http://a/form", "http://a/form")).toThrow(/chrome_page/);
    expect(() => outcome(undefined)).toThrow(/sonuç döndürmedi/);
  });

  it("işlem sayfayı değiştirdiyse boş sonuç gezinme olarak raporlanır", async () => {
    const outcome = await load();
    expect(outcome({ result: null }, "http://a/form", "http://a/gonder")).toEqual({
      navigated: true,
      url: "http://a/gonder",
    });
  });
});
