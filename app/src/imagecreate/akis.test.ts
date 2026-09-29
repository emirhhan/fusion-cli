import { describe, expect, it } from "vitest";
import {
  akisSorunlari,
  baglanabilir,
  baslangicAkisi,
  calismaSirasi,
  dugumGuncelle,
  dugumSil,
  girdiler,
  kaydedilebilir,
  type Akis,
} from "./akis";

function zincir(): Akis {
  return {
    ad: "deneme",
    dugumler: [
      { id: "m", tur: "metin", x: 0, y: 0, istem: "kırmızı kask" },
      { id: "u", tur: "uret", x: 0, y: 0, saglayici: "nim/flux" },
      { id: "v", tur: "varyasyon", x: 0, y: 0, saglayici: "gemini_web/main" },
      { id: "c", tur: "cikti", x: 0, y: 0 },
    ],
    baglantilar: [
      { kaynak: "m", hedef: "u" },
      { kaynak: "u", hedef: "v" },
      { kaynak: "v", hedef: "c" },
    ],
  };
}

describe("görsel akış modeli", () => {
  it("işlem düğümlerini bağımlılık sırasıyla verir", () => {
    expect(calismaSirasi(zincir()).map((dugum) => dugum.id)).toEqual(["u", "v"]);
  });

  it("döngü, kendine ve kabul edilmeyen girdi bağlantısını reddeder", () => {
    const akis = zincir();
    expect(baglanabilir(akis, "v", "u")).toBe(false);
    expect(baglanabilir(akis, "u", "u")).toBe(false);
    expect(baglanabilir(akis, "m", "c")).toBe(false);
    // Üret düğümünün metin girdisi zaten dolu.
    expect(baglanabilir({ ...akis, dugumler: [...akis.dugumler, { id: "m2", tur: "metin", x: 0, y: 0 }] }, "m2", "u")).toBe(false);
  });

  it("zorunlu girdisi eksik düğümü sorun olarak bildirir", () => {
    const akis = dugumSil(zincir(), "m");
    expect(akisSorunlari(akis)).toContain("Üret düğümüne bir Metin bağla.");
    expect(akisSorunlari(zincir())).toEqual([]);
  });

  it("bağlı girdileri türüne göre bulur", () => {
    const bagli = girdiler(zincir(), "v");
    expect(bagli.gorsel?.id).toBe("u");
    expect(bagli.metin).toBeUndefined();
  });

  it("güncelleme ve kaydetme girdi akışı değiştirmez", () => {
    const akis = zincir();
    const yeni = dugumGuncelle(akis, "u", { durum: "hata", hata: "x" });
    expect(akis.dugumler[1].durum).toBeUndefined();
    expect(kaydedilebilir(yeni).dugumler[1]).not.toHaveProperty("durum");
  });

  it("başlangıç akışı Metin → Üret → Çıktı zinciridir", () => {
    const akis = baslangicAkisi("nim/flux");
    expect(akis.dugumler.map((dugum) => dugum.tur)).toEqual(["metin", "uret", "cikti"]);
    expect(akisSorunlari(akis)).toEqual(["Metin düğümü boş."]);
  });
});

describe("varyasyonlu çalıştırma", () => {
  it("adet kadar üretim ister, ilkini seçer ve hepsini sonuç olarak tutar", async () => {
    const { akisiCalistir } = await import("./akisCalistir");
    let sira = 0;
    const istek = async () => ({ ok: true, dosyalar: [{ yol: `/g/${++sira}.jpg` }] });
    const baslangic: Akis = {
      ad: "x",
      dugumler: [
        { id: "m", tur: "metin", x: 0, y: 0, istem: "kask" },
        { id: "u", tur: "uret", x: 0, y: 0, saglayici: "nim", adet: 3 },
      ],
      baglantilar: [{ kaynak: "m", hedef: "u" }],
    };
    const son = await akisiCalistir(baslangic, istek, () => undefined);
    expect(son.dugumler[1].sonuclar).toEqual(["/g/1.jpg", "/g/2.jpg", "/g/3.jpg"]);
    expect(son.dugumler[1].yol).toBe("/g/1.jpg");
    expect(son.dugumler[1].durum).toBe("bitti");
  });

  it("bir kısmı üretilirse iş sürer ve eksik not edilir", async () => {
    const { akisiCalistir } = await import("./akisCalistir");
    let sira = 0;
    const istek = async () => (++sira === 1 ? { ok: true, dosyalar: [{ yol: "/g/1.jpg" }] } : { ok: false, metin: "kota doldu" });
    const baslangic: Akis = {
      ad: "x",
      dugumler: [
        { id: "m", tur: "metin", x: 0, y: 0, istem: "kask" },
        { id: "u", tur: "uret", x: 0, y: 0, saglayici: "nim", adet: 2 },
      ],
      baglantilar: [{ kaynak: "m", hedef: "u" }],
    };
    const son = await akisiCalistir(baslangic, istek, () => undefined);
    expect(son.dugumler[1].durum).toBe("bitti");
    expect(son.dugumler[1].hata).toBe("1/2 varyasyon üretildi: kota doldu");
  });
});
