# Otomatik Profesyonel Yürütme Tasarımı

Tarih: 2026-09-04

## Amaç

Fusion, ek ayar istemeden basit görevleri hızlı; karmaşık görevleri planlı, dayanıklı ve doğrulanmış biçimde tamamlamalıdır. Kullanıcı `workflow_mode` açmamalı, görevi elle bölmemeli veya her adım için yeni istem yazmamalıdır.

Bu tasarım mevcut sınıflandırıcıyı, `todo_write` durumunu, `run_agent` alt turlarını, `spawn_agent` uzman devrini, changeset'i ve doğrulama kapısını tek yürütme sözleşmesinde birleştirir. İkinci bir agent motoru oluşturmaz.

## Güncel kaynak garantisi

Geliştirme `/Users/motogate/Desktop/01-Projeler/fusion-cli` deposunun `fusion-runtime-hardening-20260827-022831` dalında, `268f70c06eff83fc96ed5b95b6321353444742a6` commitinden başlar. Bu dal 2026-09-04 tarihinde uzak eş dalın 116 commit önündedir.

Kurulu `/Applications/Fusion.app` sürümü `0.3.0-alpha.8`'dir. Kurulu runtime ile deponun paket kaynağı aynı SHA-256 özetini taşır; ancak son kaynak düzeltmeleri henüz yeniden paketlenmemiştir. Son kabul, güncel HEAD'den yeniden üretilen runtime ve macOS uygulamasında yapılacaktır.

## İlkeler

1. Profesyonel `auto` yürütme temiz kurulumda varsayılandır.
2. Basit işler gereksiz planlama maliyeti taşımaz.
3. Belirsiz veya büyüyen iş güvenli biçimde workflow'a yükselir.
4. Araç başarısı görev başarısı değildir; post-condition kanıtı gerekir.
5. Doğrulanan iş checkpoint ile korunur.
6. Hata kurtarma hata türüne göre davranır ve kör tekrar yapmaz.
7. Güvenlik ve onay kapıları hiçbir alt yolda zayıflamaz.
8. Çözüm sağlayıcıdan ve Godot gibi tek bir uygulamadan bağımsızdır.

## Yürütme modu ve config göçü

Boolean `workflow_mode` tipli moda dönüşür:

- `auto`: Varsayılan. Basit işi hızlı, karmaşık işi workflow yolunda çalıştırır.
- `always`: Teşhis amacıyla her uygun kök görevi workflow'a alır.
- `off`: İleri düzey sorun giderme için eski serbest yolu zorlar.

Eski `true`, `always`; eski `false`, `auto` olarak okunur. Böylece eski `false` yeni profesyonel davranışı kapatmaz. Config yazıcısı ilk kalıcı yazmada string biçimini üretir. Bilinmeyen değer açık hatayla reddedilir. Normal arayüz kullanıcıya açması gereken kapalı bir özellik sunmaz.

## Hibrit yönlendirme

### Başlangıç kararı

Mevcut `classify_task_details`, `required_effect_for` ve `policy_for` korunur. Yeni saf karar nesnesi görev türünü, güven skorunu, dış etkiyi, kapsam belirteçlerini, bağımlı eylemleri, araç/MCP ihtiyacını ve doğrulama gereksinimini değerlendirir.

Karar:

- `fast`: Açıkça basit ve düşük riskli iş.
- `workflow`: Baştan çok adımlı veya doğrulama gerektiren iş.
- `fast_promotable`: Hızlı başlar; çalışma kanıtı büyürse yükselir.

İstem uzunluğu tek başına ölçüt değildir. “Repoyu pushla” kısa ama dış etkili; uzun bir metni özetlemek araç zinciri gerektirmiyorsa basit olabilir.

### Çalışma sırasında yükseltme

Hızlı yol şu kanıtlardan biri oluştuğunda workflow'a yükselir:

- En az üç bekleyen todo maddesi
- İkinci dosya veya bağımsız bileşen
- İkinci araç ailesi
- Bir araç çıktısına bağlı sonraki eylem
- Teşhis ve onarım gerektiren başarısızlık
- Test, build veya dış post-condition ihtiyacı
- Hızlı yol bütçesine sığmayan kalan iş
- Modelin belirlediği bağımlı sonraki eylemler

Yükseltme aynı kök turda tek yönlüdür. Mesaj geçmişinin tamamı kopyalanmaz; görev özeti, changeset, araç kanıtı ve bekleyen işler tipli başlangıç bağlamına dönüşür.

## Tipli plan

`core` katmanı yalnız stdlib kullanan frozen dataclass'lar tanımlar:

- `ExecutionPlan`: kimlik, kök görev, adımlar, durum, şema sürümü
- `PlanStep`: hedef, bağımlılıklar, beklenen etkiler, araç aileleri, başarı koşulları, doğrulama ipucu, tekrar güvenliği, durum ve deneme sayısı
- `StepEvidence`: değişen dosyalar, araç sonuçları, doğrulama, artifact yolları, dış etki ve sonraki adım özeti

Modelin serbest metni doğrudan çalıştırılmaz. Plan ayrıştırılır; boş hedef, yinelenen kimlik, bağımlılık döngüsü ve doğrulanamaz başarı koşulu reddedilir. Geçersiz plan yalnız bir düzeltme turu alır.

## Orkestrasyon

Orkestratör `engines` katmanında mevcut yapıları bağlar:

1. Rota seçer veya hızlı turdan yükseltme bağlamını alır.
2. Tipli plan üretir.
3. Bağımlılıkları tamamlanmış bekleyen adımı seçer.
4. Adımı mevcut `run_agent(..., depth=1, self_review=False)` ile temiz alt turda çalıştırır.
5. Changeset ve araç sonuçlarından `StepEvidence` üretir.
6. Adım post-condition'ını doğrular.
7. Başarıyı checkpoint'e yazar veya hatayı kurtarma politikasına yollar.
8. Tüm adımlardan sonra kök görev kabul doğrulamasını çalıştırır.
9. Kanıttan kullanıcı özetini üretir.

`spawn_agent` modelin isteğe bağlı uzman devri olarak kalır. Orkestratör yeni bir alt-agent altyapısı kurmaz.

## Bağlam aktarımı

Alt tur ana geçmişin tamamını almaz. Kök görev özeti, tam adım sözleşmesi, bağımlı adımların kanıtları, ilgili dosya ve artifact yolları, changeset ile güvenlik kısıtlarını alır.

Mevcut workflow'daki 500 karakterlik serbest not makine bağlamı olarak kullanılmaz. İnsan özeti sınırlanabilir; gerekli alanlar tipli ve kayıpsız taşınır.

## Doğrulama

Adım doğrulaması mevcut `build_verifier` ve otomatik komut keşfini kullanır. Başarı koşulu uygun doğrulayıcıyı seçer:

- Dosya: okunabilirlik ve yapısal biçim
- Kod: hedef test, lint, type-check veya build
- Godot: headless açılış ve beklenen sahne/asset
- Web: build, tarayıcı gözlemi ve UI koşulu
- MCP okuması: beklenen veri alanları
- Git: yerel/uzak post-condition

Alt turun `ok=True` dönmesi doğrulamayı atlamaz. Tüm adımlar geçtikten sonra final doğrulama, adımlar arası entegrasyonu ve kök kabul koşullarını denetler. Final kanıtı olmadan başarı yayımlanmaz.

## Hata kurtarma

Hatalar en az şu sınıflara ayrılır: yanlış argüman, geçici sağlayıcı, araç sözleşmesi uyuşmazlığı, geçersiz çıktı, doğrulama hatası, onay gereksinimi, bütçe tükenmesi, timeout, yanıt ayrıştırma hatası ve beklenmeyen hata.

- Yanlış argüman farklı argümanla sınırlı tekrar alır.
- Geçici hata config tabanlı geri çekilme alır.
- Sözleşme uyuşmazlığı araç tanımı ve gerçek hata ile planı onarır.
- Geçersiz çıktı ve doğrulama hatası yalnız ilgili adımı düzeltir.
- Onay ve bütçe tükenmesi checkpoint'i koruyarak durur.
- Timeout kısmi tanıyı korur ve dış durumu yeniden gözler.
- Ayrıştırma hatası olası yan etkiyi doğrulamadan tekrar etmez.
- Beklenmeyen hata sınırda loglanır ve checkpoint'i bozmaz.

Yıkıcı veya idempotent olmayan işlem otomatik tekrarlanmaz. Her kurtarma eylemi mevcut güvenlik politikasından geçer.

## Checkpoint ve devam

`memory` katmanındaki protokol arkasında çalışan yerel adaptör atomik kayıt tutar. Kayıt planı, adım durumlarını, kanıtları, yarım adımı, bütçeyi, proje/konuşma kimliklerini ve şema sürümünü taşır.

Devam sırasında artifact ve güvenli post-condition yeniden kontrol edilir. Kaybolmuş dosyaya ait eski başarı körlemesine kabul edilmez. Hâlâ doğrulanan tamamlanmış adımlar yeniden çalıştırılmaz. Checkpoint sır, tam prompt veya sınırsız araç çıktısı saklamaz; eski onayı yeni işlem için kullanmaz.

## Bütçe

`WorkflowBudget` planlama, adım yürütme, adım kurtarma ve final doğrulama zarflarını ayrı izler. Değerler config'ten gelir ve gerçek çağrı sayaçlarından düşer. Bir zarf tükenince tamamlanmış iş kaybolmaz; workflow açık nedenle durur ve devam edilebilir.

## Olaylar ve kullanıcı deneyimi

Tipli olaylar rota seçimini, yükseltmeyi, planı, adım başlangıç/bitişini, araç kanıtını, doğrulamayı, yeniden denemeyi, checkpoint'i, gereken kullanıcı eylemini ve final durumu taşır. UI yalnız bu olayları sunar.

Kullanıcı çalışan adımı, kullanılan aracı, doğrulama sonucunu, yeniden deneme nedenini ve kalan işi görür. Basit görev gereksiz plan paneli açmaz.

## Test stratejisi

Her davranış TDD ile eklenir. Birim testleri rota kararı, tüm yükseltme tetikleri, tek yönlü yükseltme, plan/DAG doğrulama, hata sınıflandırma, bütçe, checkpoint göçü ve olay sırasını kapsar.

Entegrasyon testleri basit hızlı yolu, otomatik karmaşık yolu, çalışma sırasında yükseltmeyi, adım doğrulamasını, farklı argümanla onarımı, kesintiden devamı, final sahte-başarı engelini, ortak changeset'i ve güvenli onay duruşunu kapsar.

Davranış değerlendirmeleri tek bilgi sorusu, tek dosya düzenleme, çok dosyalı özellik, hata düzeltme ve regresyon testi, build zinciri, Godot MCP asset görevi, sağlayıcıdan bağımsız sahte MCP ve tarayıcı+dosya+terminal görevlerini kapsar.

Başarı `TurnOutcome=completed` değildir. Final kabul koşulu, sahte başarı oranı, kör tekrar, yeniden yapılan tamamlanmış adım, çağrı sayısı ve süre birlikte ölçülür.

## Dağıtım

Her uygulama bölümü `ruff check`, `mypy` ve tam `pytest` kapısından geçmeden commit edilmez. Son teslim:

1. Runtime arşivini güncel HEAD'den üretir.
2. Manifest ve arşiv SHA-256 özetini doğrular.
3. Tauri uygulaması ile DMG'yi yeniden üretir ve imzalar.
4. Paket smoke testini temiz geçici kullanıcı alanında çalıştırır.
5. `/Applications/Fusion.app` kurulumunu günceller.
6. Kurulu uygulama ile üretilen runtime hash'ini karşılaştırır.
7. Hızlı ve karmaşık kabul görevlerini kurulu uygulama protokolünde çalıştırır.

Kaynak testlerinin geçmesi teslim değildir. Kurulu Fusion güncel runtime'ı kullanmalı ve varsayılan `auto` davranışını göstermelidir.

## Uygulama bölümleri

1. Yürütme modu ve hibrit rota
2. Tipli plan ve plan doğrulama
3. Adım orkestrasyonu
4. Kanıt ve doğrulama
5. Hata kurtarma
6. Checkpoint ve devam
7. Bütçe zarfları
8. Olaylar ve UI
9. Çok alanlı değerlendirmeler
10. Güncel runtime, uygulama, DMG ve kurulu uygulama kabulü

## Kabul ölçütleri

- Temiz kurulum ve eski `false` config `auto` kullanır.
- Basit görev plan maliyeti olmadan tamamlanır.
- Karmaşık görev ayar istemeden planlanır.
- Büyüyen görev tek yönlü yükselir.
- Plan tipli, bağımlı ve doğrulanabilir adımlar taşır.
- Her adım ve kök görev kanıtlanmadan tamamlanmaz.
- Kör tekrar yapılmaz; yıkıcı işlem otomatik yinelenmez.
- Kesinti sonrası doğrulanan işler tekrarlanmaz.
- Kullanıcı ilerlemeyi ve durma nedenini görür.
- Güvenlik kapıları alt turlarda korunur.
- Godot dışındaki görev sınıfları ölçülür.
- Tam kalite kapısı geçer.
- Güncel runtime kurulu `/Applications/Fusion.app` içinde hash ve kabul testiyle doğrulanır.
