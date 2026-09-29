import { calismaSirasi, dugumGuncelle, girdiler, type Akis, type Dugum, type Islem } from "./akis";

export interface UretilenGorsel {
  yol: string;
  genislik: number;
  yukseklik: number;
  istem: string;
  saglayici: string;
}

export type IstekFn = (name: string, data: Record<string, unknown>) => Promise<Record<string, unknown>>;

/** İşlem düğümü için çekirdeğe gidecek istem: bağlı metin + düğümün ek talimatı. */
export function islemIstemi(akis: Akis, dugum: Dugum): string {
  const metin = girdiler(akis, dugum.id).metin?.istem?.trim() ?? "";
  const ek = dugum.istem?.trim() ?? "";
  return [metin, ek].filter(Boolean).join("\n");
}

/**
 * Akışı işlem sırasıyla çalıştırır. Her adımdan sonra güncel akışı `bildir`e
 * verir; bir işlem başarısız olursa kalan işlemler çalıştırılmaz (sonraki
 * düğümler zaten o görsele bağlıdır).
 */
export async function akisiCalistir(
  baslangic: Akis,
  istek: IstekFn,
  bildir: (akis: Akis, yeni: UretilenGorsel[]) => void,
): Promise<Akis> {
  let akis = baslangic;
  for (const planli of calismaSirasi(baslangic)) {
    const dugum = akis.dugumler.find((item) => item.id === planli.id) as Dugum;
    akis = dugumGuncelle(akis, dugum.id, { durum: "calisiyor", hata: undefined });
    bildir(akis, []);
    const istem = islemIstemi(akis, dugum);
    const referans = girdiler(akis, dugum.id).gorsel?.yol;
    let sonuc: Record<string, unknown>;
    try {
      sonuc = await istek("gorsel.olustur", {
        istem,
        saglayici: dugum.saglayici ?? "",
        islem: dugum.tur as Islem,
        ...(referans ? { referans } : {}),
      });
    } catch (reason) {
      sonuc = { ok: false, metin: `Görsel üretilemedi: ${String(reason)}` };
    }
    const dosyalar = sonuc.ok === true && Array.isArray(sonuc.dosyalar)
      ? (sonuc.dosyalar as Record<string, unknown>[])
      : [];
    if (!dosyalar.length) {
      akis = dugumGuncelle(akis, dugum.id, { durum: "hata", hata: String(sonuc.metin ?? "Görsel üretilemedi.") });
      bildir(akis, []);
      return akis;
    }
    const yeni = dosyalar.map((dosya) => ({
      yol: String(dosya.yol),
      genislik: Number(dosya.genislik ?? 0),
      yukseklik: Number(dosya.yukseklik ?? 0),
      istem,
      saglayici: String(sonuc.saglayici ?? ""),
    }));
    akis = dugumGuncelle(akis, dugum.id, { durum: "bitti", yol: yeni[0].yol });
    bildir(akis, yeni);
  }
  return akis;
}
