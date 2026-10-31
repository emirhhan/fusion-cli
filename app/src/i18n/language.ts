/**
 * Arayüz dili (P-065, temel).
 *
 * Türkçe varsayılan ve tam; İngilizce sözlük şimdilik profil menüsünü, Ayarlar'ın
 * gezinmesini ve Ayarlar › Genel'in Görünüm ve Erişilebilirlik kartlarını kapsar. Metinler bu sözlüğe taşındıkça kapsam büyür;
 * `t()` eksik anahtarda Türkçe'ye düşer, hiçbir ekran boş kalmaz.
 *
 * `<html lang>` çeviri TAMAMLANANA dek "tr" kalır: ölçüldü (31 Ekim), İngilizce seçilince
 * `lang="en"` yazılıyor ama arayüzün neredeyse tamamı Türkçe kalıyordu; ekran okuyucu Türkçe
 * metni İngilizce telaffuzla okuyordu. Seçim `data-language`'a yazılır; yalnız çevrilen
 * düğümler (`useLanguage().lang`) kendi `lang` özniteliğini taşır.
 */

export const LANGUAGE_STORAGE_KEY = "fusion.language.v1";

export type Language = "tr" | "en";

/** Dil seçicide ve menüde gösterilen adlar — her dil kendi adıyla yazılır. */
export const LANGUAGE_NAMES: Record<Language, string> = { tr: "Türkçe", en: "English" };
export const LANGUAGES: readonly Language[] = ["tr", "en"];

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

/** Arayüzün ana dili: çeviri kapsamı tamamlanana dek belge dili budur. */
export const DOCUMENT_LANGUAGE: Language = "tr";

export function applyLanguage(language: Language, root: HTMLElement = document.documentElement): void {
  root.lang = DOCUMENT_LANGUAGE;
  root.dataset.language = language;
}

export const SOZLUK = {
  tr: {
    "gorunum.baslik": "Görünüm",
    "gorunum.tema": "Tema",
    "gorunum.tema.sistem": "Sistemi izle",
    "gorunum.tema.acik": "Açık",
    "gorunum.tema.koyu": "Koyu",
    "gorunum.dil": "Dil",
    "gorunum.dil.ipucu": "Seçim hemen uygulanır ve kalıcıdır. İngilizce çeviri şimdilik kısmi: profil menüsü, Ayarlar gezinmesi, Görünüm ve Erişilebilirlik kartları çevrilir; diğer ekranlar Türkçe kalır.",
    "gorunum.dil.secili": "Seçili",
    "menu.hesabim": "Hesabım",
    "menu.ayarlar": "Ayarlar",
    "menu.kontrol": "Kontrol Paneli",
    "menu.beceriler": "Beceriler ve Ajanlar",
    "menu.mcp": "MCP bağlantıları",
    "menu.dil": "Dil",
    "menu.yardim": "Yardım",
    "menu.geribildirim": "Geri bildirim gönder",
    "menu.cikis": "Çıkış yap",
    "menu.giris": "Giriş yap",
    "ayarlar.baslik": "Ayarlar",
    "ayarlar.geri": "Uygulamaya geri dön",
    "ayarlar.ara": "Ayarları ara",
    "ayarlar.grup.Kişisel": "Kişisel",
    "ayarlar.grup.Entegrasyonlar": "Entegrasyonlar",
    "ayarlar.grup.Sistem": "Sistem",
    "ayarlar.bolum.genel": "Genel",
    "ayarlar.bolum.hesap": "Hesap",
    "ayarlar.bolum.bildirimler": "Bildirimler",
    "ayarlar.bolum.ses": "Ses",
    "ayarlar.bolum.kisayollar": "Kısayollar",
    "ayarlar.bolum.kisisellestirme": "Kişiselleştirme",
    "ayarlar.bolum.modeller": "Modeller",
    "ayarlar.bolum.tarayici": "Tarayıcı",
    "ayarlar.bolum.weboturumlari": "Web oturumları",
    "ayarlar.bolum.izinler": "İzinler",
    "ayarlar.bolum.bilgisayar": "Bu bilgisayar",
    "ayarlar.bolum.zeka": "Zeka",
    "ayarlar.bolum.uzak": "Uzaktan Erişim",
    "ayarlar.bolum.guncellemeler": "Güncellemeler",
    "ayarlar.bolum.gelismis": "Gelişmiş",
    "ayarlar.bolum.nasil": "Nasıl yapılır",
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
    "gorunum.dil.ipucu": "Your choice applies immediately and is remembered. English is partial for now: the profile menu, Settings navigation, Appearance and Accessibility cards are translated; other screens stay in Turkish.",
    "gorunum.dil.secili": "Selected",
    "menu.hesabim": "My account",
    "menu.ayarlar": "Settings",
    "menu.kontrol": "Control Panel",
    "menu.beceriler": "Skills and Agents",
    "menu.mcp": "MCP connections",
    "menu.dil": "Language",
    "menu.yardim": "Help",
    "menu.geribildirim": "Send feedback",
    "menu.cikis": "Sign out",
    "menu.giris": "Sign in",
    "ayarlar.baslik": "Settings",
    "ayarlar.geri": "Back to app",
    "ayarlar.ara": "Search settings",
    "ayarlar.grup.Kişisel": "Personal",
    "ayarlar.grup.Entegrasyonlar": "Integrations",
    "ayarlar.grup.Sistem": "System",
    "ayarlar.bolum.genel": "General",
    "ayarlar.bolum.hesap": "Account",
    "ayarlar.bolum.bildirimler": "Notifications",
    "ayarlar.bolum.ses": "Voice",
    "ayarlar.bolum.kisayollar": "Shortcuts",
    "ayarlar.bolum.kisisellestirme": "Personalization",
    "ayarlar.bolum.modeller": "Models",
    "ayarlar.bolum.tarayici": "Browser",
    "ayarlar.bolum.weboturumlari": "Web sessions",
    "ayarlar.bolum.izinler": "Permissions",
    "ayarlar.bolum.bilgisayar": "This computer",
    "ayarlar.bolum.zeka": "Intelligence",
    "ayarlar.bolum.uzak": "Remote access",
    "ayarlar.bolum.guncellemeler": "Updates",
    "ayarlar.bolum.gelismis": "Advanced",
    "ayarlar.bolum.nasil": "How-to",
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
