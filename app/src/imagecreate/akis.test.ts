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

describe("canlı, büyüyen akış", () => {
  it("sonuçtan bağlı yeni işlem düğümü ekler", async () => {
    const { sonrakiDugumEkle } = await import("./akis");
    const baslangic: Akis = {
      ad: "x",
      dugumler: [{ id: "u", tur: "uret", x: 100, y: 50, saglayici: "nim", yol: "/g/1.jpg", durum: "bitti" }],
      baglantilar: [],
    };
    const { akis, id } = sonrakiDugumEkle(baslangic, "u", "varyasyon", "gemini");
    const yeni = akis.dugumler.find((dugum) => dugum.id === id);
    expect(yeni?.tur).toBe("varyasyon");
    expect(yeni?.saglayici).toBe("gemini");
    expect(yeni!.x).toBeGreaterThan(100);
    expect(akis.baglantilar).toContainEqual({ kaynak: "u", hedef: id });
  });

  it("yalnız hedef düğüm ve eksik girdileri çalışır; girdisi değişmeyen biten düğüm yeniden üretilmez", async () => {
    const { akisiCalistir } = await import("./akisCalistir");
    const cagrilar: string[] = [];
    const istek = async (_ad: string, veri: Record<string, unknown>) => {
      cagrilar.push(String(veri.islem));
      return { ok: true, dosyalar: [{ yol: `/g/${cagrilar.length}.jpg` }] };
    };
    const baslangic: Akis = {
      ad: "x",
      dugumler: [
        { id: "m", tur: "metin", x: 0, y: 0, istem: "kask" },
        { id: "u", tur: "uret", x: 0, y: 0, saglayici: "nim" },
        { id: "v", tur: "varyasyon", x: 0, y: 0, saglayici: "gemini" },
      ],
      baglantilar: [{ kaynak: "m", hedef: "u" }, { kaynak: "u", hedef: "v" }],
    };
    const ilk = await akisiCalistir(baslangic, istek, () => undefined, { hedef: "u" });
    expect(cagrilar).toEqual(["uret"]);
    expect(ilk.dugumler.find((dugum) => dugum.id === "v")?.durum).toBeUndefined();

    await akisiCalistir(ilk, istek, () => undefined);
    // "Üret" girdisi değişmediği için tekrar çalışmaz; yalnız eksik "Varyasyon" üretilir.
    expect(cagrilar).toEqual(["uret", "varyasyon"]);
  });

  it("girdisi değişen biten düğüm yeniden çalışır", async () => {
    const { akisiCalistir } = await import("./akisCalistir");
    const cagrilar: string[] = [];
    const istek = async (_ad: string, veri: Record<string, unknown>) => {
      cagrilar.push(String(veri.istem));
      return { ok: true, dosyalar: [{ yol: `/g/${cagrilar.length}.jpg` }] };
    };
    let akis: Akis = {
      ad: "x",
      dugumler: [
        { id: "m", tur: "metin", x: 0, y: 0, istem: "kask" },
        { id: "u", tur: "uret", x: 0, y: 0, saglayici: "nim" },
      ],
      baglantilar: [{ kaynak: "m", hedef: "u" }],
    };
    akis = await akisiCalistir(akis, istek, () => undefined);
    akis = { ...akis, dugumler: akis.dugumler.map((dugum) => (dugum.id === "m" ? { ...dugum, istem: "mavi kask" } : dugum)) };
    await akisiCalistir(akis, istek, () => undefined);
    expect(cagrilar).toEqual(["kask", "mavi kask"]);
  });
});
