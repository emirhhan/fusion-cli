# Fusion 0.4.6 durum kaydı — 26 Eylül 2026

## Kurulum ve veri

- `/Applications/Fusion.app` sürümü 0.4.6'dır. Uygulama ve DMG yerel olarak oluşturuldu; kurulu uygulamanın ad-hoc imzası `codesign --verify --deep --strict` ile doğrulandı.
- Önceki 0.4.5 uygulaması `~/Library/Application Support/Fusion/backups/` altında saklandı. Kurulum öncesi kullanıcı verisi ve yapılandırma aynı dizindeki `0.4.6-preinstall-2026-09-26` klasörüne kopyalandı. Mevcut veri dizinleri değiştirilmedi.
- Kurulu uygulama açıldığında mevcut sohbetler, proje ve hesap görüldü. Koyu sohbet, hesap, ayarlar, model seçici, dar pencere ve ses mini paneli görsel olarak incelendi. Ses panelindeki Fusion botu ve üç nokta menüsünün açılıp kapanması gözlendi.
- Kurulu uygulamadaki Chrome eklentisi `panel.js` ve `panel.css` dosyaları kaynakla birebir SHA-256 eşleşiyor.
- Ekran görüntüsü izni için güncellenen paket tekrar kuruldu. Önceki 0.4.6 uygulaması `Fusion-0.4.6-before-capture-permission.app` adıyla yedeklendi; kurulumdan sonra mevcut sohbetler yeniden göründü ve imza doğrulaması geçti.

## Uygulananlar ve doğrulama

- Sohbet satırında sağ kenara hizalanan, üzerine gelince görünen tek üç nokta menüsü; sabitleme, projeye taşıma ve silme komutları bu menüde. Menü kaydırma alanının dışında açılıyor.
- Koyu yerel pencere üst çerçevesi; dar ve geniş görünümler için metin, hesap ve kontrol renkleri.
- 360×112 taşınabilir, her zaman üstte ses paneli; Fusion botu, üç nokta menüsü ve hazır Türkçe selamlaşma yanıtları.
- Chrome paneli Fusion renkleri ve alanlarıyla güncellendi; çalışan görev için Durdur eklendi. Gerçek Chrome'da yerel eşleştirme, test sekmesine izin, sayfayı okuma, metin yazma, düğmeye basma ve aynı siteye gezinme başarılı oldu. Görev iptali panelde canlı olarak doğrulandı.
- Chrome'un `captureVisibleTab` çağrısı gerçek testte `activeTab` izniyle reddedildi. Kullanıcı eylemiyle açılan panel ve arka plan çağrısı da denendi; aynı hata tekrarlandı. Bunun için açık açıklamalı, isteğe bağlı `<all_urls>` izin düğmesi eklendi. Kullanıcı izni verilmeden bu geniş erişim etkinleşmez; ekran görüntüsü geçişi henüz doğrulanmadı.
- Fusion masaüstü araçları gerçek Chrome test penceresinde uçtan uca çalıştı: `desktop_window_focus` Chrome'u öne aldı, `desktop_type` seçili alana `Fusion desktop test` yazdı, `desktop_click` yerel sayfadaki Uygula düğmesini tıkladı ve sayfa aynı metni gösterdi. `desktop_screenshot` gerçek 2880×1800 masaüstü PNG'si üretti; görsel incelendi. Pencere listesi ve erişilebilirlik okuması da gerçek uygulamada çalıştı.
- Bağlam göstergesi modelin doğrulanmamış token penceresini kesin yüzde gibi göstermiyor; ölçtüğü karakter özetleme eşiğini açıkça belirtiyor.
- Son React koşusu 725/725 testi 96 dosyada geçirdi. Tam Python paketi 360 dosya ve 4.455 test üzerinden dört kalıcı parçaya bölündü; dört parçanın çıkış kodu 0. Önceki turda Rust 74 test (3 ignored) geçti. Ruff lint, 333 kaynak dosyada mypy, değişen Python dosyalarında Ruff format ve üretim web build'i geçti. Bütün depo için `ruff format --check .` eski 72 dosyanın biçiminden dolayı geçmiyor; bu değişikliklerdeki üç Python dosyası biçim denetiminden geçti.

## Kalan doğrulama sınırları

- Chrome uzantısında gerçek `snapshot`, `type`, `click`, `navigate` aynı canlı turda geçti. `screenshot` için Chrome'un geniş isteğe bağlı izni ve ardından canlı doğrulama gerekiyor. Modelin kendi başına sayfayı yönetmesi de tam doğrulanmadı.
- Masaüstü araçları yerel Chrome testinde uçtan uca doğrulandı. Farklı uygulamalar ve modelin kendi başına çok adımlı masaüstü yönetimi için aynı düzeyde canlı doğrulama yapılmadı.
- Mikrofon donanımı testinde giriş düzeyi çoğunlukla sıfır geldi; konuşma tanıma ve sesli hazır yanıtın gerçek mikrofonla turu doğrulanamadı.
- Tam Claude in Chrome veya ChatGPT/Codex özellik eşliği iddia edilmiyor. Kullanıcı arayüzü ve doğrulanan işlevler 0.4.6 kapsamındadır.
- Makine 05:16, 05:24 ve 05:39 civarında macOS `WindowServer` watchdog panikleriyle yeniden başladı. Günlükte `no successful checkins from WindowServer ... in 120 seconds` yazıyor. Bu kayıt Fusion'ı tek başına neden olarak göstermiyor. Canlı GUI testleri tekrar tekrar kesildi.

## Yayın kararı

Yerel 0.4.6 paketi kurulu ve geri dönüş yedeği mevcut. Yukarıdaki canlı sınırlar kapanmadan genel sürüm olarak yayımlanmış sayılmamalıdır.
