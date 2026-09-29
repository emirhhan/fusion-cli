import { calismaSirasi, dugumGuncelle, girdiler, MAX_ADET, type Akis, type Dugum, type Islem } from "./akis";

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
    const adet = Math.min(Math.max(1, Math.round(dugum.adet ?? 1)), MAX_ADET);
    const uretilen: UretilenGorsel[] = [];
    let hata: string | null = null;
    // Varyasyonlar sırayla istenir: aynı web oturumu tek sohbeti aynı anda işler.
    for (let sira = 0; sira < adet; sira += 1) {
      const tur = await tekUretim(istek, { istem, saglayici: dugum.saglayici ?? "", islem: dugum.tur as Islem, referans });
      if (typeof tur === "string") { hata = tur; break; }
      uretilen.push(...tur);
      bildir(dugumGuncelle(akis, dugum.id, { sonuclar: uretilen.map((gorsel) => gorsel.yol) }), tur);
    }
    if (!uretilen.length) {
      akis = dugumGuncelle(akis, dugum.id, { durum: "hata", hata: hata ?? "Görsel üretilemedi." });
      bildir(akis, []);
      return akis;
    }
    // Bir kısmı üretildiyse iş sürer; eksik varyasyon düğümde not olarak kalır.
    akis = dugumGuncelle(akis, dugum.id, {
      durum: "bitti",
      yol: uretilen[0].yol,
      sonuclar: uretilen.map((gorsel) => gorsel.yol),
      hata: hata ? `${uretilen.length}/${adet} varyasyon üretildi: ${hata}` : undefined,
    });
    bildir(akis, []);
  }
  return akis;
}

/** Tek çekirdek çağrısı: üretilen görseller ya da kullanıcıya gösterilecek hata metni. */
async function tekUretim(
  istek: IstekFn,
  veri: { istem: string; saglayici: string; islem: Islem; referans?: string },
): Promise<UretilenGorsel[] | string> {
  let sonuc: Record<string, unknown>;
  try {
    sonuc = await istek("gorsel.olustur", {
      istem: veri.istem,
      saglayici: veri.saglayici,
      islem: veri.islem,
      ...(veri.referans ? { referans: veri.referans } : {}),
    });
  } catch (reason) {
    return `Görsel üretilemedi: ${String(reason)}`;
  }
  const dosyalar = sonuc.ok === true && Array.isArray(sonuc.dosyalar)
    ? (sonuc.dosyalar as Record<string, unknown>[])
    : [];
  if (!dosyalar.length) return String(sonuc.metin ?? "Görsel üretilemedi.");
  return dosyalar.map((dosya) => ({
    yol: String(dosya.yol),
    genislik: Number(dosya.genislik ?? 0),
    yukseklik: Number(dosya.yukseklik ?? 0),
    istem: veri.istem,
    saglayici: String(sonuc.saglayici ?? ""),
  }));
}
