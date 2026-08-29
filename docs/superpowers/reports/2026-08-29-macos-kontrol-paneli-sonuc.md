# Fusion macOS Kontrol Paneli, Ayarlar ve Gateway Güvenliği — F Aşaması Sonuç

## Teslim edilenler

### Native kontrol paneli

- Panel gerçek Fusion durumunu protokolden okur: etkin ajan/hakem/ad modelleri, izin
  kapsamı, MCP sunucuları, şifreli sağlayıcı anahtarları ve yerel gateway durumu.
- Sağlayıcı satırları yalnız METADATA taşır (`id`, `ad`, `ortam`, `kurulu`); anahtar
  değeri bu sınırı hiçbir yanıtta ve hiçbir logda geçmez.
- Yerel gateway panelden başlatılıp durdurulabilir.
- Sol navigasyondaki "Kontrol Paneli" ve "Ayarlar" bu ekrana bağlıdır.

### Gateway sertleştirme

- `Origin` denetimine ek olarak `Host` denetimi eklendi: yerel olmayan Host başlığı
  `421` ile reddedilir. Bu, DNS-rebinding saldırısını kapatır — tarayıcı yabancı bir
  isimle 127.0.0.1'e bağlansa bile istek gateway'e giremez.
- HTTP/1.1'de `Host` zorunlu olduğu için eksik başlık da şüpheli sayılır ve reddedilir.
- Dış ağa açma (`0.0.0.0`) çalışmaya devam eder ama açık uyarı üretir; korumalar kapanmaz.

### Eşzamanlı yapılandırma yazımı

- CLI, uygulama ve panel aynı anda farklı ayarlar kaydettiğinde birinin değişikliğini
  sessizce silen yarış, süreçler-arası dosya kilidiyle kapatıldı. İki gerçek süreçle
  sınandı.

### İlk açılış

- Altı adımlı onboarding uygulamaya bağlandı: çalışma zamanı, Claude/Codex/Hermes
  keşfi, sağlayıcı hazırlığı, proje seçimi ve izinlerin sade anlatımı.

## Doğrulama

- Kök kapısı (`make check`): Ruff temiz, mypy 243 kaynak dosyasında temiz,
  2.552 Python testi ve 105 kilitlenme/sözleşme testi geçti, exit 0.
- Masaüstü kapısı (`make app-check`): 30 test dosyası / 119 React testi, TypeScript
  üretim derlemesi, Clippy ve 34 Rust testi — hepsi geçti, exit 0.
- Paketli `.app` ve imzasız DMG üretildi; temiz HOME'da gerçek runtime ile dosya
  okuma, süreç başlatma/durdurma, önizleme, beceri kataloğu ve kontrol protokolü
  çalıştı.

## Açık bulgu (H aşamasına taşındı)

`_foreign_host` içinde `Host: local` başlığı, ASGI birim testlerinin sentetik yerel
adı olarak koşulsuz kabul ediliyor. Üretimde de kabul edildiği için, "local" adını
127.0.0.1'e çözen bir ağda denetim atlanabilir. Tarayıcı `Host`'u URL'den kurduğu
için sömürüsü dar, ama test kolaylığının üretim yoluna sızması doğru değil. H
aşamasındaki güvenlik denetiminde kapatılacak.
