import { atalar, calismaSirasi, dugumGuncelle, girdiler, MAX_ADET, type Akis, type Dugum, type Islem } from "./akis";

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
export interface CalistirSecenekleri {
  /** Verilirse yalnız bu düğüm ve eksik/değişmiş ataları çalışır. */
  hedef?: string;
  /** UI sahibi değiştiyse yeni sağlayıcı işi başlatma veya eski sonucu yayımlama. */
  devam?: () => boolean;
}

/** Çekirdeğin "referans görsel yok/okunamıyor" cevabı; ham metne bağlı kalınmaz. */
const REFERANS_KODLARI = new Set(["reference_invalid", "referans_yok"]);

/**
 * Ölçüldü (29 Ekim): bitmiş düğümün çıktı dosyası silinmişse düğüm "girdisi
 * değişmedi" diye atlanıyor, alt düğüme olmayan yol gidiyor ve alt düğüm
 * anlaşılmaz bir referans hatasıyla düşüyordu. Artık referans reddedilince
 * üretici düğüm bayat sayılır ve akış bir kez daha planlanır: üst düğüm yeniden
 * üretilir, aynı imzalı bağımsız dallar atlanmaya devam eder. Referans
 * kullanıcının seçtiği görsel düğümündeyse açık hata verilir.
 */
export async function akisiCalistir(
  baslangic: Akis,
  istek: IstekFn,
  bildir: (akis: Akis, yeni: UretilenGorsel[]) => void,
  secenekler: CalistirSecenekleri = {},
): Promise<Akis> {
  let akis = baslangic;
  const kapsam = secenekler.hedef ? new Set([...atalar(baslangic, secenekler.hedef), secenekler.hedef]) : null;
  for (const planli of calismaSirasi(baslangic)) {
    if (secenekler.devam?.() === false) return akis;
    if (kapsam && !kapsam.has(planli.id)) continue;
    const dugum = akis.dugumler.find((item) => item.id === planli.id) as Dugum;
    const istem = islemIstemi(akis, dugum);
    const referans = girdiler(akis, dugum.id).gorsel?.yol;
    const adet = Math.min(Math.max(1, Math.round(dugum.adet ?? 1)), MAX_ADET);
    const imza = JSON.stringify([dugum.tur, istem, referans ?? "", dugum.saglayici ?? "", adet, dugum.oran ?? "1:1"]);
    if (dugum.durum === "kismi" && dugum.girdiImzasi === imza && dugum.id !== secenekler.hedef) {
      return akis;
    }
    // Bitmiş düğüm açıkça çalıştırılırsa yeniden üret; kısmi düğümde aynı
    // girdiye ait başarılı sonuçları koruyup yalnız eksikleri tamamla.
    if (dugum.yol && dugum.girdiImzasi === imza && dugum.id !== secenekler.hedef) continue;
    const tamamla = dugum.durum === "kismi" && dugum.girdiImzasi === imza
      && dugum.id === secenekler.hedef && (dugum.sonuclar?.length ?? 0) > 0
      && (dugum.sonuclar?.length ?? 0) < adet;
    const sonuclar = tamamla ? [...(dugum.sonuclar ?? [])] : [];
    akis = dugumGuncelle(akis, dugum.id, { durum: "calisiyor", hata: undefined });
    bildir(akis, []);
    let hata: string | null = null;
    // Varyasyonlar sırayla istenir: aynı web oturumu tek sohbeti aynı anda işler.
    while (sonuclar.length < adet) {
      if (secenekler.devam?.() === false) return akis;
      const tur = await tekUretim(istek, { istem, saglayici: dugum.saglayici ?? "", islem: dugum.tur as Islem, referans, oran: dugum.oran });
      if (secenekler.devam?.() === false) return akis;
      if ("hata" in tur) {
        const uretici = referans && REFERANS_KODLARI.has(tur.kod) ? referansUreticisi(akis, referans) : undefined;
        if (uretici?.tur === "gorsel") {
          hata = "Girdi görseli diskte yok; Görsel düğümünde yeniden seç.";
        } else if (uretici && sonuclar.length === 0) {
          // Üst düğümün çıktısı kaybolmuş: bayat say, akışı yeniden planla.
          const temiz = dugumGuncelle(akis, uretici.id, {
            durum: "bos", yol: undefined, sonuclar: undefined, girdiImzasi: undefined,
            hata: undefined,
          });
          bildir(temiz, []);
          return akisiCalistir(temiz, istek, bildir, secenekler);
        } else hata = tur.hata;
        break;
      }
      sonuclar.push(...tur.map((gorsel) => gorsel.yol));
      bildir(dugumGuncelle(akis, dugum.id, { sonuclar: [...sonuclar] }), tur);
    }
    if (!sonuclar.length) {
      akis = dugumGuncelle(akis, dugum.id, { durum: "hata", hata: hata ?? "Görsel üretilemedi." });
      bildir(akis, []);
      return akis;
    }
    // Kısmi sonuç korunur; alt düğüme sessizce ilk varyasyon aktarılmaz.
    akis = dugumGuncelle(akis, dugum.id, {
      durum: hata ? "kismi" : "bitti",
      yol: tamamla && dugum.yol && sonuclar.includes(dugum.yol) ? dugum.yol : sonuclar[0],
      sonuclar,
      girdiImzasi: imza,
      hata: hata ? `${sonuclar.length}/${adet} varyasyon üretildi: ${hata}` : undefined,
    });
    bildir(akis, []);
    if (hata) return akis;
  }
  return akis;
}

/** Referans yolunu çıktı olarak taşıyan düğüm (işlem ya da görsel girdisi). */
function referansUreticisi(akis: Akis, referans: string): Dugum | undefined {
  return akis.dugumler.find((dugum) => dugum.yol === referans || dugum.sonuclar?.includes(referans));
}

interface UretimHatasi { hata: string; kod: string }
const GECERSIZ_MAKBUZ: UretimHatasi = { hata: "Görsel üreticisi geçersiz dosya makbuzu döndürdü.", kod: "" };

/** Tek çekirdek çağrısı: üretilen görseller ya da kullanıcıya gösterilecek hata metni. */
async function tekUretim(
  istek: IstekFn,
  veri: { istem: string; saglayici: string; islem: Islem; referans?: string; oran?: string },
): Promise<UretilenGorsel[] | UretimHatasi> {
  let sonuc: Record<string, unknown>;
  try {
    sonuc = await istek("gorsel.olustur", {
      istem: veri.istem,
      saglayici: veri.saglayici,
      islem: veri.islem,
      ...(veri.referans ? { referans: veri.referans } : {}),
      ...(veri.oran && veri.oran !== "1:1" ? { oran: veri.oran } : {}),
    });
  } catch (reason) {
    return { hata: `Görsel üretilemedi: ${String(reason)}`, kod: "" };
  }
  const dosyalar = sonuc.ok === true && Array.isArray(sonuc.dosyalar)
    ? (sonuc.dosyalar as unknown[])
    : [];
  if (!dosyalar.length) return { hata: String(sonuc.metin ?? "Görsel üretilemedi."), kod: String(sonuc.code ?? "") };
  const images: UretilenGorsel[] = [];
  for (const item of dosyalar) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return GECERSIZ_MAKBUZ;
    const dosya = item as Record<string, unknown>;
    if (typeof dosya.yol !== "string" || !dosya.yol.trim()
      || !validDimension(dosya.genislik) || !validDimension(dosya.yukseklik)) {
      return GECERSIZ_MAKBUZ;
    }
    images.push({
      yol: dosya.yol,
      // Eski sağlayıcı makbuzunda boyut yoksa sıfır yalnız bilinmeyen ölçüdür.
      genislik: typeof dosya.genislik === "number" ? dosya.genislik : 0,
      yukseklik: typeof dosya.yukseklik === "number" ? dosya.yukseklik : 0,
      istem: veri.istem,
      saglayici: typeof sonuc.saglayici === "string" ? sonuc.saglayici : "",
    });
  }
  return images;
}

function validDimension(value: unknown): boolean {
  return value === undefined || (typeof value === "number" && Number.isFinite(value) && value > 0);
}
