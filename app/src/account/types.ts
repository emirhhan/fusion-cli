/** Hesap uçlarının tel üzerindeki tipleri. Parola ve karma BURADA YOKTUR. */

export interface Hesap {
  kimlik: string;
  kullanici_adi: string;
  eposta: string;
  avatar: string;
  olusturuldu: number;
}

export interface HesapDurumu {
  hesaplar: Hesap[];
  /** Açık hesabın kimliği; kimse giriş yapmadıysa boş. */
  etkin: string;
  /** Hiç hesap yoksa true: giriş değil KAYIT ekranı gösterilir. */
  kurulum_gerekli: boolean;
}

/** Kayıt sonucu — kurtarma kodu yalnız burada döner, bir daha gösterilmez. */
export interface KayitSonucu {
  hesap: Hesap;
  kurtarma_kodu: string;
  /** Hesapsız kurulumdan devralınan yapılandırma dosyaları. */
  devralinan_ayarlar: string[];
}

/** Hesap satırının baş harfleri — avatar yoksa kullanılır. */
export function hesapBasHarfleri(hesap: Pick<Hesap, "kullanici_adi">): string {
  return hesap.kullanici_adi
    .split(/\s+/)
    .slice(0, 2)
    .map((parca) => parca[0] ?? "")
    .join("")
    .toLocaleUpperCase("tr");
}
