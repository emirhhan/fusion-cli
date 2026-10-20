/**
 * Eğitim içeriği — kurulum akışındaki "Eğitim" adımı ve Ayarlar'daki "Nasıl yapılır"
 * sayfası AYNI listeyi okur; metin iki yerde tekrarlanmaz.
 *
 * İçerik ürünün gerçeğini anlatır: her konu uygulamada var olan bir yere işaret eder.
 * Görseller `scripts/capture-guide.mjs` ile çalışan arayüzden alınır (`public/guide`).
 */

export type GuideGroup = "baslangic" | "calisma" | "baglantilar" | "kisisel";

export type GuideSettingsSection =
  | "genel" | "ses" | "kisisellestirme" | "modeller" | "tarayici" | "izinler" | "uzak" | "guncellemeler";

export interface GuideTopic {
  id: string;
  group: GuideGroup;
  title: string;
  summary: string;
  /** Uygulamada nerede olduğu, tek cümle. */
  where: string;
  /** `public/guide/<image>.webp` */
  image: string;
  imageAlt: string;
  steps: string[];
  /** Verilirse "Ayarlar'da aç" düğmesi gösterilir. */
  settingsSection?: GuideSettingsSection;
  /** Kurulum akışında da gösterilir mi? Hepsi Ayarlar'da durur. */
  inOnboarding: boolean;
}

export const GUIDE_GROUPS: Record<GuideGroup, string> = {
  baslangic: "Başlangıç",
  calisma: "Çalışma alanı",
  baglantilar: "Bağlantılar",
  kisisel: "Kişisel ve sistem",
};

export const GUIDE_TOPICS: readonly GuideTopic[] = [
  {
    id: "sohbet", group: "baslangic", title: "Sohbet ve görev verme",
    summary: "Fusion'a ne yapmasını istediğini düz Türkçe yaz.",
    where: "Ana ekranın altındaki yazı kutusu.",
    image: "sohbet", imageAlt: "Fusion sohbet ekranı: kullanıcı isteği ve Fusion'ın yanıtı",
    steps: [
      "Alttaki kutuya isteğini yaz (ör. \"Bu projeyi incele ve eksikleri açıkla\").",
      "Enter ile gönder; satır atlamak için Shift + Enter kullan.",
      "Fusion çalışırken yaptığı işler sohbette satır satır görünür.",
      "Kutudaki ataç düğmesiyle dosya veya görsel ekleyebilirsin.",
    ],
    inOnboarding: true,
  },
  {
    id: "proje", group: "baslangic", title: "Proje açma ve değiştirme",
    summary: "Fusion yalnız seçtiğin klasörde çalışır.",
    where: "Sol kenar çubuğu → Projeler; sağ panelde Dosyalar sekmesi.",
    image: "dosyalar", imageAlt: "Sağ panelde proje dosyaları listesi",
    steps: [
      "Sol kenar çubuğunda \"Projeler\" başlığından bir klasör seç ya da yeni klasör aç.",
      "Sağ paneldeki Dosyalar sekmesinde projenin dosyalarını gör; bir dosyaya tıklayınca içeriği açılır.",
      "Fusion'ın dokunabileceği klasörü Ayarlar → İzinler'den değiştirebilirsin.",
    ],
    settingsSection: "izinler", inOnboarding: true,
  },
  {
    id: "saglayici", group: "baslangic", title: "Model sağlayıcısı bağlama",
    summary: "Fusion'ın çalışması için en az bir yapay zekâ sağlayıcısı bağlı olmalı.",
    where: "Kurulumdaki Sağlayıcılar adımı; sonradan Ayarlar → Modeller.",
    image: "saglayici", imageAlt: "Sağlayıcı listesi: bağlı olanlar ve anahtar bekleyenler",
    steps: [
      "Listeden bir sağlayıcı seç ve \"Bağlan\" düğmesine bas.",
      "Anahtar isteyen sağlayıcıda anahtarı yapıştırıp \"Kaydet\" de; web oturumu isteyenlerde giriş sağlayıcının kendi sayfasında yapılır.",
      "Anahtar bu bilgisayarda kalır; ekranda tekrar gösterilmez.",
      "Ücretsiz çırak modeli etkinse ek bir şey yapman gerekmez.",
    ],
    settingsSection: "modeller", inOnboarding: true,
  },
  {
    id: "izin", group: "calisma", title: "İzin modları ve onay",
    summary: "Fusion'ın neyi kendi başına yapacağını sen belirlersin.",
    where: "Yazı kutusunun altındaki mod düğmesi; Ayarlar → İzinler.",
    image: "onay", imageAlt: "Fusion bir dosyayı değiştirmeden önce onay istiyor",
    steps: [
      "Kutunun altındaki mod düğmesinden ya da Shift + Tab ile modu değiştir: Otomatik, Yalnız plan, Güvenli.",
      "Güvenli modda her değiştirici işlem için bir onay penceresi çıkar; \"Bir kez izin ver\" ya da \"Reddet\" seç.",
      "Yalnız plan modunda Fusion hiçbir şeyi değiştirmez, sadece plan çıkarır.",
    ],
    settingsSection: "izinler", inOnboarding: true,
  },
  {
    id: "terminal", group: "calisma", title: "Terminal ve değişiklikler",
    summary: "Komutları ve yapılan değişiklikleri sağ panelden izle.",
    where: "Sağ panel: Dosyalar, Değişiklikler, Terminal, Önizleme sekmeleri.",
    image: "terminal", imageAlt: "Sağ panelde terminal sekmesi",
    steps: [
      "Sağ paneldeki sekme simgelerinden Terminal'i seç.",
      "Fusion'ın çalıştırdığı komutlar ve çıktıları burada görünür.",
      "Değişiklikler sekmesinde hangi dosyaların değiştiğini gör, istemediğini geri al.",
      "Önizleme sekmesi bir web sayfasını ya da görseli uygulamanın içinde açar.",
    ],
    inOnboarding: false,
  },
  {
    id: "gecmis", group: "calisma", title: "Claude ve Codex geçmişini sürdürme",
    summary: "Başka araçta kaldığın yerden Fusion'la devam et.",
    where: "Sol kenar çubuğu → Devam et.",
    image: "gecmis", imageAlt: "Önceki bir sohbetin önizlemesi ve devam et düğmesi",
    steps: [
      "Sol kenar çubuğunda \"Devam et\" altından Claude ya da Codex geçmişini aç.",
      "Bir oturum seç; içeriğini önizlemede oku.",
      "Sürdür dediğinde sohbet Fusion'da devam eder. Bulunan anahtar benzeri metinler önceden uyarılır.",
    ],
    inOnboarding: true,
  },
  {
    id: "ekip", group: "calisma", title: "Ekip (yardımcı ajanlar)",
    summary: "Büyük işlerde Fusion işi yardımcı ajanlara bölebilir.",
    where: "Sağ panel → Ajanlar sekmesi.",
    image: "ekip", imageAlt: "Ajanlar panelinde araştırmacı, tasarımcı ve görsel üretici",
    steps: [
      "Görev büyükse Fusion yardımcı ajanları kendisi başlatır; ayrıca bir şey yapman gerekmez.",
      "Sağ paneldeki Ajanlar sekmesinde kimin ne üzerinde çalıştığını canlı izle.",
      "Bir ajanın kartına tıklayınca yaptığı işlerin ayrıntısı açılır.",
    ],
    inOnboarding: false,
  },
  {
    id: "ses", group: "calisma", title: "Sesle konuşma",
    summary: "Yazmak yerine konuş, Fusion sesli yanıt versin.",
    where: "Yazı kutusundaki ses düğmesi; ayarlar Ayarlar → Ses.",
    image: "ayar-ses", imageAlt: "Ses ayarları: konuşma hızı ve ses seçimi",
    steps: [
      "Yazı kutusunun sağındaki ses düğmesine bas; macOS mikrofon ve konuşma tanıma izni ister, bir kez onayla.",
      "Konuş; Fusion seni dinler, işi yapar ve sesli yanıt verir.",
      "Ses, hız ve model seçimini Ayarlar → Ses'ten değiştir.",
    ],
    settingsSection: "ses", inOnboarding: true,
  },
  {
    id: "gorsel", group: "calisma", title: "Görsel ve video üretimi",
    summary: "Tarif et, Fusion görseli üretsin.",
    where: "En soldaki ana menü → Görsel ve video üretimi.",
    image: "gorsel", imageAlt: "Görsel üretim ekranı ve üretilen görseller",
    steps: [
      "Ana menüden \"Görsel ve video üretimi\"ni aç.",
      "Ne istediğini yaz, boyutu seç ve üret.",
      "Üretilen görseller listede toplanır; istediğini kaydedebilir ya da yeniden üretebilirsin.",
    ],
    inOnboarding: false,
  },
  {
    id: "kitaplik", group: "calisma", title: "Kitaplık ve zamanlananlar",
    summary: "Dosyalarını sakla; işleri belli saatte kendiliğinden çalıştır.",
    where: "En soldaki ana menü → Kitaplık ve Zamanlananlar.",
    image: "kitaplik", imageAlt: "Ana menüde Kitaplık seçili",
    steps: [
      "Kitaplık'ta Fusion'a göstermek istediğin dosyaları topla.",
      "Zamanlananlar'dan tekrar eden bir iş tanımla; Fusion onu o saatte çalıştırır.",
    ],
    inOnboarding: false,
  },
  {
    id: "kits", group: "baslangic", title: "Kits",
    summary: "Fusion'ın içinde açılan çalışma alanı: sayfalar, notlar ve hazır araçlar.",
    where: "En soldaki ana menü → Kits.",
    image: "kits-menu", imageAlt: "Ana menüde Kits seçili",
    steps: [
      "Ana menüden \"Kits\"i aç; ilk açılışta hazırlanması birkaç saniye sürebilir.",
      "Kits kendi içinde çalışır; bilgisayarına erişmek istediğinde Fusion sana izin sorar.",
    ],
    inOnboarding: true,
  },
  {
    id: "beceriler", group: "baglantilar", title: "Beceriler ve ajan tanımları",
    summary: "Hazır uzmanlıkları Fusion'a bağla.",
    where: "Beceriler ve Ajanlar ekranı; yazı kutusunda / komut paleti.",
    image: "beceriler", imageAlt: "Beceriler kataloğu: beceriler, ajanlar, talimatlar ve MCP",
    steps: [
      "Beceriler ekranında bilgisayarındaki becerileri, ajanları ve talimatları gör.",
      "Bir satıra tıklayınca ne yaptığını ve hangi izinleri istediğini oku.",
      "Kutuya / yazarak komut paletini açıp bir beceriyi doğrudan çağırabilirsin.",
    ],
    inOnboarding: false,
  },
  {
    id: "baglayicilar", group: "baglantilar", title: "Bağlayıcılar (MCP)",
    summary: "Fusion'ı dış servislere ve araçlara bağla.",
    where: "Bağlayıcılar ekranı (MCP bağlantıları).",
    image: "baglayicilar", imageAlt: "Bağlayıcılar kataloğu",
    steps: [
      "Bağlayıcılar ekranında bir servisi seç.",
      "Kurulum formundaki adımları izle; gerekirse resmî sayfayı açan bağlantıyı kullan.",
      "Bağlanan servisin araçları Fusion'ın kullanımına açılır; bağlantıyı istediğinde kaldırabilirsin.",
    ],
    inOnboarding: false,
  },
  {
    id: "chrome", group: "baglantilar", title: "Chrome eklentisi",
    summary: "Fusion açık Chrome sekmene, senin verdiğin izinle bakabilsin.",
    where: "Ayarlar → Tarayıcı.",
    image: "ayar-tarayici", imageAlt: "Tarayıcı ayarları: Chrome eklentisi kurulum durumu ve Eklentiyi kur düğmesi",
    steps: [
      "Ayarlar → Tarayıcı'yı aç ve \"Eklentiyi kur\"a bas. Tek tıklama yeter.",
      "macOS ilk seferde Erişilebilirlik izni ister: Sistem Ayarları → Gizlilik ve Güvenlik → Erişilebilirlik'te Fusion'ı aç. Bu izin bir kez verilir.",
      "Chrome'da çıkan tek onayı kabul et; gerisini Fusion yapar.",
      "\"Chrome'a yüklendi\" ve \"Fusion ile eşleşti\" satırları Tamam olunca kurulum bitmiştir.",
      "Kendi Chrome oturumlarına ve çerezlerine dokunulmaz.",
    ],
    settingsSection: "tarayici", inOnboarding: true,
  },
  {
    id: "uzak", group: "baglantilar", title: "Telefondan uzaktan erişim (Tailscale)",
    summary: "Bilgisayarındaki Fusion'ı telefonundan, yalnız senin cihazlarına açık şekilde kullan.",
    where: "Ayarlar → Uzaktan Erişim.",
    image: "ayar-uzak", imageAlt: "Uzaktan erişim ayarları ve Tailscale kurulum rehberi",
    steps: [
      "Tailscale'i bilgisayara ve telefona kur; ikisinde de aynı hesapla giriş yap (ücretsiz plan yeter).",
      "Ayarlar → Uzaktan Erişim'de erişim türü olarak \"Özel tünel (Tailscale)\"ı seç.",
      "\"Dinlemeyi başlat\"a bas; ekrandaki komutu terminalde bir kez çalıştır.",
      "Komutun yazdığı https adresini telefonda aç ve \"Ana Ekrana Ekle\"yi seç.",
      "Eşleştirme kodunu oluştur, telefona gir; riskli işlemleri bu bilgisayarda onayla.",
    ],
    settingsSection: "uzak", inOnboarding: true,
  },
  {
    id: "kisisel", group: "kisisel", title: "Hafıza ve talimatlar",
    summary: "Fusion'a nasıl çalışmasını istediğini bir kez söyle.",
    where: "Ayarlar → Kişiselleştirme.",
    image: "ayar-kisisel", imageAlt: "Kişiselleştirme: bellek ve özel talimatlar",
    steps: [
      "Ayarlar → Kişiselleştirme'yi aç.",
      "Özel talimatlar alanına tercihlerini yaz (ör. \"Türkçe yaz, değişiklikten sonra testleri çalıştır\") ve kaydet.",
      "Bellek bölümünde Fusion'ın senin hakkında hatırladıklarını görebilir ve silebilirsin.",
    ],
    settingsSection: "kisisellestirme", inOnboarding: false,
  },
  {
    id: "genel", group: "kisisel", title: "Tema ve genel ayarlar",
    summary: "Açık ya da koyu görünüm, geçmiş listesi.",
    where: "Ayarlar → Genel.",
    image: "ayar-genel", imageAlt: "Genel ayarlar: tema seçimi",
    steps: [
      "Ayarlar'ı aç; en üstteki arama kutusu bir ayarı adıyla bulur.",
      "Genel bölümünden temayı Açık, Koyu ya da Sistem olarak seç.",
    ],
    settingsSection: "genel", inOnboarding: false,
  },
  {
    id: "guncelleme", group: "kisisel", title: "Güncellemeler",
    summary: "Yeni sürümü gör ve kur.",
    where: "Ayarlar → Güncellemeler.",
    image: "ayar-guncelleme", imageAlt: "Güncellemeler paneli",
    steps: [
      "Ayarlar → Güncellemeler'i aç.",
      "Yeni sürüm varsa panelden indir ve kur; Fusion yeniden açılır.",
    ],
    settingsSection: "guncellemeler", inOnboarding: false,
  },
];

export function guideImageUrl(topic: Pick<GuideTopic, "image">): string {
  return `/guide/${topic.image}.webp`;
}

export const ONBOARDING_TOPICS: readonly GuideTopic[] = GUIDE_TOPICS.filter((topic) => topic.inOnboarding);
