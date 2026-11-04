# İşlem paneli ve kırmızı kapatma düğmesi

Kullanıcının 4 Kasım tarihli ayrıntılı isteği uygulanır. Mevcut React/Tauri mimarisi korunur.

## İşlem paneli
Her araç/iş adımı açılabilir bir satırdır. Bir kullanıcı turunda bir veya iki işlem varsa satırlar normal akışta alt alta görünür. Daha fazla işlem varsa en fazla iki kompakt satır gösterilir; bunlardan birini açmak, seçilen satır dahil bütün işlemleri sohbet içindeki sınırlı yükseklikli bir panele taşır. Panelin kendi dikey kaydırması vardır; tekerlek ve sınırdaki kaydırma ana sohbeti hareket ettirmez. Her iç satır ayrıca açılıp mevcut kod/komut/çıktı/diff ayrıntılarını gösterir. Panel açıkken yeni işlemler eklenebilir; açılan ayrıntı kaybolmaz. Sohbet değişince panel durumu başka sohbete taşınmaz. Asistan açıklamaları ve kullanıcı onay/soru kartları gizlenmez.

Yaklaşım: Mevcut ToolTrail/StepDetail sunumu tekrar kullanılır; sınır tek olay bloğunda değil, Conversation kullanıcı turu/workgroup seviyesinde uygulanır. Normal görünümde eski tüm-işleri-kapatan dış details iki satırı gizlemez. Özet ve ayrıntılı görünümün açıkça seçilmiş amaçları korunur. Ayrı kayan uygulama penceresi yerine sohbet içi panel seçildi: kullanıcının kendi içinde kayan pencere davranışını odak ve pencere yönetimi eklemeden sağlar.

## Kırmızı düğme
Ana pencerenin yerel kırmızı kapatma düğmesine basmak, JavaScript onay kutusunu beklemeden tam uygulama kapanışını başlatır. Pencere hemen gizlenir; mevcut uygulama temizliği arka planda ve mevcut zaman sınırıyla tamamlanır. Tekrarlanan kapatma ikinci temizlik işi başlatmaz. Donmuş veya henüz hazır olmayan web görünümü kapanışı engelleyemez. Konuşma/ayrık sohbet pencerelerinin mevcut yerel kapanış kapsamları korunur. Yerel macOS düğmesi kullanılır; sahte HTML düğme eklenmez.

## Doğrulama
Bir/iki/çok işlem, akış sırasında üçüncü işlem, seçilen ayrıntı, sohbet değişimi, klavye/erişilebilirlik ve gerçek tarayıcıda iç kaydırma testleri yapılır. Rust tarafında yerel ana pencere kapanış rotası, tek seferlik temizlik ve diğer pencere kapsamları test edilir. Kod incelemeleri, paket derlemesi ve kurulu uygulamada gerçek kırmızı düğme kabulü tamamlanır.
