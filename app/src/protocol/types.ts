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
}

/**
 * Tel üzerinden gelen değeri doğrula. Çekirdek eski sürümse alan hiç gelmez;
 * bozuk gelirse gösterge yanlış bir sayı çizmek yerine hiç çizilmez.
 */
export function baglamOlcusuOku(deger: unknown): BaglamOlcusu | null {
  if (!deger || typeof deger !== "object") return null;
  const { kullanilan, sinir, yuzde, model, model_siniri_token, son_girdi_token, son_girdi_model } = deger as Record<string, unknown>;
  const sayilar = [kullanilan, sinir, yuzde];
  if (!sayilar.every((sayi) => typeof sayi === "number" && Number.isFinite(sayi) && sayi >= 0)) {
    return null;
  }
  if (model !== undefined && model !== null && typeof model !== "string") return null;
  if (model_siniri_token !== undefined && model_siniri_token !== null && (
    typeof model_siniri_token !== "number" || !Number.isInteger(model_siniri_token) || model_siniri_token <= 0
  )) return null;
  if (son_girdi_token !== undefined && son_girdi_token !== null && (
    typeof son_girdi_token !== "number" || !Number.isInteger(son_girdi_token) || son_girdi_token < 0
  )) return null;
  if (son_girdi_model !== undefined && son_girdi_model !== null && typeof son_girdi_model !== "string") return null;
  return {
    kullanilan: kullanilan as number,
    sinir: sinir as number,
    yuzde: Math.min(100, yuzde as number),
    ...(model !== undefined ? { model: model as string | null } : {}),
    ...(model_siniri_token !== undefined ? { model_siniri_token: model_siniri_token as number | null } : {}),
    ...(son_girdi_token !== undefined ? { son_girdi_token: son_girdi_token as number | null } : {}),
    ...(son_girdi_model !== undefined ? { son_girdi_model: son_girdi_model as string | null } : {}),
  };
}
