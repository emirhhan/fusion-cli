# Fusion macOS Oturum ve Geçmiş Sonuç Raporu

Tarih: 29 Ağustos 2026

## Teslim edilen ürün davranışı

- Her canlı konuşma ayrı paketli `fusion app` alt sürecinde çalışır. Rust `SessionManager` süreç kimliği, proje kökü, PID, stdin sahipliği, kapanış nedeni ve uygulama kapanışındaki toplu temizliği yönetir.
- Eski `cekirdek_baslat` / `cekirdege_yaz` komutları varsayılan oturuma delege edildi; önceki React sözleşmesi kırılmadı.
- React tarafında her konuşmanın ayrı `ProtocolClient`, mesaj, çalışma, onay ve hata durumu vardır. Bir süreç kapanınca yalnız ilgili konuşma etkilenir.
- Sidebar yalnız çekirdeğin keşfettiği Claude/Codex/Hermes kaynaklarını gösterir. Kaynak → sayfalı liste → sayfalı önizleme → devralma akışı klavye ve küçük pencere desteğiyle tamamlandı.
- `gecmis.surdur` isteği yeni konuşmanın kendi çekirdeğinde çalışır. Böylece devralma künyesi tam bir sonraki tura gider; eski konuşmanın sürecine sızmaz.
- Devam oturumu `[claude]`, `[codex]` veya `[hermes]` etiketi taşır. Dış geçmiş salt okunur kalır.
- Hassas olabilecek değerlerin kendisi UI'a veya localStorage'a yazılmaz. Yalnız sayı, sakin bir yenileme önerisiyle gösterilir.
- Kalıcılık kaydı sürümlüdür ve yalnız `id`, `title`, `source`, `root`, `updatedAt` alanlarını içerir. Mesajlar, sorular, PID, hata ve hassas içerik saklanmaz.

## Arayüz kalite geçişi

Kaynak seçici üç bölmeli profesyonel bir masaüstü yüzeyi olarak eklendi. Kontroller en az 40–44 px hedef alanı, açık hover/active/focus durumları, sınırlı CSS geçişleri, tabular sayaçlar, dengeli başlık sarımı, koyu tema ve focus trap kullanır. `transition: all` ve `will-change: all` kullanılmadı.

Görsel kapı şu durumları kapsar:

- kaynak seçimi;
- dolu önizleme ve sayfalama;
- hassas değer bildirimi (koyu tema);
- boş kaynak;
- hata;
- uzun başlık/uzun yanıt ve 920 px pencere;
- mevcut boş, konuşma, responsive, onay ve klavye odağı görünümleri.

## Doğrulama kanıtı

### Python

- `make check`
- Ruff format/check: temiz
- mypy: 238 kaynak dosyası, hata yok
- pytest: 2.520 geçti
- deadlock/sözleşme kapısı: 105 geçti

### React / Rust

- `make app-check`
- npm audit: 0 açık
- Vitest: 24 dosyada 94 test geçti
- TypeScript + Vite üretim derlemesi: geçti
- Cargo fmt + Clippy `-D warnings`: geçti
- Rust: 34 test geçti

Çoklu oturum oluşturma, satırların doğru istemciye yönlendirilmesi, konuşma geçişi, kontrollü kapanış, tek süreç çöküşü ve eski okuyucu/PID yarışı Rust + React taşıma testlerinde doğrulandı.

### Görsel regresyon

- `make app-visual`
- Playwright: 13/13 geçti
- Yeni history akışı: 6/6 geçti
- Kritik açık/koyu/uzun içerik görüntüleri ayrıca gözle incelendi.

### Paket ve temiz kullanıcı smoke

- `make app-package`
- PyInstaller runtime sağlık ve stdio app protokolü: geçti
- Tauri release `.app` + `.dmg`: üretildi
- Temiz HOME ilk açılışı: runtime kuruldu ve app protokolü geçti
- Temiz HOME ikinci açılışı: runtime yeniden kurulmadan app protokolü geçti
- Hedef: `aarch64-apple-darwin`
- Runtime sürümü: `0.3.0a1`
- `Fusion.app`: yaklaşık 166 MB
- `Fusion_0.3.0-alpha.1_aarch64.dmg`: yaklaşık 160 MB

## Dağıtım sınırı

Kullanıcının Apple Developer hesabı yok ve açılmayacak. Bu nedenle paket notarize edilmedi ve Developer ID ile imzalanmadı. `.dmg` yerel test/dağıtım için hazırdır; başka bir Mac'te ilk açılışta Gatekeeper bağlam menüsüyle **Aç** veya Sistem Ayarları → Gizlilik ve Güvenlik onayı isteyebilir. Bu, uygulama/runtime test hatası değildir; Apple'ın imzasız dağıtım kısıtıdır.
