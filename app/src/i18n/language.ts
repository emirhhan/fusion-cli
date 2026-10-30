/**
 * Arayüz dili (P-065, temel).
 *
 * Türkçe varsayılan ve tam; İngilizce sözlük şimdilik Ayarlar › Genel'in Görünüm ve
 * Erişilebilirlik kartlarını kapsar. Metinler bu sözlüğe taşındıkça kapsam büyür;
 * `t()` eksik anahtarda Türkçe'ye düşer, hiçbir ekran boş kalmaz. Dil `<html lang>`'e
 * yazılır ki ekran okuyucu doğru telaffuz etsin.
 */

export const LANGUAGE_STORAGE_KEY = "fusion.language.v1";

export type Language = "tr" | "en";

const isLanguage = (value: string | null): value is Language => value === "tr" || value === "en";

export function readLanguage(storage?: Pick<Storage, "getItem">): Language {
  try {
    const value = (storage ?? localStorage).getItem(LANGUAGE_STORAGE_KEY);
    return isLanguage(value) ? value : "tr";
  } catch {
    return "tr";
  }
}

export function saveLanguage(language: Language, storage?: Pick<Storage, "setItem">): void {
  try {
    (storage ?? localStorage).setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Kalıcılaşmasa da bu pencerede uygulanır.
  }
}

export function applyLanguage(language: Language, root: HTMLElement = document.documentElement): void {
  root.lang = language;
}

export const SOZLUK = {
  tr: {
    "gorunum.baslik": "Görünüm",
    "gorunum.tema": "Tema",
    "gorunum.tema.sistem": "Sistemi izle",
    "gorunum.tema.acik": "Açık",
    "gorunum.tema.koyu": "Koyu",
    "gorunum.dil": "Dil",
    "gorunum.dil.ipucu": "İngilizce çeviri şimdilik kısmi: Görünüm ve Erişilebilirlik ayarlarını kapsar. Diğer ekranlar Türkçe kalır.",
    "erisilebilirlik.baslik": "Erişilebilirlik",
    "erisilebilirlik.yazi": "Yazı boyutu",
    "erisilebilirlik.yazi.small": "Küçük",
    "erisilebilirlik.yazi.normal": "Normal",
    "erisilebilirlik.yazi.large": "Büyük",
    "erisilebilirlik.yazi.xlarge": "Çok büyük",
    "erisilebilirlik.vurgu": "Vurgu rengi",
    "erisilebilirlik.vurgu.brand": "Fusion (camgöbeği)",
    "erisilebilirlik.vurgu.blue": "Mavi",
    "erisilebilirlik.vurgu.violet": "Mor",
    "erisilebilirlik.vurgu.mint": "Nane",
    "erisilebilirlik.hareket": "Hareket (animasyon)",
    "erisilebilirlik.hareket.system": "Sistemi izle",
    "erisilebilirlik.hareket.reduce": "Azalt",
    "erisilebilirlik.hareket.allow": "Her zaman göster",
    "erisilebilirlik.kontrast": "Yüksek kontrast",
    "erisilebilirlik.ipucu": "Yazı boyutu bütün arayüzü ölçekler; terminal ve kod kartları da uyar. Hareketi azalt, sistem ayarından bağımsız çalışır.",
    "atla.icerik": "İçeriğe atla",
    "atla.mesaj": "Mesaj kutusuna atla",
  },
  en: {
    "gorunum.baslik": "Appearance",
    "gorunum.tema": "Theme",
    "gorunum.tema.sistem": "Follow system",
    "gorunum.tema.acik": "Light",
    "gorunum.tema.koyu": "Dark",
    "gorunum.dil": "Language",
    "gorunum.dil.ipucu": "English is partial for now: it covers the Appearance and Accessibility settings. Other screens stay in Turkish.",
    "erisilebilirlik.baslik": "Accessibility",
    "erisilebilirlik.yazi": "Text size",
    "erisilebilirlik.yazi.small": "Small",
    "erisilebilirlik.yazi.normal": "Default",
    "erisilebilirlik.yazi.large": "Large",
    "erisilebilirlik.yazi.xlarge": "Extra large",
    "erisilebilirlik.vurgu": "Accent color",
    "erisilebilirlik.vurgu.brand": "Fusion (cyan)",
    "erisilebilirlik.vurgu.blue": "Blue",
    "erisilebilirlik.vurgu.violet": "Violet",
    "erisilebilirlik.vurgu.mint": "Mint",
    "erisilebilirlik.hareket": "Motion (animations)",
    "erisilebilirlik.hareket.system": "Follow system",
    "erisilebilirlik.hareket.reduce": "Reduce",
    "erisilebilirlik.hareket.allow": "Always show",
    "erisilebilirlik.kontrast": "High contrast",
    "erisilebilirlik.ipucu": "Text size scales the whole interface, including the terminal and code cards. Reduce motion works independently of the system setting.",
    "atla.icerik": "Skip to content",
    "atla.mesaj": "Skip to message box",
  },
} as const satisfies Record<Language, Record<string, string>>;

export type MetinAnahtari = keyof typeof SOZLUK.tr;

/** Anahtarı seçili dilde çevir; sözlükte yoksa Türkçe'ye düş. */
export function t(key: MetinAnahtari, language: Language = getLanguage()): string {
  const sozluk: Record<string, string> = SOZLUK[language];
  return sozluk[key] ?? SOZLUK.tr[key];
}

const aboneler = new Set<() => void>();
let anlik: Language | null = null;

export function getLanguage(): Language {
  if (anlik === null) anlik = readLanguage();
  return anlik;
}

export function subscribeLanguage(listener: () => void): () => void {
  aboneler.add(listener);
  return () => {
    aboneler.delete(listener);
  };
}

export function setLanguage(language: Language): void {
  anlik = language;
  saveLanguage(language);
  applyLanguage(language);
  for (const listener of aboneler) listener();
}

/** Testler için önbelleği sıfırla. */
export function resetLanguageCache(): void {
  anlik = null;
}
