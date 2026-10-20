import { describe, expect, it } from "vitest";
import { yankiMi } from "./echo";

describe("yankiMi", () => {
  const konusulan = "Bugün hava çok güzel, dışarı çıkmak için ideal bir gün";

  it("seslendirilen metnin parcasini yanki sayar", () => {
    expect(yankiMi("hava çok güzel dışarı", konusulan)).toBe(true);
  });

  it("kullanicinin yeni sozunu yanki saymaz", () => {
    expect(yankiMi("hayır onu değil şunu yap", konusulan)).toBe(false);
  });

  it("Fusion konusmuyorsa hicbir sey yanki degildir", () => {
    expect(yankiMi("hava çok güzel", null)).toBe(false);
  });

  it("tek kelimeyi ayiklamaz; tesadufi eslesme riski yuksek", () => {
    expect(yankiMi("güzel", konusulan)).toBe(false);
  });

  it("noktalama ve buyuk harf farki eslesmeyi bozmaz", () => {
    expect(yankiMi("BUGÜN HAVA, ÇOK GÜZEL!", konusulan)).toBe(true);
  });

  it("Turkce I/ı ayrimini korur", () => {
    expect(yankiMi("dışarı çıkmak için", konusulan)).toBe(true);
  });

  it("araya giren soz yanki kelimeleri tasisa da yeni soz baskinsa gecer", () => {
    expect(yankiMi("dur bir saniye başka bir şey soracağım güzel", konusulan)).toBe(false);
  });
});
