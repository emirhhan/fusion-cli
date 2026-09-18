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
  argumanlar?: Record<string, string>;
  tehlike?: string | null;
  soru?: string;
  secenekler?: { deger?: string; etiket: string; aciklama?: string }[];
  onerilen?: string | null;
  /** Düzenleme onaylarında "ne değişecek" önizlemesi (unified diff). */
  diff?: string;
}

/**
 * Kalan bağlam ölçüsü (`oturum.durum` → `baglam`).
 *
 * `sinir`, çekirdeğin geçmişi özetlemeye başladığı karakter eşiğidir; web
 * oturumunda çok daha düşüktür. `yuzde` 0–100 arasına kırpılmış doluluktur.
 */
export interface BaglamOlcusu {
  kullanilan: number;
  sinir: number;
  yuzde: number;
}

/**
 * Tel üzerinden gelen değeri doğrula. Çekirdek eski sürümse alan hiç gelmez;
 * bozuk gelirse gösterge yanlış bir sayı çizmek yerine hiç çizilmez.
 */
export function baglamOlcusuOku(deger: unknown): BaglamOlcusu | null {
  if (!deger || typeof deger !== "object") return null;
  const { kullanilan, sinir, yuzde } = deger as Record<string, unknown>;
  const sayilar = [kullanilan, sinir, yuzde];
  if (!sayilar.every((sayi) => typeof sayi === "number" && Number.isFinite(sayi) && sayi >= 0)) {
    return null;
  }
  return {
    kullanilan: kullanilan as number,
    sinir: sinir as number,
    yuzde: Math.min(100, yuzde as number),
  };
}
