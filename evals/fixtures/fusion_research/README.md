# Fusion araştırma görevleri — Task 6b

32 görev aynı yükleyici ve yürütücü üzerinden erişilir: 16 development, 8 validation,
8 blind. İlk 14 dosya sözleşmesi korunur; kalan 18 görev gerçek agent döngüsünün
araç, parser, checkpoint/journal, son kriter, ortam, ders ve ilerleme yollarını kullanır.

İnsan referansları çevrimdışı sağlayıcı yanıt betikleridir. `tests/test_research_support.py`
model sınırına bu yanıtları verir; gerçek araçlar ve gerçek ürün kabulü çalışır.
Bu kontrol model başarı oranı, genuine web kaydı veya canlı temel çizgi değildir.
`live_baseline` null kalır. `task6_complete` bağımsız paket incelemesi tamamlanana kadar false kalır.

`seed/` dosyaları ve suite `setup` baytları ajan çalışma alanına girer. Referans,
`scenario.json`, kabul kodu ve manifest girmez. Güvenilir controller ayrı geçici dizinde
journal/checkpoint/Chroma durumunu kurar. Chroma fixture gömmesi ağsız sabit bir uyarandır;
seçim, sürüm, bölüm, karantina ve confidence hesabı gerçek ürün kodunda yapılır.

Mevcut `AgentTaskExecutor` temiz tohumu saklar, aday ürün farkını uygular ve dış kabulü
bu temiz dizinde çalıştırır. Korunan tohum testleri aktarılmaz. `_runtime_receipt.json`
ajan dosyasından alınmaz; yalnız gerçek runner gözleminden kabul alanına yazılır.
Gözlenen model olayları, son kaynak kontrolü, özgün journal okuması ve ortam kimliği
bu makbuzdadır. Tam aday dosyası olsa bile süreç kanıtı çıkarılmış karşı kontrol düşer.

Görev bütçesi bütün rollerin `ModelCallStarted` sınırında yeni provider invocation
başlamadan uygulanır; süre sınırı mevcut `TurnDeadline` ile ve iptal edilebilir dış
çağrı kapsamında tutulur. Metadata görev kimliklerini ve heterojen görev bütçelerini
ayrı taşır; ortak tek değer yoksa scalar bütçe null kalır. `effective_config_digest`
CLI temel ayarıdır; `task_config_digests` gerçek AgentDeps.config değerinin aynı güvenli
project_effective projeksiyonundan gelir. Üretici yoksa görev ayarı bilinmiyor kalır. FrozenRun yalnız tam görev
kapsamı olan pozitif bütçeleri kabul eder. Gerçek çalıştırmalar `execution_ids` içinde
(görev, tekrar) kimliği taşır; beklenen bütün çiftler tam bir kez bulunmadan ortam veya
görev yapılandırması tamamlanmış sayılmaz. Gerçek görev yapılandırması eksikse FrozenRun
durumu doğrulanmamış kalır. Rapor bütçelerinde boolean/metin sayıya dönüştürülmez.

Ortam özeti gerçek araç/gate ve temiz kabul komutunun `EvidenceEnvironment` ölçümünden
gelir. Kapsam eksikse bilinmiyor kalır. `--corpus` mevcut Task3 `load_corpus` kabulünden
geçer; admitted, synthetic ve bilinmeyen kullanım sayıları aynı RunMetadata'ya bağlanır.
Sentetik kayıtlar genuine sayılmaz. Corpus verilmezse özeti null kalır.

Yerel kontrol:

```sh
PYTHONPATH=src python -m pytest tests/test_eval_acceptance.py tests/test_research_runtime_fixtures.py -q
```

Canlı yol aynı CLI'dir; sağlayıcı hiçbir zaman referans betiğiyle değiştirilmez:

```sh
python -m evals run evals/suite/fusion-research-dev.yaml --model MODEL --corpus CORPUS.json --out rapor.json
```

Bu komut burada canlı olarak çalıştırılmadı. Validation/blind yalnız açıkça o suite
seçildiğinde değerlendirilir. Prompt seçimi için `load_suite(allowed_splits=...)`
`namespace: fusion_research` ad alanını ve araştırma kabul komutunun fixture kimliğini
parse öncesinde doğrular; dosya adını veya split başlığını değiştirmek
kör görev kimliğini geliştirme görevi yapmaz. Direct/minimal profiller runtime
senaryoları için desteklenmez ve açıkça reddedilir.

İlk 14 görevde T01/T02 taşıma varyantları ve T11 gerçek arama sıralaması hâlâ
`file-contract; runtime stimulus variants not measured` kapsamındadır; yeni
runtime fixtureları bu eski görevlerin ölçülmemiş süreç kanıtı sayılmaz.

T13/T15/T24 shell kanıtı ilgili dondurulmuş kriter komutuna ve gerçek ToolStarted/ToolExecuted
sınırlarında ölçülen ürün hashlerine bağlıdır. T13/T24 aynı yeniden üretimin eski üründe
kırılmasını ve aday üründe geçmesini ister; T15 eski yeşil kriteri ve yeni ürün kriterini
ayrı kimlikle bağlar. İlgisiz `assert False` / `assert True` bu kanıtı sağlayamaz.
