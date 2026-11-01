/**
 * Eğitim içeriği — kurulum akışındaki "Eğitim" adımı ve Ayarlar'daki "Nasıl yapılır"
 * sayfası AYNI listeyi okur; metin iki yerde tekrarlanmaz.
 *
 * İçerik ürünün gerçeğini anlatır: her konu uygulamada var olan bir yere işaret eder.
 * Görseller `scripts/capture-guide.mjs` ile çalışan arayüzden alınır (`public/guide`).
 */

import type { SettingsSection } from "../settings/search";

export type GuideGroup = "baslangic" | "calisma" | "baglantilar" | "kisisel";

export type GuideSettingsSection = SettingsSection;

export interface GuideTopic {
  id: string;
  group: GuideGroup;
  /** Görev biçiminde kısa başlık ("… açmak", "… eklemek"). */
  title: string;
  summary: string;
  /** Uygulamada nerede olduğu, tek cümle. */
  where: string;
  /** `public/guide/<image>.webp`; kurulumdaki eğitimde gösterilir. Ayarlar listesi görselsizdir. */
  image?: string;
  imageAlt?: string;
  steps: string[];
  /** Verilirse "Ayarlar'da aç" düğmesi gösterilir. */
  settingsSection?: GuideSettingsSection;
  /** Kurulum akışında da gösterilir mi? (görseli olmalı) Hepsi Ayarlar'da durur. */
  inOnboarding: boolean;
}

export const GUIDE_GROUPS: Record<GuideGroup, string> = {
  baslangic: "Başlangıç",
  calisma: "Çalışırken",
  baglantilar: "Bağlantılar ve genişletme",
  kisisel: "Kişisel ve sistem",
};

/** Fusion 0.7.19 masaüstü — kaynak: docs/NASIL_KULLANILIR.md ve CHANGELOG 0.7.19. */
export const GUIDE_TOPICS: readonly GuideTopic[] = [
  {
    id: "sohbet", group: "baslangic", title: "Yeni sohbet başlatmak",
    summary: "İsteğini düz Türkçe yaz; Fusion yaptığı her adımı sohbette gösterir.",
    where: "Kenar çubuğunda Yeni sohbet (⌘N); sol üstteki Home sohbete döner.",
    image: "sohbet", imageAlt: "Fusion sohbet ekranı: kullanıcı isteği ve Fusion'ın yanıtı",
    steps: [
      "Yeni sohbet'e bas ya da ⌘N; başka bir sayfadaysan sol üstteki Home seni sohbete getirir.",
      "Kutuya isteğini yaz, Enter ile gönder; alt satır için Shift + Enter.",
      "Dosya ya da görsel eklemek için ataç düğmesini kullan veya sürükle bırak; @dosya ile proje dosyasını an.",
      "Çalışan turu Esc ile durdurursun; kutuda / yazınca komutlar listelenir.",
    ],
    inOnboarding: true,
  },
  {
    id: "proje", group: "baslangic", title: "Proje açmak ve değiştirmek",
    summary: "Her sohbet bir klasörde çalışır; Fusion yalnız o klasöre dokunur.",
    where: "Kenar çubuğu → Projeler; sağ panelde Dosyalar, Değişiklikler, Terminal, Önizleme.",
    image: "dosyalar", imageAlt: "Sağ panelde proje dosyaları listesi",
    steps: [
      "Projeler başlığından bir klasör seç ya da yeni proje aç; yeni sohbetler o klasörde başlar.",
      "Sağ paneldeki sekmelerle dosyaları, değişiklikleri, terminali ve önizlemeyi izle.",
      "Sohbet içinde /cd <yol> çalışma dizinini değiştirir; ayrı dalda çalışmak için /worktree.",
    ],
    settingsSection: "izinler", inOnboarding: true,
  },
  {
    id: "saglayici", group: "baslangic", title: "Model sağlayıcısı bağlamak",
    summary: "Kendi aboneliğinle (ChatGPT, Claude, Gemini) ya da bir API anahtarıyla çalış.",
    where: "Profil menüsü → Kontrol Paneli; roller Ayarlar → Modeller.",
    image: "saglayici", imageAlt: "Sağlayıcı listesi: bağlı olanlar ve anahtar bekleyenler",
    steps: [
      "Kontrol Paneli'nde bir abonelik kartına dokun; giriş ayrı pencerede yapılır, oturum bu bilgisayarda kalır.",
      "API anahtarı isteyen karta anahtarı yapıştır; şifreli kasada saklanır, ekranda yeniden gösterilmez.",
      "Ayarlar → Modeller'de varsayılan modeli, öğretmeni ve Fusion hakemini seç; seçim anında kaydedilir.",
    ],
    settingsSection: "modeller", inOnboarding: true,
  },
  {
    id: "kits", group: "baslangic", title: "Kits'i kullanmak",
    summary: "Fusion'ın içinde açılan çalışma alanı: sayfalar, notlar ve hazır araçlar.",
    where: "En soldaki ray → Kits.",
    image: "kits-menu", imageAlt: "Ana menüde Kits seçili",
    steps: [
      "Raydan Kits'i aç; ilk açılış birkaç saniye sürebilir.",
      "Kit'ler kendi içinde çalışır; bilgisayarına ya da Chrome'una erişmek istediklerinde Fusion her seferinde sorar.",
    ],
    inOnboarding: true,
  },
  {
    id: "izin", group: "calisma", title: "İzin kiplerini ve kuralları ayarlamak",
    summary: "Fusion'ın neyi sormadan yapacağını sen belirlersin.",
    where: "Kutunun altındaki kip düğmesi (Shift + Tab); Ayarlar → İzinler.",
    image: "onay", imageAlt: "Fusion bir dosyayı değiştirmeden önce onay istiyor",
    steps: [
      "Kipler: Otomatik, Manuel, Düzenlemeleri kabul et, Plan. Shift + Tab bu dördü arasında döner.",
      "İzinleri atla hiçbir şey sormaz; yanlışlıkla açılmasın diye yalnız kip menüsünden seçilir.",
      "Onay kartında \"Evet, bir daha sorma\" kalıcı kural yazar; \"Not ekle\" ret gerekçesini modele iletir.",
      "Ayarlar → İzinler'de izin ver / sor / yasakla kurallarını Claude Code biçimiyle ekle (ör. Bash(npm test *)); klasör dışını okumayı ya da yazmayı tamamen kapatabilirsin.",
    ],
    settingsSection: "izinler", inOnboarding: true,
  },
  {
    id: "bilgisayar", group: "calisma", title: "Bilgisayar kullanımına izin vermek",
    summary: "Fusion ekranı görüp tıklayabilir ve yazabilir; sınırı sen koyarsın (yalnız macOS).",
    where: "Ayarlar → Bu bilgisayar.",
    steps: [
      "macOS izinleri bölümünde Erişilebilirlik ve Ekran Kaydı için \"İzin iste\"ye bas; Ekran Kaydı'ndan sonra Fusion'ı yeniden aç.",
      "Tavanı seç: Yalnız bak, Tıkla ya da Tam kontrol. Kategori ve uygulama ayarları bu tavanı aşamaz.",
      "Dokunulmasını istemediğin uygulamaları Reddedilen uygulamalar'a ekle.",
      "Gönder, sil, öde düğmeleri ve Sistem Ayarları her seferinde sorulur; fiziksel Esc turu durdurur.",
    ],
    settingsSection: "bilgisayar", inOnboarding: false,
  },
  {
    id: "rewind", group: "calisma", title: "Geri almak (/rewind)",
    summary: "Kodu ve konuşmayı önceki bir noktaya döndür.",
    where: "Kutuda /rewind; sağ panel → Değişiklikler.",
    steps: [
      "/rewind ile önceki bir noktayı seç; kod, konuşma ya da ikisi birden geri döner (terminalde Esc Esc).",
      "Tek bir dosyayı geri almak için Değişiklikler sekmesini kullan.",
      "Geri alma yalnız Fusion'ın yaptığı değişikliği geri alır; commit'lenmemiş kendi işine dokunmaz.",
    ],
    inOnboarding: false,
  },
  {
    id: "gecmis", group: "calisma", title: "Sohbeti sürdürmek",
    summary: "Fusion, Claude Code ya da Codex'te kaldığın yerden devam et.",
    where: "Kenar çubuğundaki sohbet listesi; Devam et; kutuda /resume.",
    image: "gecmis", imageAlt: "Önceki bir sohbetin önizlemesi ve devam et düğmesi",
    steps: [
      "Kendi sohbetlerin kenar çubuğunda durur; tıklayınca kaldığın yerden açılır.",
      "/resume listeden seçtirir, /rename adlandırır, /branch sohbeti dallandırır.",
      "Claude Code ya da Codex geçmişi için Devam et'ten kaynağı seç, önizle ve Sürdür'e bas; anahtar benzeri metinler önceden uyarılır.",
    ],
    inOnboarding: true,
  },
  {
    id: "arkaplan", group: "calisma", title: "Arka plan görevleri ve zamanlama",
    summary: "Uzun işi arka plana al, tekrar eden işi saatine bağla.",
    where: "Kutuda /bg ve /tasks; raydaki Zamanlananlar ve Kitaplık.",
    steps: [
      "/bg <görev> işi arka planda başlatır; sohbet serbest kalır, bitince bildirim gelir.",
      "/tasks çalışan ve biten arka plan işlerini listeler.",
      "/loop 30m <görev> işi aralıklarla tekrarlar; günlük ya da haftalık iş için Zamanlananlar'ı kullan.",
      "Üretilen ve yüklenen dosyalar Kitaplık'ta toplanır.",
    ],
    inOnboarding: false,
  },
  {
    id: "ekip", group: "calisma", title: "Kişilik ve alt ajan kullanmak",
    summary: "Büyük işi uzman alt ajanlara böl ya da oturumu bir kişilikle sürdür.",
    where: "Kutuda /persona ve /subtask; sağ panel → Ajanlar.",
    steps: [
      "/persona ile oturumu bir ajan kişiliğiyle sürdür (ör. explore ya da plan).",
      "Kendi alt ajanını .claude/agents/<ad>.md dosyasıyla tanımla: model, araçlar, izin kipi.",
      "Büyük işlerde Fusion alt ajanları kendisi başlatır; Ajanlar sekmesinden canlı izle ya da durdur.",
      "/subtask, bu sohbetin bağlamını devralan bir alt ajan açar.",
    ],
    inOnboarding: false,
  },
  {
    id: "gorsel", group: "calisma", title: "Görsel oluştur",
    summary: "Tarif et, Fusion görseli üretsin.",
    where: "Komut paleti (⌘K) → Görsel oluştur.",
    steps: [
      "⌘K ile komut paletini açıp \"Görsel oluştur\" eylemini seç.",
      "Ne istediğini yaz, boyutu ve sağlayıcıyı seç, üret; sonuçlar listede toplanır.",
    ],
    inOnboarding: false,
  },
  {
    id: "beceriler", group: "baglantilar", title: "Beceriler ve slash komutları",
    summary: "Claude, Codex ve Fusion becerilerini çağır; proje talimatını yönet.",
    where: "Profil menüsü → Beceriler ve Ajanlar; kutuda /.",
    steps: [
      "Beceriler ve Ajanlar ekranında becerileri, ajanları ve talimatları gör; istemediğini kapat.",
      "Kutuya / yaz ve komutu ya da beceriyi seç; $ad da aynı beceriyi çağırır.",
      "/init proje talimatı (CLAUDE.md) yazar, /doctor prompt talimatı denetler; yüklenen dosyalar Ayarlar → Kişiselleştirme'de listelenir.",
    ],
    settingsSection: "kisisellestirme", inOnboarding: false,
  },
  {
    id: "mcp", group: "baglantilar", title: "MCP sunucusu eklemek",
    summary: "Fusion'ı GitHub, Notion, veritabanı gibi araçlara bağla.",
    where: "Profil menüsü → MCP bağlantıları.",
    steps: [
      "Keşfet sekmesinde bir uygulamayı seç ve Bağlan ya da Kur'a bas; OAuth isteyenlerde giriş penceresi açılır.",
      "Listede olmayan sunucu için Ekle'ye bas; komut ya da adres gir. Projedeki .mcp.json da okunur.",
      "Bağlı sekmesinde durumu ve araçları gör, bağlantıyı kaldır.",
    ],
    inOnboarding: false,
  },
  {
    id: "kancalar", group: "baglantilar", title: "Kanca (hook) eklemek",
    summary: "Belirli olaylarda kendi komutunu çalıştır; Claude Code kancaları aynen çalışır.",
    where: "~/.claude/settings.json içindeki \"hooks\" bloğu; liste Ayarlar → İzinler → Kancalar.",
    steps: [
      "Kancayı ~/.claude/settings.json ya da projedeki .claude/settings.json dosyasının \"hooks\" bloğuna yaz.",
      "PreToolUse çıkış 2 ile aracı engeller, Stop bitmemiş işi sürdürür, SessionStart bağlam ekler.",
      "Tanımlı kancalar Ayarlar → İzinler'de salt okunur listelenir; güvenilmeyen projede kancalar çalışmaz.",
    ],
    settingsSection: "izinler", inOnboarding: false,
  },
  {
    id: "oturum-aktar", group: "baglantilar", title: "Tarayıcı oturumu ve çerez aktarmak",
    summary: "Ajanın tarayıcısı senin oturumunla, yalnız seçtiğin sitelerde çalışsın.",
    where: "Ayarlar → Web oturumları.",
    steps: [
      "Oturum içe aktar'da kaynağı seç: Dosyadan (cookies.txt ya da JSON), Chrome'dan ya da Model oturumundan.",
      "Profile ad ver, \"Alan adlarını göster\" ile taşınacak siteleri işaretle; hiçbiri hazır seçili gelmez.",
      "Çerezler şifreli saklanır; ajan profili her yüklemeden önce onay ister.",
    ],
    settingsSection: "weboturumlari", inOnboarding: false,
  },
  {
    id: "chrome", group: "baglantilar", title: "Chrome eklentisini kurmak",
    summary: "Fusion açık Chrome sekmene, verdiğin izinle bakabilsin.",
    where: "Ayarlar → Tarayıcı.",
    image: "ayar-tarayici", imageAlt: "Tarayıcı ayarları: Chrome eklentisi kurulum durumu ve Eklentiyi kur düğmesi",
    steps: [
      "Ayarlar → Tarayıcı'da \"Eklentiyi kur\"a bas.",
      "macOS ilk seferde Erişilebilirlik izni ister: Sistem Ayarları → Gizlilik ve Güvenlik → Erişilebilirlik'te Fusion'ı aç (bir kez).",
      "Chrome'daki tek onayı kabul et; \"Chrome'a yüklendi\" ve \"Fusion ile eşleşti\" Tamam olunca kurulum biter.",
    ],
    settingsSection: "tarayici", inOnboarding: true,
  },
  {
    id: "uzak", group: "baglantilar", title: "Telefondan uzaktan kontrol",
    summary: "Bilgisayardaki Fusion'ı telefonundan, yalnız kendi cihazlarına açık şekilde kullan.",
    where: "Ayarlar → Uzaktan Erişim; üst çubuktaki Uzaktan kontrol göstergesi.",
    image: "ayar-uzak", imageAlt: "Uzaktan erişim ayarları ve Tailscale kurulum rehberi",
    steps: [
      "Tailscale'i bilgisayara ve telefona kur, ikisinde de aynı hesapla giriş yap.",
      "Erişim türü olarak \"Özel tünel (Tailscale)\"ı seç, \"Dinlemeyi başlat\"a bas ve ekrandaki komutu bir kez çalıştır.",
      "Verilen https adresini telefonda aç, Ana Ekrana Ekle; eşleştirme kodunu oluşturup telefona gir.",
      "Riskli işlemler bu bilgisayarda ya da süreli yetki verdiğin telefonda onaylanır.",
    ],
    settingsSection: "uzak", inOnboarding: true,
  },
  {
    id: "ses", group: "kisisel", title: "Sesle konuşmak",
    summary: "Yazmak yerine konuş; Fusion sesli yanıt versin.",
    where: "Kutudaki ses düğmesi; ayarlar Ayarlar → Ses.",
    image: "ayar-ses", imageAlt: "Ses ayarları: konuşma hızı ve ses seçimi",
    steps: [
      "Kutunun sağındaki ses düğmesine bas; macOS mikrofon iznini bir kez onayla.",
      "Konuş; Fusion işi yapar ve sesli yanıt verir. Hızı Ayarlar → Ses'ten değiştir.",
    ],
    settingsSection: "ses", inOnboarding: true,
  },
  {
    id: "kisisel", group: "kisisel", title: "Bellek ve kalıcı talimat",
    summary: "Nasıl çalışmasını istediğini bir kez söyle.",
    where: "Ayarlar → Kişiselleştirme; kutuda # ile not.",
    steps: [
      "Kalıcı talimat'a tercihlerini yaz (ör. \"Türkçe yaz, değişiklikten sonra testleri çalıştır\") ve kaydet.",
      "Otomatik bellek proje notlarını BELLEK.md'ye yazar; /memory ile düzenle, kutuda # ile not ekle.",
      "Claude Code, Codex, Gemini CLI ya da Cursor ayarlarını Başka araçtan içe aktar ile taşı (/import).",
    ],
    settingsSection: "kisisellestirme", inOnboarding: false,
  },
  {
    id: "kisayollar", group: "kisisel", title: "Kısayollar ve komut paleti",
    summary: "Her eylem, sohbet, dosya ve ayar ⌘K'dan bulunur.",
    where: "⌘K; tuşları değiştirmek için Ayarlar → Kısayollar.",
    steps: [
      "⌘K paleti açar; ⌘P dosyaya gider, ⌘N yeni sohbet, ⌘, Ayarlar, ⌘J terminal, ⌘1-9 sohbetler arasında geçer.",
      "Ayarlar → Kısayollar'da bir eylemin tuşunu değiştir; bağlar keybindings.json'a yazılır.",
    ],
    settingsSection: "kisayollar", inOnboarding: false,
  },
  {
    id: "genel", group: "kisisel", title: "Tema, dil ve erişilebilirlik",
    summary: "Görünümü, yazı boyutunu ve dili kendine göre ayarla.",
    where: "Ayarlar → Genel; dil profil menüsünden de değişir.",
    steps: [
      "Temayı Açık, Koyu ya da Sistem seç; yazı boyutu, vurgu rengi, hareket ve yüksek kontrast aynı yerde.",
      "Ayarlar'ın üstündeki arama kutusu bir ayarı adıyla bulur.",
    ],
    settingsSection: "genel", inOnboarding: false,
  },
  {
    id: "guncelleme", group: "kisisel", title: "Güncellemek",
    summary: "Yeni sürümü gör, notlarını oku ve kur.",
    where: "Ayarlar → Güncellemeler; yeni sürüm kenar çubuğunda da haber verilir.",
    steps: [
      "Ayarlar → Güncellemeler'de yeni sürümü indir ve kur; çalışan tur varken kurulum beklenir.",
      "Sürüm notlarını aynı yerde ya da /release-notes ile oku.",
    ],
    settingsSection: "guncellemeler", inOnboarding: false,
  },
];

export function guideImageUrl(topic: Pick<GuideTopic, "image">): string | null {
  return topic.image ? `/guide/${topic.image}.webp` : null;
}

export const ONBOARDING_TOPICS: readonly GuideTopic[] = GUIDE_TOPICS.filter((topic) => topic.inOnboarding);
