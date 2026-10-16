# Fusion profesyonel devam planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion'ın gerçek kullanıcı görevlerini çalışır teslimat ve bağımsız doğrulama ile tamamlaması.

**Architecture:** Mevcut Python agent döngüsü, ücretsiz sağlayıcılar, Tauri uygulaması ve Kits korunur. Yeni bir motor kurulmaz; ölçümlerdeki kör noktalar kapatılır, sonra gerçek koşularla ürün davranışı değerlendirilir.

**Tech Stack:** Python, pytest, Playwright, React/Tauri, TypeScript.

**Spec:** Kullanıcının 12 Ekim devam talimatı; `../reports/2026-10-12-devralma.md`; kardeş depo `fusion-kabul/DEVIR-2026-10-09.md`.

## Global Constraints

- Mevcut `ajan-ekibi` dalında çalış; push ve yeni dal yok.
- Deponun `.env` dosyasını okuma; anahtarları rapora taşıma.
- Genel düzeltme yap; sneaksup'a özel seçici veya başarı ayrıcalığı ekleme.
- Tam pytest ve kabul koşusunu aynı anda çalıştırma.
- Her faz sonunda Ruff, mypy ve pytest; kapı geçmeden commit yok.
- Fazlar için önceki kalıcı onay geçerli; yalnız kullanıcı gerektiren gerçek engelde soru sor.

## Review Focus

- Aynı sayıda yanlış menü açılması başarı sayılmamalı.
- Doğru menü adı altında yanlış içerik açılması yakalanmalı.
- Kaynakta panel yoksa kopyada panel zorunlu olmamalı.
- Gizli ata içindeki bağlantılar görünür içerik sayılmamalı.
- Kaynak ölçülemiyorsa başarılı ölçüm gibi raporlanmamalı.

## Faz 1: Menü kabulünün yanlış başarılarını kapat

**Files:** `evals/kabul/areas/site_clone_menu.py` (yeni), `site_clone_probe.py`, `tests/test_kabul_site_menu.py` (yeni), `tests/test_kabul_core.py`.

**Interfaces:** `MenuPanel(label: str, links: tuple[str, ...])`; `menu_panels_opened(page: Page) -> tuple[MenuPanel, ...]`; `menu_check(clone: tuple[MenuPanel, ...], source: tuple[MenuPanel, ...] | None) -> Check`.

- [x] Önce aynı panel sayısına rağmen yanlış etiket/içerik, kapalı panel ve ölçülmeyen kaynak testlerini yaz; kırmızı sonucu gör.
- [x] Sayı yerine tetikleyici etiketi ve yeni görünür bağlantı metinlerini ölç. Görünürlükte ataları ve görünüm kesişimini dikkate al. Mevcut bekleme sürelerini koru.
- [x] Kopya ve kaynakta aynı ölçümü kullan; eksik etiket/içeriği raporla.
- [x] Gerçek Chromium'da yerel HTML ile açık, bozuk ve gizli panel senaryolarını doğrula.
- [ ] İlgili testler, Ruff, mypy, tam pytest; bağımsız kod incelemesi; sonra commit.

## Faz 2: Davranış kapsamını tamamla

- [ ] Önce menü kanıtını ürün döngüsüne bağla: kaynak yakalamada ölç, `start_preview` içinde kopyayı karşılaştır, açık bulguyu `site_verify` kapanışına taşı. Kopya temaların tasarım farkı muafiyeti işlev kusurunu gizlememeli.
- [ ] Menü veri tipi/karşılaştırmasını `core`'da, görünürlük betiğini ortak araç kaynağında tut; kabul ve ürün aynı kurala dayansın. Kaynağı her önizlemede yeniden açmak yerine yakalamadaki referansı sakla.
- [ ] Sekme içerik değişimini ve kaydırıcı hareketini kaynakla karşılaştıran ölçüm tasarla; mevcut `site_clicks` yakalama mantığıyla kanıtları ilişkilendir.
- [ ] Ürün sayfasında galeri, beden seçimi, fiyat ve sepete ekleme davranışını denetle; WooCommerce şablonundaki eksikleri önce kırmızı testle göster.
- [ ] Kaynak ve kopya aynı görünümde ölçülsün; ölçülemeyenleri başarısız ürün diye cezalandırma.

## Faz 3: Gerçek kalite koşuları

- [ ] Site kopyası, oyun ve Remotion'ı sırayla yeniden üret; rapor yanında ekran görüntülerini incele.
- [ ] Kaynak değişikliği, model/sağlayıcı arızası, ürün kusuru ve denetçi kusurunu kanıtla ayır.
- [ ] Kabulü geçmeyen teslimatı completed sayan yolları kapat; tek örneğe özel istem ekleme.

## Faz 4: Günlük ve gelişmiş iş matrisi

- [ ] Mevcut `kendini_gelistirme`, `tarayici` kabul alanları ve `evals/suite/production.yaml` önce kullanılsın; aynı işi yapan ikinci ölçüm düzeneği kurulmasın.
- [ ] Kod değiştirme/test düzeltme, araştırma ve belge işleri, MCP ile güvenli okuma, Fusion Browser görevleri için tekrar edilebilir görevler belirle.
- [ ] Ücretsiz sağlayıcı başarısızlığı ve yedek model geçişini gerçek görevde ölç.
- [ ] Terminal ve masaüstü/Kits'in aynı araç ve doğrulama yeteneklerine eriştiğini karşılaştır.

## Faz 5: Kullanıma teslim

- [ ] Eksik web/MCP girişlerini yalnız gerektiğinde kullanıcıyla tamamla; geçmiş ders belleğini varmış gibi gösterme.
- [ ] Sesli konuşmayı kullanıcının mikrofon denemesiyle doğrula.
- [ ] App ve Kits kalite kapıları, paketleme ve kurulu uygulama doğrulaması.
- [ ] Yetkinlik raporunda yalnız ölçülmüş sonuçları yaz; Claude/Codex eşdeğerliği ancak aynı görevlerde karşılaştırmalı kanıt varsa söylenir.

## Faz 2'nin ilk teslimatı: ürünün menü işlev kapısı

**Amaç:** Kaynakta açılan panelin kopyada açılmamasını Fusion'ın kendi araç sonucu ve kapanış kapısı yakalasın. Yakalama dosyası görsel başarı belgesi sayılmasın.

**Dosyalar ve sorumluluklar:**
- `core/menu_evidence.py`: `MenuPanel` ve saf `menu_problems(clone, source)` karşılaştırması; üçüncü parti veya dosya erişimi yok.
- `tools/assets/menu_probe.js`: kaynak ve kopya için ortak görünürlük/başlık keşfi. Mevcut eval betiği buraya taşınır; yeni algoritma kopyası yazılmaz.
- `tools/menu_probe.py`: async Playwright menü ölçümü ve yerel referans okuma/yazma. Kaynak görüntü ölçüleri mevcut `site_capture.VIEWPORTS[0]` ile eşleşir; döngüsel import açılmadan ölçü caller'dan geçirilir.
- `tools/site_capture.py`: `CapturedPage.menu_panels` (varsayılan boş); yalnız ana masaüstü yakalamada, kaynak DOM değiştirilmeden önce ölçüm.
- `engines/agent/clone_tools.py`: `.fusion/menu-reference.json` kaydını yakalamadan yazar; sürüm ve viewport ile, ham sayfa veya kimlik bilgisi saklamaz.
- `engines/agent/preview_tools.py`: kayıt varsa yerel sayfada davranışı ölçer. Bulgular `extra_problems` ve `open_findings` içine girer; `kopya` tasarım muafiyetinin dışında tutulur.
- `evals/kabul/areas/site_clone_menu.py`: ortak saf karşılaştırma ve JS kaynağına ince sync adaptör; bağımsız kabulün `Check` tipini ürüne taşımak yok.

**Önce kırmızı testler:**
- Kaynakta Kadın/Sneaker/Bot, kopyada aynı etiketli kapalı panel → `start_preview` çıktısında `SORUNLU`, `open_findings` dolu; `SiteVerifier` kapanışı engeller.
- Kopya CSS'i paneli açacak biçimde düzeltilip yeniden önizlenir → menü bulgusu temizlenir; eski kusur kalıcı cache gibi taşınmaz.
- `.fusion/tema-ilk` bulunan kopya projede de eksik menü engellenir; görsel fark muafiyeti sürer.
- Bozuk/sürümü bilinmeyen referans veya Chromium arızası → doğrulanmış menü başarısı değil, açık ölçüm eksikliği.
- Referansı olmayan eski projede yeni menü gereksinimi uydurulmaz; diğer önizleme kontrolleri korunur.
- Yakalama sırasında menü verisi gerçekten kayda ulaşır; yalnız veri sınıfına alan eklenmesi teslimat değildir.

**Doğrulama:** Yerel HTML + Chromium, kaynak/tema roundtrip testi, önizleme/kapanış entegrasyonu, Ruff ve tam mypy, bağımsız inceleme, tam pytest. Kaynak/kopya ölçümleri aynı JS ve saf karşılaştırmayı kullanır; doğal CSS hover için sync/async tarayıcı adaptörleri kendi Page türleriyle kalır.
