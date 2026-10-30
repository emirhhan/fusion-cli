import { describe, expect, it } from "vitest";
import { akisiCalistir } from "./akisCalistir";
import type { Akis } from "./akis";

/** Diskte hangi dosyaların bulunduğunu taklit eden sahte çekirdek. */
function cekirdek() {
  const diskte = new Set<string>();
  const cagrilar: { islem: string; istem: string; referans?: string }[] = [];
  let sayac = 0;
  const istek = async (_ad: string, veri: Record<string, unknown>) => {
    const referans = typeof veri.referans === "string" ? veri.referans : undefined;
    if (referans && !diskte.has(referans)) {
      return { ok: false, code: "reference_invalid", metin: "Referans görsel doğrulanamadı." };
    }
    cagrilar.push({ islem: String(veri.islem), istem: String(veri.istem), referans });
    const yol = `/g/${++sayac}.png`;
    diskte.add(yol);
    return { ok: true, dosyalar: [{ yol }] };
  };
  return { diskte, cagrilar, istek };
}

function akis(): Akis {
  return {
    ad: "x",
    dugumler: [
      { id: "m", tur: "metin", x: 0, y: 0, istem: "kask" },
      { id: "u", tur: "uret", x: 0, y: 0, saglayici: "nim" },
      { id: "v", tur: "varyasyon", x: 0, y: 0, saglayici: "gemini", istem: "mavi" },
      { id: "m2", tur: "metin", x: 0, y: 0, istem: "eldiven" },
      { id: "b", tur: "uret", x: 0, y: 0, saglayici: "nim" },
    ],
    baglantilar: [
      { kaynak: "m", hedef: "u" }, { kaynak: "u", hedef: "v" }, { kaynak: "m2", hedef: "b" },
    ],
  };
}

describe("bitmiş düğümün çıktı dosyası diskten silinmişse", () => {
  it("üst düğüm yeniden üretilir; bağımsız dal gereksiz çalışmaz", async () => {
    const { diskte, cagrilar, istek } = cekirdek();
    const ilk = await akisiCalistir(akis(), istek, () => undefined);
    expect(cagrilar.map((c) => c.islem)).toEqual(["uret", "uret", "varyasyon"]);
    const uYol = ilk.dugumler.find((d) => d.id === "u")?.yol as string;
    // Kullanıcı Varyasyon talimatını değiştirdi ve Üret'in çıktısı galeriden silindi.
    diskte.delete(uYol);
    const degisik: Akis = { ...ilk, dugumler: ilk.dugumler.map((d) => d.id === "v" ? { ...d, istem: "kırmızı" } : d) };
    cagrilar.length = 0;

    const son = await akisiCalistir(degisik, istek, () => undefined);

    // Olmayan referans alt düğüme gitmez: Üret yeniden üretilir, sonra Varyasyon yeni çıktıyla çalışır.
    expect(cagrilar.map((c) => c.islem)).toEqual(["uret", "varyasyon"]);
    const yeniU = son.dugumler.find((d) => d.id === "u");
    expect(yeniU?.yol).not.toBe(uYol);
    expect(cagrilar[1].referans).toBe(yeniU?.yol);
    expect(son.dugumler.find((d) => d.id === "v")?.durum).toBe("bitti");
    // Bağımsız dal (m2 → b) yeniden üretilmedi.
    expect(cagrilar.some((c) => c.istem === "eldiven")).toBe(false);
  });

  it("silinen dosya kullanıcının seçtiği görsel girdisiyse açık hata verir, hiçbir şey üretmez", async () => {
    const { cagrilar, istek } = cekirdek();
    const secili: Akis = {
      ad: "x",
      dugumler: [
        { id: "g", tur: "gorsel", x: 0, y: 0, yol: "/g/silindi.png" },
        { id: "b", tur: "buyut", x: 0, y: 0, saglayici: "gemini" },
      ],
      baglantilar: [{ kaynak: "g", hedef: "b" }],
    };
    const son = await akisiCalistir(secili, istek, () => undefined);
    expect(cagrilar).toEqual([]);
    expect(son.dugumler.find((d) => d.id === "b")).toMatchObject({ durum: "hata" });
    expect(son.dugumler.find((d) => d.id === "b")?.hata).toMatch(/diskte|galeride|yeniden seç/i);
  });
});

it("istek reddedilince hata metni 'Error:' öneki taşımaz (U3-19)", async () => {
  const hatali = async () => { throw new Error("Önce bekleyen görsel işlerinin bitmesi gerekir."); };
  const sonuc = await akisiCalistir({
    ad: "x",
    dugumler: [
      { id: "m", tur: "metin", x: 0, y: 0, istem: "kask" },
      { id: "u", tur: "uret", x: 0, y: 0, saglayici: "p" },
    ],
    baglantilar: [{ kaynak: "m", hedef: "u" }],
  }, hatali, () => undefined);
  const hata = sonuc.dugumler.find((dugum) => dugum.id === "u")?.hata ?? "";
  expect(hata).toBe("Görsel üretilemedi: Önce bekleyen görsel işlerinin bitmesi gerekir.");
});
