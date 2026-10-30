import { describe, expect, it } from "vitest";
import { baglamOlcusuOku } from "./types";

describe("baglamOlcusuOku", () => {
  it("geçerli ölçüyü olduğu gibi okur", () => {
    expect(baglamOlcusuOku({ kullanilan: 1200, sinir: 24000, yuzde: 5 })).toEqual({
      kullanilan: 1200,
      sinir: 24000,
      yuzde: 5,
    });
  });

  it("alan yoksa ya da bozuksa null döner; gösterge yanlış sayı çizmez", () => {
    expect(baglamOlcusuOku(undefined)).toBeNull();
    expect(baglamOlcusuOku({ kullanilan: 1, sinir: 2 })).toBeNull();
    expect(baglamOlcusuOku({ kullanilan: "1", sinir: 2, yuzde: 3 })).toBeNull();
    expect(baglamOlcusuOku({ kullanilan: -1, sinir: 2, yuzde: 3 })).toBeNull();
  });

  it("yüzdeyi 100'e kırpar", () => {
    expect(baglamOlcusuOku({ kullanilan: 9, sinir: 1, yuzde: 900 })?.yuzde).toBe(100);
  });

  it("bozuk isteğe bağlı alan yalnız kendini düşürür, gösterge kalır (U5-19)", () => {
    const olcu = baglamOlcusuOku({ kullanilan: 1, sinir: 2, yuzde: 50, model_siniri_token: 1.5, son_girdi_model: 7, model: "m" });
    expect(olcu).toEqual({ kullanilan: 1, sinir: 2, yuzde: 50, model: "m" });
  });
});
