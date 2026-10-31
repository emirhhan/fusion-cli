/** Tel biçimi: satır başına bir JSON nesnesi. Anahtarlar Türkçedir. */

export type GelenTip = "olay" | "sonuc" | "soru";

export interface GelenMesaj {
  tip: GelenTip;
  id?: string;
  veri: Record<string, unknown>;
}

export interface Istek {
  tip: "istek";
  id: string;
  ad: string;
  veri: Record<string, unknown>;
}

export interface Cevap {
  tip: "cevap";
  id: string;
  veri: Record<string, unknown>;
}

/** Onay ya da serbest metin sorusu. `tur` alanı hangisi olduğunu söyler. */
export interface Soru {
  tur: "onay" | "soru";
  arac?: string;
  /** Çekirdek `ad='değer'` listesi gönderir; eski istemciler sözlük bekliyordu. */
  argumanlar?: string[] | Record<string, string>;
  /** İzin kartının insan dilindeki tek cümlelik başlığı. */
  baslik?: string;
  /** Komut, dosya yolu ya da adres — olduğu gibi gösterilir. */
  hedef?: string;
  tehlike?: string | null;
  /** Neden soruluyor / silme hedefi — tehlike değil, bilgi. */
  neden?: string | null;
  soru?: string;
  secenekler?: { deger?: string; etiket: string; aciklama?: string }[];
  onerilen?: string | null;
  /** Düzenleme onaylarında "ne değişecek" önizlemesi (unified diff). */
  diff?: string;
  /** Eşleşen izin kuralı (`Bash(npm run *)`); kartta bilgi satırı (P-001). */
  kural?: string | null;
  /** Çekirdek cevaptaki `not` alanını okur: ret gerekçesi modele gider (P-013). */
  not_alinir?: boolean;
}

/**
 * Kalan bağlam ölçüsü (`oturum.durum` → `baglam`).
 *
 * `sinir` geçmişin özetleme eşiğidir; modelin tam token penceresi değildir.
 * Model penceresi yalnız doğrulanabilirse ayrıca bildirilir.
 */
export interface BaglamOlcusu {
  kullanilan: number;
  sinir: number;
  yuzde: number;
  model?: string | null;
  model_siniri_token?: number | null;
  son_girdi_token?: number | null;
  son_girdi_model?: string | null;
  son_girdi_pencere_token?: number | null;
  son_girdi_pencere_yuzde?: number | null;
}

/**
 * Tel üzerinden gelen değeri doğrula. Çekirdek eski sürümse alan hiç gelmez;
 * bozuk gelirse gösterge yanlış bir sayı çizmek yerine hiç çizilmez.
 */
export function baglamOlcusuOku(deger: unknown): BaglamOlcusu | null {
  if (!deger || typeof deger !== "object") return null;
  const {
    kullanilan, sinir, yuzde, model, model_siniri_token, son_girdi_token,
    son_girdi_model, son_girdi_pencere_token, son_girdi_pencere_yuzde,
  } = deger as Record<string, unknown>;
  const sayilar = [kullanilan, sinir, yuzde];
  if (!sayilar.every((sayi) => typeof sayi === "number" && Number.isFinite(sayi) && sayi >= 0)) {
    return null;
  }
  // İsteğe bağlı alanlardan biri bozuksa YALNIZ o alan düşer; zorunlu üçlü sağlamsa gösterge
  // çizilmeye devam eder (U5-19). Bozuk bir ek alan tüm göstergeyi gizlemesin.
  const gecerliMetin = (v: unknown): string | null | undefined =>
    v === undefined || v === null || typeof v === "string" ? v : undefined;
  const gecerliTam = (v: unknown, enAz: number): number | null | undefined =>
    v === undefined || v === null || (typeof v === "number" && Number.isInteger(v) && v >= enAz) ? v : undefined;
  const modelOk = gecerliMetin(model);
  const modelSiniri = gecerliTam(model_siniri_token, 1);
  const sonGirdi = gecerliTam(son_girdi_token, 0);
  const sonGirdiModel = gecerliMetin(son_girdi_model);
  const sonGirdiPencere = gecerliTam(son_girdi_pencere_token, 1);
  const sonGirdiYuzde =
    son_girdi_pencere_yuzde === undefined || son_girdi_pencere_yuzde === null
    || (typeof son_girdi_pencere_yuzde === "number" && Number.isFinite(son_girdi_pencere_yuzde)
      && son_girdi_pencere_yuzde >= 0 && son_girdi_pencere_yuzde <= 100)
      ? (son_girdi_pencere_yuzde as number | null | undefined) : undefined;
  return {
    kullanilan: kullanilan as number,
    sinir: sinir as number,
    yuzde: Math.min(100, yuzde as number),
    ...(modelOk !== undefined ? { model: modelOk } : {}),
    ...(modelSiniri !== undefined ? { model_siniri_token: modelSiniri } : {}),
    ...(sonGirdi !== undefined ? { son_girdi_token: sonGirdi } : {}),
    ...(sonGirdiModel !== undefined ? { son_girdi_model: sonGirdiModel } : {}),
    ...(sonGirdiPencere !== undefined ? { son_girdi_pencere_token: sonGirdiPencere } : {}),
    ...(sonGirdiYuzde !== undefined ? { son_girdi_pencere_yuzde: sonGirdiYuzde } : {}),
  };
}
