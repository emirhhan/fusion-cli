# Ortak onarım kaydını üretim döngüsüne bağlama

Bu belge uygulanacak sözleşmedir; saf ledger canlı döngüye henüz bağlı değildir. Küçük LLM sağlayıcı, retry, bağlam ve model yapılandırması korunur. Kaynak metni veya sır depolanmaz. Amaç aynı ölçümü uzatmak yerine kanıtlı yaklaşım değişikliğine geçmektir; kalite kapısını gevşetmek değildir.

## Veri sınırı

- `core/tools.py::ToolResult` sonunda geriye uyumlu `failure_evidence: tuple[FailureEvidence, ...] = ()` alanı. `structured` ham sözlüğünü engine içinde yorumlayarak yeni bir ikinci sözleşme açılmaz.
- Ürün kontrolü sahibi ailesini belirler; engine serbest hata metninden regex ile aile türetmez. Örneğin yerleşim kontrolü taşma/çakışma/boşluk kodunu ölçüm fonksiyonundan taşır. Başlık veya koordinat değişince aile değişmez.
- `check_id` kontrolün kapsamını da ayırır (proje/kontrol kimliği); iki farklı proje aynı `layout` adına indirgenmez. `attempt_id` bağımsız gerçek çalıştırmayı tanımlar. Aynı işin tüm durum sorguları aynı kimliği kullanır.
- Kaynak parmak izi bağımsız deneme **başlamadan önce** ilgili kaynaklardan alınır. Sonuç alındığında mevcut dosyayı hashleyip eski render'ın kaynağı sanmak yasaktır. İçerik hashleri ve göreli yollar dışında içerik saklanmaz. İzlenen kaynak/bağımlılık kapsamı eksikse açık bilinmeyen kaynak kanıtı kullanılır; değişmedi iddiası kurulmaz.
- Generic shell çıkış kodu tek başına ürün ailesi değildir. Yapılandırılmış kontrol kaydı bulunmayan işler mevcut davranışlarını korur. Sağlayıcı/altyapı kanıtı ürün ledger'ına girmez.

## Araç aktarımı

`tools/jobs.py` başlangıç kaydında deneme kimliği ve deneme-öncesi kaynak manifestini saklar. Sonuç adapter'ı doğrulanmış yapılandırılmış kontrol çıktısını bir kez çözer; `job_status` her polling'de aynı typed kanıtı döndürür. Devam eden iş başarısız deneme sayılmaz. Bitmiş aynı iş tekrar sorgulanınca yeni hak tüketilmez. Bozuk/eksik kanıt görünür uyarı oluşturur; başarı veya ürün ailesi uydurulmaz.

Remotion için LayoutAudit gerçek geometri kontrolünün typed hata kodu adapter'a aktarılmalıdır. Renderer çıktısındaki kanıt yalnız belirlenmiş sürümlü bir JSON kayıt protokolüyle çözülür; genel stderr üzerinde başlık/stack regex'i kullanılmaz. Renderer kaynak manifesti/attempt kimliği ile bu kayıt birleştirilir. Çıktı kayıtları ve dosya yolları güvenilir kabul edilmez; şema ve proje kökü sınırı doğrulanır. Mevcut render ve taşma kapısı devam eder.

Oyun/animasyon kanıt adapter'ı ayrı sahiplikte çalışır; ortak ToolResult sözleşmesini kullanır. Bu plan kendi özel ikinci oyun hata yolu açmaz.

## Engine karar noktası

`loop.py::_run_tools` gerçek ToolResult alındıktan sonra, tool history mesajına ve ilerleme sinyaline geçmeden küçük bir `repair_flow` yardımcı modülüne gider. Turun paylaşılan TurnBudget nesnesi ledger sahibidir; nested düzeltme çağrıları aynı kaydı paylaşır. Sohbet sıkıştırması ledger'ı sıfırlamaz. Resume gerekiyorsa snapshot ayrıca checkpoint'e sürümlü biçimde eklenir; yalnız mesaj özetinden geri kurulmaz.

1. Aynı bağımsız deneme: `ALREADY_OBSERVED`; yeni başarısız deneme/onarım hakkı/ilerleme oluşturmaz.
2. İlk ürün başarısızlığı veya ilgili kaynak değişimi: mevcut onarım hakkı ile hedefli düzeltmeye izin; kaynak değişimi düzelme kanıtı değildir.
3. Aynı aile ve aynı kaynak: `CHANGE_APPROACH`; tek kısa notla kontrol/aile ve değişmeyen kaynak belirtilir. Modelden kaynak hipotezini değiştirip hedefli düzenleme yapması istenir. İlgisiz düzenleme bu hata kaydını sıfırlamaz.
4. Mevcut hak tükenmişse `EXHAUSTED`: doğrulanmamış sonuçla güvenilir kapanış; başarılı artefakt iddiası yok.

Bütçe yeni eşik üretmez. `TurnBudget.max_verify_rounds/verify_rounds/take_verify_round` mevcut düzeltme kapısının otoritesidir; aynı hata kaydının polling'i tüketmez. Final doğrulama ile araç kaynaklı düzeltmenin aynı hakkı iki kez tüketmemesi için tüketim tek `repair_flow` geçişinde toplanmalı ve mevcut final yolunun testleri korunmalı. Bu refactor ayrı küçük kalite fazıdır; yürürlükteki MAX_VERIFY_ROUNDS değeri değiştirilmez.

Genel RoundSignals ilerleme kuralı tüm shell/düzenlemeler için değiştirilmez. Yalnız aynı yapılandırılmış tamamlanmış ölçümün polling'i ve tekrar başarısız ölçümü yeni okuma/başarı olarak ilerleme tazelemez. Yeni gerçek kaynak düzenlemesi genel ilerleme olabilir; ilgili hata ledger'ını otomatik temizlemez.

## Önce kırmızı, sonra yeşil entegrasyon testleri

Yerel fake provider ve fake job/typed result; ağ, browser veya render gerektirmez:

- Yeni job kimliği ve komut argümanı aynı aile/manifest: yaklaşım değişikliği; ilgisiz edit ve no-op write engeli sıfırlamaz.
- Aynı bitmiş job farklı wait_s ile sorgulanır: tek deneme, tek hak tüketimi; süren job ürün başarısızlığı değildir.
- Render başladıktan sonra kaynak değişir: sonuç başlangıç manifestini korur; sonraki bağımsız deneme yeni hash taşır.
- Geçerli kaynak değişikliği ardından yeniden render: izin var, başarı ancak gerçek başarılı kontrol sonucundan gelir.
- Provider429, süreç kesintisi ve bozuk kanıt ürün loop sayacına girmez; mevcut retry/liveness davranışı korunur.
- Nested correction ve history compaction aynı snapshot/remaining budget kullanır; final gate çift hak tüketmez.
- Çok küçük bağlam bütçesinde not kısa kalır; kaynak metni/digest listesi/prompt dökümü verilmez, gate bulguları kaybolmaz.
- Generic eski ToolResult ve shell işi aynı davranışı sürdürür; oyun/animasyon typed adapter aynı ortak yoldan çalışır.

## Tamamlanma kanıtı

İlgili unit/engine/jobs testleri, ruff, mypy, bağımsız inceleme ve Türkçe yerel committen sonra boş bir görevde gerçek yeni Fusion üretimi yapılır. Kanıt: aynı layout ailesi kaynak değişmeden tekrarlanırsa yaklaşım değişikliği görünür; aynı job polling tekrar hak tüketmez; başarılı teslimde gerçek render/işlev kapıları geçer. Yalnız saf ledger testleri kolun tamamlandığını göstermez. Ağır koşular root tarafından sıralı ve WindowServer %60 sınırı altında yürütülür.
