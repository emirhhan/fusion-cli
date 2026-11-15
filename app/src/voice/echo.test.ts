import { describe, expect, it } from "vitest";
import { cevapYankisiMi, yankiMi } from "./echo";

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

describe("cevapYankisiMi", () => {
  const okunan = "Dosya yazılsın mı? Evet ya da hayır de.";

  it("okunan metinde geçen tek kelimelik cevabı yankı sayar", () => {
    expect(cevapYankisiMi("evet", okunan)).toBe(true);
  });

  it("okunan metinde geçmeyen cevabı kullanıcıdan sayar", () => {
    expect(cevapYankisiMi("onayla", okunan)).toBe(false);
  });

  it("Fusion konuşmuyorsa ya da söz boşsa yankı değildir", () => {
    expect(cevapYankisiMi("evet", null)).toBe(false);
    expect(cevapYankisiMi("", okunan)).toBe(false);
  });
});
