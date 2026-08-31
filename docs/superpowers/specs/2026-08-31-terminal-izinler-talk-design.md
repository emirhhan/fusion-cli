# Gerçek Terminal, İzin Merkezi ve Fusion Talk Tasarımı

## Amaç

Fusion masaüstü uygulamasının terminalini gerçek etkileşimli bir kabuğa dönüştürmek, macOS izinlerini özellik kullanıldığı ana ertelemek ve Fusion Talk penceresini güvenilir konuşma tanıma ile yerel bir yardımcı pencere gibi çalıştırmak.

## Ürün kararları

- Terminal paneli bir komut çalıştırıcı taklidi olmayacak; PTY tabanlı gerçek bir terminal olacak.
- Arka plan görevlerini yöneten mevcut `surec.*` altyapısı korunacak. PTY terminali bundan ayrı bir masaüstü kabiliyeti olacak.
- Uygulama açılışta mikrofon, konuşma tanıma, geniş disk erişimi veya Keychain istemeyecek.
- macOS sistem izinleri otomatik onaylanamaz. Fusion yalnız gerekli anda tek bir açıklama ekranı gösterecek, ardından işletim sistemi penceresini açacak.
- Full Disk Access varsayılan gereksinim olmayacak. Kullanıcı çalışma klasörünü sistem klasör seçicisiyle seçer.
- Fusion işlem onayları `auto` kipinde güvenli işlemlerde kesintisiz ilerler; yıkıcı işlemler yine açık onay ister.
- `%10 saydamlık`, pencerenin `%90 opak` olması anlamına gelir.
- Talk penceresi köşesiz ve gölgesiz olacak; şeffaf webview üzerinde ikinci bir iç çerçeve görünmeyecek.
- Kırmızı düğme Talk'ı kapatıp ana pencereyi geri getirir. Sarı düğme Talk'ı Dock'a küçültür. Yeşil düğme normal ve mini görünüm arasında geçiş yapar.
- Başlığın boş alanı pencereyi sürükler; düğmeler sürükleme alanı değildir.
- Mini görünümde avatar, durum, mikrofon, üç pencere düğmesi ve normal görünüme dönme olanağı kalır.
- Tanınan son metin yalnız bir kez açık olan aynı sohbete gönderilir. Belirsiz sesli onay hiçbir zaman otomatik kabul edilmez.
- Her görsel teslimat normal/mini ve açık/koyu ekran görüntüleriyle kullanıcıya gösterilir.

## 1. Gerçek terminal mimarisi

React tarafında `@xterm/xterm` ve `@xterm/addon-fit` kullanılır. Tauri/Rust tarafında `portable-pty` bir PTY açar ve kullanıcının varsayılan kabuğunu çalışma klasöründe başlatır. Her sekmenin bağımsız PTY kimliği, yazıcısı ve okuyucu iş parçacığı bulunur.

Komut sınırı:

- `terminal_ac(cwd, cols, rows) -> TerminalSnapshot`
- `terminal_yaz(terminal_id, data)`
- `terminal_boyutla(terminal_id, cols, rows)`
- `terminal_kapat(terminal_id)`
- Rust olayı: `terminal://cikti`, yükü `{ terminal_id, data }`
- Rust olayı: `terminal://kapandi`, yükü `{ terminal_id, exit_code }`

Çıktı ANSI kodları korunarak xterm'e yazılır. Klavye girdisi, `Ctrl+C`, ok tuşları, sekme tamamlama ve TUI programları PTY'ye ham olarak iletilir. Terminal kapatılırken çocuk süreç ve okuyucu temizlenir. Ana pencere kapanırken tüm PTY'ler kapatılır. Mevcut `ProcessManager`, test/dev-server gibi ajan süreçlerinde değişmeden kalır.

## 2. İzin mimarisi

`PermissionCenter` yalnız gözlemlenebilen ürün durumunu tutar: `unknown`, `granted`, `denied`, `restricted`. Açılış bu durumları sorgulayabilir ancak izin istemez.

- Klasör: kullanıcı “Klasör aç” dediğinde yerel klasör seçici açılır. Fusion yalnız seçilen klasörde çalışır.
- Mikrofon ve konuşma tanıma: Talk ilk kez başlatıldığında tek Fusion açıklama sayfası gösterilir. Kullanıcı devam edince macOS'un iki zorunlu sistem penceresi sırayla gelebilir.
- Keychain: yalnız sağlayıcı anahtarı kaydedilirken erişilir.
- Reddedilen izin: ilgili özellik hata vermek yerine izin merkezinde açıklama ve “Sistem Ayarlarını Aç” eylemi gösterir.
- Geniş erişim: isteğe bağlı gelişmiş yardım olarak anlatılır; otomatik olarak Full Disk Access penceresine yönlendirilmez.

Uygulama içi araç onayı TCC'den ayrı tutulur. `auto`, `plan`, `security` kipleri korunur; oturumluk izin güvenli/yıkıcı olmayan işlemlerde kullanılabilir.

## 3. Talk penceresi ve konuşma yaşam döngüsü

Tauri penceresi çerçevesiz kalır fakat web içeriği tüm dikdörtgeni `%90` opak arka planla doldurur. Köşe yarıçapı ve pencere/panel gölgeleri sıfırlanır. Pencere düğmeleri gerçek komutlara bağlanır; sarı düğme için ayrı `ses_penceresi_simge_durumu` komutu eklenir.

Konuşma oturumu açık durum makinesiyle yönetilir:

1. Kullanıcı mikrofonu seçer.
2. İzin durumu doğrulanır; gerekirse ilk kullanım açıklaması gösterilir.
3. Dinleyiciler kurulmuş halde yeni yardımcı süreç başlatılır.
4. Kısmi metin ekranda güncellenir.
5. Son metin bir revizyon kimliğiyle bir kez sohbete gönderilir.
6. Yardımcı beklenmedik kapanırsa sessizce “idle” sayılmaz; kullanıcıya neden ve yeniden deneme gösterilir.
7. Kullanıcı durdurduğunda kapanış beklenen kapanış olarak işaretlenir.
8. Asistan konuşurken mikrofon durur; otomatik dinleme açıksa yanıt bitince temiz bir oturum başlar.

Mini ve normal görünümler aynı makineyi ve mikrofon eylemini kullanır. Görünüm değiştirmek tanıma sürecini yeniden başlatmaz.

## Güvenlik ve gizlilik

- Terminal yalnız kullanıcının açıkça seçtiği çalışma klasöründe açılır.
- Terminal çıktıları sağlayıcıya kendiliğinden gönderilmez.
- Mikrofon yalnız görünür dinleme durumunda aktiftir; durum ve hata arayüzde görünürdür.
- Sistem izinleri veya yıkıcı Fusion araçları otomatik tıklanmaz.
- `.env` dahil proje dosyaları terminal tarafından normal dosya sistemi yetkileriyle erişilebilir; uygulama bunları telemetriye veya dış sisteme kendiliğinden taşımaz.

## Kabul ölçütleri

- `vim`, `python`, `top` benzeri etkileşimli programlar terminalde çalışır; `Ctrl+C` süreci keser ve terminal oturumu yaşamaya devam eder.
- Açılışta macOS izin penceresi görünmez.
- Talk ilk kullanımında anlaşılır açıklama ve gerekli sistem izinleri dışında tekrar eden sorular yoktur.
- Normal ve mini Talk'ta mikrofon çalışır; konuşulan cümle aynı sohbete bir kez yazılır.
- Trafik ışıkları belirtilen gerçek davranışları uygular ve başlık sürüklenebilir.
- Talk penceresinde yuvarlak iç panel, dış dikdörtgen izi veya gölge yoktur; opaklık `%90`dır.
- React, Rust, Python ve görsel test kapıları geçer; paketli macOS uygulamasında gerçek mikrofon duman testi yapılır.
