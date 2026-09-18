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
});
