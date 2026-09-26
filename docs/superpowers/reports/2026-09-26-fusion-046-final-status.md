# Fusion 0.4.6 durum kaydı — 26 Eylül 2026

## Kurulum ve veri

- `/Applications/Fusion.app` sürümü 0.4.6'dır. Uygulama ve DMG yerel olarak oluşturuldu; kurulu uygulamanın ad-hoc imzası `codesign --verify --deep --strict` ile doğrulandı.
- Önceki 0.4.5 uygulaması `~/Library/Application Support/Fusion/backups/` altında saklandı. Kurulum öncesi kullanıcı verisi ve yapılandırma aynı dizindeki `0.4.6-preinstall-2026-09-26` klasörüne kopyalandı. Mevcut veri dizinleri değiştirilmedi.
- Kurulu uygulama açıldığında mevcut sohbetler, proje ve hesap görüldü. Koyu sohbet, hesap, ayarlar, model seçici, dar pencere ve ses mini paneli görsel olarak incelendi. Ses panelindeki Fusion botu ve üç nokta menüsünün açılıp kapanması gözlendi.
- Kurulu uygulamadaki Chrome eklentisi `panel.js` ve `panel.css` dosyaları kaynakla birebir SHA-256 eşleşiyor.

## Uygulananlar ve doğrulama

- Sohbet satırında sağ kenara hizalanan, üzerine gelince görünen tek üç nokta menüsü; sabitleme, projeye taşıma ve silme komutları bu menüde. Menü kaydırma alanının dışında açılıyor.
- Koyu yerel pencere üst çerçevesi; dar ve geniş görünümler için metin, hesap ve kontrol renkleri.
- 360×112 taşınabilir, her zaman üstte ses paneli; Fusion botu, üç nokta menüsü ve hazır Türkçe selamlaşma yanıtları.
- Chrome paneli Fusion renkleri ve alanlarıyla güncellendi; çalışan görev için Durdur eklendi. Gerçek Chrome'da yerel eşleştirme, test sekmesine izin ve sayfayı okuma başarılı oldu. Görev iptali panelde canlı olarak doğrulandı.
- Bağlam göstergesi modelin doğrulanmamış token penceresini kesin yüzde gibi göstermiyor; ölçtüğü karakter özetleme eşiğini açıkça belirtiyor.
- Önceki turda React 723/723, Rust 74 test (3 ignored), ilgili Python testleri ve üretim build'i geçti. Bu turda Chrome köprüsü 6/6, Ruff ve ilgili mypy geçti. Tam Python paketi yeniden başlatıldı; sonucu tamamlanmadan başarılı sayılmamalı.

## Kalan doğrulama sınırları

- Chrome uzantısında gerçek `snapshot`, `type`, `click`, `screenshot`, `navigate` komutlarının tamamı tek canlı turda henüz geçmedi. İlk bağlantı ve sayfa okuma geçti; canlı test yeniden başlatmalar nedeniyle yarıda kaldı. Modelin kendi başına sayfayı yönetmesi de tam doğrulanmadı.
- Masaüstü erişilebilirlik, fare ve klavye araçlarının gerçek bir üçüncü taraf uygulamada uçtan uca turu tamamlanmadı. Kaynak testleri geçti.
- Mikrofon donanımı testinde giriş düzeyi çoğunlukla sıfır geldi; konuşma tanıma ve sesli hazır yanıtın gerçek mikrofonla turu doğrulanamadı.
- Tam Claude in Chrome veya ChatGPT/Codex özellik eşliği iddia edilmiyor. Kullanıcı arayüzü ve doğrulanan işlevler 0.4.6 kapsamındadır.
- Makine 05:16, 05:24 ve 05:39 civarında macOS `WindowServer` watchdog panikleriyle yeniden başladı. Günlükte `no successful checkins from WindowServer ... in 120 seconds` yazıyor. Bu kayıt Fusion'ı tek başına neden olarak göstermiyor. Canlı GUI testleri tekrar tekrar kesildi.

## Yayın kararı

Yerel 0.4.6 paketi kurulu ve geri dönüş yedeği mevcut. Yukarıdaki canlı sınırlar kapanmadan genel sürüm olarak yayımlanmış sayılmamalıdır.
