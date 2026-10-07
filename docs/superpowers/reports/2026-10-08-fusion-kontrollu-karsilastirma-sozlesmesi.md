# Fusion kontrollü karşılaştırma sözleşmesi

Bu sözleşme **gelecekteki** boş başlangıç üretimleri içindir. Dalga37 veya önceki çıktılara sonuç görüldükten sonra puan/rubrik uydurmaz. Hedef, Fusion’ın oyun, Remotion, site kopyalama ve animasyon üretiminin tabana göre %90 daha gelişmiş ve profesyonel olmasıdır; mutlak90 kalite veya kusur azalması bu hedefin yerine geçmez.

Özgün taban koşularının kirli çalışma ağacı ve kesin motor SHA’sı bilinmiyor. `3fd76ae` **açık referans revizyonudur**; özgün tabanla aynı olduğu ileri sürülmez. Tarihî taban oranları ve geçersiz site ölçümü [önceki ölçüm sözleşmesinde](2026-10-07-fusion-yetenek-karsilastirmasi.md) korunur. Yeni karşılaştırma yalnız bu referans ile kaydedilecek güncel revizyon arasındaki farkı ölçer.

## Üretim başlamadan dondurulacak girdiler

- Referans SHA: `3fd76ae`nin tam SHA’sı; güncel motor: kalite kapısından geçmiş tam SHA. Yerel kod/beceri/kit değişiklikleri iki revizyonda da kayıtsız bırakılamaz.
- Denetim: güncel `evals` ve bağımsız görsel/işlev kontrol listesinin **tek sabit sürümü**, iki motor için aynı. Güncel motorun kit/becerileri referans üretimine enjekte edilmez.
- Brief: aşağıdaki A/B metinleri veya alanın mevcut görev metniyle birlikte üretimden önce kaydedilen nihai metin/hash. A metni referans ve güncel için byte düzeyinde aynı olmalı.
- Aynı model/öğretmen kimliği, parametreler, fallback/devralma politikası, araç adım bütçesi ve alanın mevcut `timeout_s` değeri. Yapılandırmanın sır içermeyen özeti/hash’i kaydedilir; `.env` veya sırlar okunmaz/yayınlanmaz.
- Aynı renderer/tarayıcı/sürüm, viewport, FPS, ekran ölçeği ve inceleme zamanları. Kaynak dosyaları/varlıklar aynı başlangıç girdileridir.
- Her üretim ayrı **boş** çalışma dizininden başlar. Eski çözüm/üretilmiş tema/video/oyun kodu başlangıç girdisi değildir.
- Her üretime ayrı boş `FUSION_MEMORY_DIR`; öğretmenin proje günlüğü de yeni çalışma dizininde başlar. Bu değişken referans revizyonda da mevcuttur. Kullanıcının tarayıcı oturumları, hesapları ve kimlik bilgileri taşınmaz. Ek küresel ders/plan önbelleği kullanılıyorsa eşit başlangıç sağlanmadan karşılaştırma başlatılmaz.
- Motorun gerçekten seçildiği `fusion_cli.__file__` ile doğrulanır. Koşucu eski motor seçme CLI parametresi sunmadığından motor kaynak yolu açıkça seçilir; iki koşuda da aynı evals kullanılır.
- Ağır üretimler sırayla çalışır. WindowServer yükü60% sınırına ulaşırsa yeni görsel yük başlatılmaz; kullanıcının çalışan uygulamaları kapatılmaz. Uyku/altyapı kesintileri kaydedilir.

Bir `manifest.json` her koşunun yanında bu girdileri, çalışma dizinini, başlangıç/bitiş zamanını, bellek başlangıcını, seçilen motor yolunu, kaynak görüntü/varlık hash’lerini ve çıktı/denetim kanıt yollarını taşımalı. Sır içeren yapılandırma veya ortam dökümü konmaz.

## En küçük koşu matrisi

Her satır **üç ayrı üretimdir**: referans-A, güncel-A, güncel-B. Toplam12 üretim. B, aynı alanda farklı brief aktarımını sınar; A’daki çıktıyı yeniden kullanmaz. Bu matris tek denemelik gösterimdir, kararlılık/istatistiksel genelleme kanıtı değildir.

| Alan | A: referans ve güncel aynı görev | B: yalnız güncel, farklı görev |
|---|---|---|
| Oyun | Masaüstünde file:// açılan üstten bakışlı arena oyunu. Başla; yön/ateş/pause; sırayla oynanabilen3dalga;3.dalgada boss; skor/can; gerçek yerel sprite; oyun sonu ve R ile tam sıfırlama. Her dalganın başlama/bitme ve düşman üst sınırı briefte üretimden önce aynı sayılarla sabitlenir. | Yan görünüşlü platform oyunu:3ayrı bölüm, hareket/zıplama, toplanabilir nesne, tehlike, bölüm kapısı, kaybetme ve yeniden başlatma. İlk bölüm atlanamaz; menü/HUD ayrı alan kullanır. Aynı başlangıç/bitiriş/yeniden başlatma kanıtları gerekir. |
| Remotion | Fusion tanıtımı: alanın mevcut A görev metni, aynı logo/belgeler, aynı süre/FPS/çözünürlük ve sahne içerikleri. Her sahne ile final saniyeleri gerçek render’da incelenir. | Farklı içerikli ürün lansmanı: briefte önceden listelenen problem→özellik→kullanım→çağrı sahneleri; aynı teknik süre/FPS/çözünürlük bütçesi, farklı metin ve görsel varlıklar. |
| Site | `site_kopyasi` alanı: Sneaks Up kaynak mağazasını yerel WordPress/WooCommerce’e kopyala; ana/kategori/ürün/sepet/checkout, yerel görseller ve kapıda ödemeli gerçek test siparişi. Kaynak kareleri1440×900 ve390×844’te aynı referansa sabitlenir. | `site_kopyasi_2`: Desa kaynak mağazası. Aynı sayfa türleri, viewportlar ve alışveriş akışı; farklı menü/katalog/tipografi. Kaynak erişilemezse ölçüm geçersizdir. |
| Animasyon | Alanın mevcut A görev metni: kaydırma ile ortaya çıkma, hover ve etkileşim, layout hareketi, farklı easing, okunur içerik ve reduced-motion. Metin/varlıklar ve viewportlar aynı. | Farklı bir etkinlik/program arayüzü: filtreyle kart düzeni değişimi, açılan detay, hover geri bildirimi ve kaydırma hareketi; reduced-motion alternatifleri. Aynı hareket/etkileşim/okunurluk kontrolleri. |

Yeni bütçe/eşik sayısı rastgele eklenmez. A’da belirtilmesi gereken dalga/bölüm süreleri, nesne sınırları ve varlık listesi; B’nin nihai metniyle birlikte **ilk üretimden önce** manifestte tamamlanır. Bunlar eksikse satır başlamaya hazır değildir. Alanlar için mevcut kabul CLI’si `--alan <alan> --paralel 1 --tekrar 1 --config <sabit-config> --cikti <yeni-kok>` biçiminde kullanılabilir. B görevleri ayrı sabit metinle aynı sürücü üzerinden açılmalıdır; mevcut CLI’nin B brief parametresi olduğu varsayılmaz.

## İşlev kapısı: puandan ayrı zorunlu kabul

| Alan | Kritik başarısızlıklar ve gerekli gerçek kanıt |
|---|---|
| Oyun | Gerçek Başla tıklaması başarısız; ilk bölüm/dalga atlanır; geçişte savaş/doğma devam eder; kontrol/pause bozuk; gerçek oyun sonu/R sıfırlama çalışmaz; donma/konsol hatası. Uzun oyun, kontrollü düşman sayısı, boş sayfa/oyun FPS karşılaştırması ve menü/oynama/bitiş kareleri gerekir. Zor olması tek başına kusur değildir. |
| Remotion | Strict tsc veya gerçek render başarısız; anlamlı içerik taşar/çakışır; sahne/final boş veya okunamaz. Yerleşim kapısı kaldırılmaz. Aynı dış kabul kuralları her iki çıktıya uygulanır; referansın kaynak koduna yeni kit eklenmez. |
| Site | Eksik/kırık sayfa veya kaynak; ana/kategori/ürün/sepet/checkout akışı çalışmaz; sipariş veritabanında oluşmaz; önemli mobil taşma/başlık çakışması; ölü zorunlu menü/kontrol. Aynı kaynakla renkli eş viewport kareleri gerekir; gri ton0.75 tek başına birebir kopya kabulü değildir. |
| Animasyon | CSS/JS eksik; gereken hareket/hover/kaydırma/filtre çalışmaz; konsol hatası/donma/taşma; reduced-motion yolu çalışmaz veya içerik erişilemez. Gerçek etkileşim öncesi/sonrası kareleri gerekir. |

Kapı başarısızsa teslim profesyonel kabul edilmez. Kalite endeksi yine tanı amacıyla raporlanabilir; kapı sonucunu yüksek puanla örtmez. Çizim çağrısı görünürlüğü, dosya varlığı çalışma durumunu, yüklenen asset gerçek kullanımını tek başına kanıtlamaz.

## Önceden sabit profesyonellik endeksi

Her alan **eşit ağırlıklı5boyutta**, boyut başına0–4 puanlanır. Endeks `Q = 5 × (beş puanın toplamı)`; tavan100’dür. Aynı kanıt ve aynı ankraj kullanılır. Endeks operasyonel ve kısmen insan yargısına dayanır; doğal bir oran ölçeği veya kesin bilimsel büyüklük değildir.

| Puan | Bütün boyutlar için ankraj |
|---|---|
| 0 | İlgili çıktı/özellik yok veya değerlendirilemiyor; altyapı kaynaklı değerlendirilemezlik ayrıca geçersiz koşu olarak ayrılır. |
| 1 | Özellik tanınabilir, fakat büyük kusur kullanımını/mesajını önemli ölçüde bozuyor. |
| 2 | Temel gereksinim çalışıyor/görünüyor; tekrar eden belirgin kusur veya tutarsızlık var. |
| 3 | Briefi tutarlı karşılıyor; sınırlı küçük kusurlar var, normal kullanım/okuma korunuyor. |
| 4 | Örneklenen bütün zorunlu durumlarda tutarlı, okunur, kontrollü ve gerekçeli profesyonel uygulama; kritik kusur yok. |

| Alan | Eşit ağırlıklı5boyut |
|---|---|
| Oyun | Kontrol/ilerleme tutarlılığı; HUD/menü/bitiş okunurluğu; sprite ve görsel tutarlılık; zorluk/geri bildirim/efekt; kontrollü yükte akıcılık. |
| Remotion | Tipografi/hiyerarşi; kompozisyon/yerleşim; ritim/anlatı; hareket/geçiş tutarlılığı; sahne/final bütünlüğü ve teknik teslim. |
| Site | Logo/renk/tipografi benzerliği; yerleşim/boşluk/görsel benzerliği; responsive düzen; sayfalar arası tutarlılık; alışveriş/etkileşim deneyimi. |
| Animasyon | Hareketin amaca uygunluğu; timing/easing; görsel hiyerarşi/okunurluk; etkileşim/geri bildirim; responsive/reduced-motion tutarlılığı. |

Referans/güncel etiketleri mümkünse gizlenerek aynı kare/etkileşim paketleri incelenir. Her puan, kanıt yolu ve kısa gerekçeyle yazılır. Tek kör inceleme istatistiksel tarafsızlık garantisi değildir; değerlendirici ve bilinen etiketler kaydedilir. B koşusu ayrı puanlanır, A’daki gelişim oranına karıştırılmaz.

## %90 göreli hedef ve matematik sınırı

Aynı alanın eş koşullu A endeksi için `g = 100 × (Q_güncel − Q_referans) / Q_referans` raporlanır. Hedef için `Q_güncel ≥ 1.9 × Q_referans` gerekir.

- Referans0 ise oran tanımsızdır; %sonsuz veya %90 geçti yazılmaz.
- Tavan100 olduğundan referans `100/1.9 ≈ 52.63` üzerindeyse bu endekste %90 göreli artış matematiksel olarak mümkün değildir. Beş adet0–4 puanın endeksi5’in katlarıdır; bu nedenle bu rubrikte referans55 ve üzeri hedefe erişemez.
- Bu sınır görülünce rubrik/tavan/başlangıç puanı değiştirilmez, yeni elverişli referans seçilmez. Hedefin bu ölçekte kanıtlanamadığı açıkça bildirilir; mutlak90 veya kusur azalması yerine konmaz.
- Dört alan ayrı gösterilir. Bir alanın güçlü gelişimi diğerinin başarısızlığını ortalamayla gizlemez. Kullanıcı dört alanın gelişimini istemiştir.

Tek A çifti, yalnız o brief ve o denemenin farkını gösterir. Tek B, yalnız örnek aktarımı gösterir. Kararlılık iddiası için bağımsız tekrarlar gerekir; tüm geçerli denemeler ve değişkenlik raporlanır. Tekrar sayısı sonuç görüldükten sonra en iyi örneği seçmek için kullanılmaz.

## Geçerlilik ve yürütme sınırı

Sağlayıcı/sürücü/denetçi arızası, kaynak siteye erişememe veya ölçümü bozan makine uykusu ayrı işaretlenir. Normal bütçede eksik üretim, modelin hatalı kodu veya başarısız kapanış kapısı gerçek ürün sonucu olarak kalır. Kesinti iddiası olay/log kanıtına dayanır; gerçek kusur mazeretle geçiştirilmez.

Mevcut dalgalar ancak bütün sabit koşulları gerçekten karşıladığı kanıtlanırsa yeni matriste kullanılabilir. Bu sözleşme eski çıktıları geriye dönük yeniden tanımlamaz. Ortak iyileştirme teslimatı ile yeni boş üretimdeki aktarım kanıtı birlikte gerekli; üretilmiş çıktıyı elle yamamak Fusion başarısı değildir.
