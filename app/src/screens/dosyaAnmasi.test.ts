/** `@` ile dosya anmanın saf ayrıştırması. */
import { describe, expect, it } from "vitest";

import { anmayiBul, anmayiDegistir } from "./dosyaAnmasi";

describe("anmayiBul", () => {
  it("metnin başındaki @ anmayı açar", () => {
    expect(anmayiBul("@comp", 5)).toEqual({ baslangic: 0, sorgu: "comp" });
  });

  it("boşluktan sonraki @ anmayı açar", () => {
    expect(anmayiBul("şunu oku @src/a", 15)).toEqual({ baslangic: 9, sorgu: "src/a" });
  });

  it("sadece @ yazınca boş sorguyla açılır", () => {
    // Liste `@` basılır basılmaz görünmeli; kullanıcı henüz bir şey yazmadı.
    expect(anmayiBul("@", 1)).toEqual({ baslangic: 0, sorgu: "" });
  });

  it("kelime ortasındaki @ anma DEĞİLDİR", () => {
    // `posta@ornek.com` bir e-postadır, dosya anması değil.
    expect(anmayiBul("posta@ornek", 11)).toBeNull();
  });

  it("boşluk görünce anma kapanır", () => {
    expect(anmayiBul("@src/a.py devam", 15)).toBeNull();
  });

  it("imlecin ÖNÜNDEKİ parçaya bakar", () => {
    // Kullanıcı cümlenin ortasına dönüp yazıyor olabilir.
    expect(anmayiBul("@comp ve sonra", 5)).toEqual({ baslangic: 0, sorgu: "comp" });
  });

  it("parantez içinde anma açılır", () => {
    expect(anmayiBul("(@src", 5)).toEqual({ baslangic: 1, sorgu: "src" });
  });

  it("@ yoksa null döner", () => {
    expect(anmayiBul("düz metin", 9)).toBeNull();
  });
});

describe("anmayiDegistir", () => {
  it("anmayı yolla değiştirir ve ardına boşluk koyar", () => {
    const anma = anmayiBul("@comp", 5)!;
    expect(anmayiDegistir("@comp", anma, 5, "src/Composer.tsx")).toEqual({
      metin: "@src/Composer.tsx ",
      imlec: 18,
    });
  });

  it("cümlenin ortasındaki anmayı değiştirirken kalanı korur", () => {
    const metin = "şunu @comp oku";
    const anma = anmayiBul(metin, 10)!;
    expect(anmayiDegistir(metin, anma, 10, "a/b.ts")).toEqual({
      metin: "şunu @a/b.ts  oku",
      imlec: 13,
    });
  });
});
