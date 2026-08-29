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
}
