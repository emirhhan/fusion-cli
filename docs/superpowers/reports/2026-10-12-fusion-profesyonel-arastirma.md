# Fusion — kapsamlı profesyonel kullanım raporu

12 Ekim 2026. 145 geliştirme maddesi, 16 uygulama paketi, 35 regresyon senaryosu, 12 canlı kabul görevi. Araştırma ve uygulama devri; ürünün tamamlandığı iddiası değil.

Bu tek dosya rapor, kaynak belgelerden üretilmiştir. Düzenleme kaynağı `2026-10-12-fusion-profesyonel-arastirma/` klasörü ve uygulama planıdır. Karar defteri D01–D05 sözleşme önceliğini belirler.


---

Belge: `docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/README.md`

# Fusion profesyonel kullanım araştırması ve uygulama dosyası

**Tarih:** 12 Ekim 2026, Türkiye. **Amaç:** Fusion'ı günlük ve gelişmiş işlerde gönül rahatlığıyla kullanılabilecek bir çalışma ortamına dönüştürmek. **Teslim:** araştırma, korunacak özellikler, geniş iş listesi, kesin davranış sözleşmeleri, kabul senaryoları ve başka bir hesapta GPT-6.1 Sol low ile uygulanabilecek görev paketleri.

Bu belge tamamlanan bir geliştirme iddiası değildir. Kaynak kod incelemesi, bu oturumdaki test sonuçları ve resmî ürün belgeleri ayrı kanıt sınıflarıdır. Kodda bulunması, bugün paketlenmiş uygulamada uçtan uca çalıştığı anlamına gelmez. Önerilen özellikler mevcut gibi sunulmaz.

## Okuma ve uygulama sırası

1. Bu ana rapor: ürün kararı, başlangıç durumu, ortak sözleşmeler, öncelik ve ölçüm.
2. `01-masaustu-sohbet-ayarlar.md`: masaüstü, karşılama, sohbet, model, düşünme, izin ve soru araştırması.
3. `02-mcp-agent-donguleri.md`: MCP, araçlar, beceriler, ajanlar ve kurtarma araştırması.
4. `03-kits-gorsel-uretimi.md`: Kits ve görsel üretim araştırması.
5. `04-ortak-gelistirme-listesi.md`: alanları birbirine bağlayan ek işler ve Fusion'a özgü ileri fikirler.
6. `05-kabul-senaryolari.md`: kullanıcı akışları, hata koşulları ve teslim kapıları.
7. `../../plans/2026-10-12-fusion-profesyonel-uygulama.md`: uygulayıcı için görev paketleri.
8. `07-kaynak-ve-karar-defteri.md`: bağımsız inceleme sonrası kesinleşen öneri kararları; D01–D05 uygulamada önceliklidir.
9. `06-baska-hesaba-devret.md`: başka hesaba yapıştırılacak başlangıç talimatı ve ilerleme kaydı.

Alan listeleri alternatif fikir kataloglarıdır. Hepsi aynı anda uygulanmayacak. Uygulama planı bağımlılıkları ve ilk güvenilir kullanım sürümünü belirler. Birbirini kapsayan maddeler görev paketinde birleştirilir; ikinci bir altyapı oluşturulmaz.

## 1. Ana karar

Fusion'ın çekirdeğini silip bir ChatGPT görünümü yazmak gerekmiyor. Mevcut çekirdekte doğrulanmış araç yeteneği, öğretmen/çırak, ders belleği, tipli olaylar, açık sonuç durumu, onarım kaydı, checkpoint, MCP bağlantı havuzu ve gerçek etki workflow'ları gibi değerli yapılar var. Geliştirme bu yapıların üzerine yapılmalı.

Kullanıcının beklediği his şudur: bir isteği yazdığında Fusion ne yapabileceğini bilir, işi başlatır, gerekiyorsa kısa ve anlamlı soru sorar, gereksiz onaylarla kesmez, çalışırken anlaşılır ilerleme gösterir, hatadan kurtulur ve bitirdiğinde gerçek sonucu açar. Çalışma ortamı sade görünür; ayrıntı istendiğinde erişilebilir. ChatGPT/Codex/Claude düzeyinde görünüm bu tutarlılıktan doğar.

Öncelik sırası: **doğru durum → doğru yetenek → güvenilir iş yürütme → tutarlı arayüz → görsel incelik → ileri özellikler**. Güzel kartların arkasında yanlış başarı veya yanlış model varsa güven oluşmaz.

“Asla kırılmasın/asla saçmalamasın” mutlak bir yazılım veya model garantisi olarak verilmez. Uygulanabilir karşılığı: desteklenen kritik akışlarda gerileme kapısı, bilinmeyeni açık gösterme, başarısızlığı başarıya çevirmeme, kontrollü yan etki, tekrar denemede aynı işlemi iki kez yapmama ve kullanıcı verisini kaybetmeden kurtarma. Raporun kabul senaryoları bu hedefi somutlaştırır.

## 2. Bugünkü gerçek başlangıç

| Kanıt | Sonuç | Bu sonucun kanıtlamadığı |
|---|---|---|
| Fusion CLI kaynak revizyonu | `644a2e44145db726bd09565511e40e38cfda7231`, mevcut `ajan-ekibi` dalı | Çalışma ağacındaki ek değişiklikler bu commit'e henüz dahil değil |
| Kits kaynak revizyonu | `1dd007c1a37b3795fe00a28045acac6c136d5fd3` | Paketlenmiş Fusion içindeki Kits sürümünün aynı olduğu doğrulanmadı |
| Masaüstü Vitest | Node 22 ile 122 dosya / 956 test geçti | Tauri, gerçek MCP, ses ve paket kurulum kabulü değil |
| TypeScript | App ve Kits `tsc --noEmit` geçti | Kits sunucu build, lint, tüm testler ve gerçek model smoke değil |
| Python tam koşu | Üç başarısız testle bitti | Tam kalite kapısı yeşil değil; bu koşulda kod commit edilmemeli |
| Ruff/mypy | Ruff kod kontrolleri; tam mypy 532 dosya geçti | Python davranış testlerinin yerine geçmez |
| Gemini | Gerçek Fusion isteğine `OK`, yaklaşık 33.3 saniye; giriş doğrulaması kaydedildi | 3.1 Pro erişimi kanıtlanmadı; ret sonrası mevcut 3.6 Flash yedeği çalıştı |
| Görsel inceleme | Depodaki sohbet, ayarlar, karşılama screenshot fixture'ları gözle incelendi | Bunlar yeni canlı uygulama ekranları değil; bazı fixture'lar geçmiş UI içeriyor |

Python başarısızlıkları:

- `tests/test_kabul_html_game.py::test_restart_only_on_game_over_with_state_hook_passes`
- `tests/test_remotion_kit.py::test_runtime_edilmis_onceki_kare_feature_markerini_yeniden_kullanmaz`
- `tests/test_remotion_observe.py::test_renderer_ayri_gruptaki_direncli_chromium_benzeri_cocugu_temizler`

Nedenleri bu araştırma turunda teşhis edilmedi. Zamanlamaya benzeyen hata, inceleme olmadan “flaky” diye kapatılmamalı. Yeni özelliklerden önce aynı testler tek başına ve uygun çalışma ortamında tekrar edilmeli; ürün kusuru ile ortam/test senkronizasyonu ayrılmalı.

Masaüstü CI Node 22 kullanıyor. Global Node 26, jsdom `localStorage` uyumsuzluğuyla 194 test hatası üretti; Node 22 ile aynı paket temiz geçti. Kits `engines.node >=24` ve `kits:*` scriptlerinde Node 24.21.0 kullanıyor. **App ile Kits'e aynı Node sürümünü körlemesine dayatmayın.** Paket araçları her alt projenin doğrulanmış runtime'ını kullanmalı.

Araştırmaya başlarken tam pytest bitmişti. Bu rapor herhangi bir canlı kabul üretiminin arkada başarıyla sürdüğü varsayımına dayanmaz. Önceki menü kanıtı ve oyun koordinatı değişiklikleri çalışma ağacında bulunuyor; bu araştırma bunları silmez veya commit etmez.

## 3. Korunması gereken güçlü fikirler

| Yapı | Kaynakta görülen sahip | Geliştirme ilkesi |
|---|---|---|
| Ücretsiz sağlayıcılar + doğrulanmış araç yeteneği | `core/model_capability.py`, `config/tool_policy.py`, `appserver/model_catalog.py` | Yalnız katalogda var diye mutation agent yapma; doğrulama kapısını koru |
| Öğretmen/çırak ve dersler | `engines/agent/teacher_flow.py`, `apprentice_handoff.py`, bellek katmanı | İyi örneklerden öğrenme korunmalı; yanlış sonuç ders diye kaydedilmemeli |
| Tipli olay ve ayrı ajan kanalı | `core/events.py`, `app/src/protocol/olayAkisi.ts` | Yeni UI gerçek olaydan beslensin; sahte ilerleme yüzdesi üretmesin |
| Gerçek tur sonucu | `TurnOutcome`, `FilesChanged`, `NoFileChanges` | Model “bitti” dese bile runtime sonucu partial ise bunu açık göster |
| Model değişim olayı | `ModelFallbackActivated`, `ModelResult` gözlenen model alanı | Var olan olayı bütün arayüzlere taşı; yeni paralel fallback sistemi kurma |
| Onarım kaydı | `core/repair_ledger.py`, `engines/agent/repair_flow.py` | Aynı sonucu polling yeni deneme saymasın; aynı hatada yaklaşım değişsin |
| Workflow checkpoint | `core/checkpoint.py`, `memory/checkpoint_store.py` | Devam etmeden kaynak ve etki kanıtını kontrol et |
| MCP pool + hata sınıflandırması | `mcp_bridge/pool.py`, `failures.py` | Tek bozuk sunucu diğerlerini durdurmasın; kalıcı hatayı kör retry yapma |
| Tek composer, proje ve çalışma paneli | `app/src/screens/Composer.tsx`, `Inspector.tsx` | Kullanıcıya teknik motor seçimi yükleme; ayrıntıyı bağlamsal göster |
| Kanıttan takip önerisi | `FollowupsSuggested`, `core/followups.py` | Basit devam önerisi için ekstra pahalı model çağrısı ekleme |
| Görsel akış editörü | `app/src/imagecreate/akis.ts`, `AkisTuvali.tsx` | Basit üretimi zorlaştırmadan ileri kullanıcıya akış düzenleme sun |
| Kits belge + sohbet yakınlığı | Kits `PageConversation.tsx`, `PageDocument.tsx` | Belgeyi ve konuşmayı birlikte çalıştır; kaydetme/uygulama çatışmasını çöz |

7–8 Ekim raporları bugünkü kodun yerine geçmez. Örneğin eski onarım raporu “ledger henüz bağlı değil” derken güncel `loop.py` `record_failure_evidence` kullanıyor. Eski backlog'daki dosya anma ve takip önerileri de güncel kaynakta bulunuyor. Uygulayıcı her eski “eksik” maddesini yeniden doğrulamalı.

## 4. Güncel ürün araştırmasından alınacak ilkeler

- ChatGPT/Codex projeleri sohbetleri, dosyaları ve talimatları birlikte taşır. Fusion'da proje, sohbet ve Kits belgesinin hangi bağlamı paylaştığı açık olmalı. [Resmî Projects and chats belgesi](https://learn.chatgpt.com/docs/projects).
- Codex'te izin politikası ile teknik sandbox ayrı kavramlardır. Fusion'ın “onay isteme” seçimi işletim sistemi izolasyonu varmış gibi sunulmamalı. [Resmî agent approvals belgesi](https://learn.chatgpt.com/docs/agent-approvals-security).
- Codex MCP yerel STDIO ve Streamable HTTP bağlarını, kimlik doğrulamayı ve sunucu talimatlarını destekler. Fusion ekranı kurulumu değil çalışan yeteneği göstermeli. [Resmî MCP belgesi](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
- Skill, başlık/description ile keşfedilip gerektiğinde içeriği yüklenen tekrar kullanılabilir workflow'dur. Fusion her skill'i her tur prompt'una doldurmamalı. [Resmî skills belgesi](https://learn.chatgpt.com/docs/build-skills).
- ChatGPT görsel akışında üretim, referans, büyük görüntüleme ve seçili görsele geri bildirim birlikte çalışır. Fusion'da görsel üretimi sohbetin ve dosya tesliminin doğal parçası olmalı. [Resmî image generation belgesi](https://learn.chatgpt.com/docs/image-generation).
- Claude Code izin kurallarını host uygular; prompt tek başına izin sınırı değildir. Fusion'ın izin ekranı gerçek executor davranışıyla aynı olmalı. [Claude Code permissions](https://code.claude.com/docs/en/permissions).
- Claude checkpoint'i kod ve konuşma geri dönüşünü ayrı sunar. Fusion checkpoint ile dış servisteki işlemin geri alınmasını aynı şey sanmamalı. [Claude checkpointing](https://code.claude.com/docs/en/checkpointing).
- Claude subagent ayrı bağlam/sorumluluk sağlar; skill tekrar kullanılabilir talimattır. Fusion UI bu farkı anlatmalı. [Claude subagents](https://code.claude.com/docs/en/sub-agents), [Claude skills](https://code.claude.com/docs/en/skills).
- MCP annotations güvenlik sözleşmesi değildir; güvenilmeyen sunucunun ipuçları tek başına izni kaldırmamalı. [MCP annotation açıklaması](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/).
- MCP'nin 2026-07-28 sürümü önemli protokol değişiklikleri içeriyor. Fusion'ın eski initialize/oturum akışını bir anda silmek yerine sunucu/SDK uyumluluk matrisi ve adapter geçişi gerekiyor. [Resmî sürüm duyurusu](https://blog.modelcontextprotocol.io/posts/2026-07-28/).
- Klavye erişimi, görünür odak, kontrast, hover içeriğine erişim ve durum mesajları profesyonel UI'nin parçasıdır. [WCAG 2.2 Quick Reference](https://www.w3.org/WAI/WCAG22/quickref/).

Bunlar benzer ürünlerin bütün özelliklerinin Fusion'da kullanılabileceğinin kanıtı değildir. Özellikle ChatGPT aboneliğiyle Fusion'a her API modelinin bağlanabileceği varsayılmaz. Sağlayıcı kullanım yolu ve yetenek kanıtı ayrı doğrulanır.

## 5. Ürün davranış sözleşmeleri

### 5.1 İstenen ve gerçekleşen model

Var olan `ModelCapability`, `CompletionRequest`, `ModelResult`, `ModelCallStarted/Finished`, `ModelFallbackActivated` genişletilir. UI kendi model kataloğunu üretmez. Katalog “doğrulanmış / doğrulanmamış / şu an yanıt vermiyor” ayrımını korur. Başarılı yanıt için kullanılan model runtime'dan gelir; istenen model adı kopyalanmaz.

Model değiştirme işlemi başarısızsa önceki etkin model korunur; UI seçimin uygulanmadığını gösterir. Bir tur sürerken seçilen yeni model varsayılan olarak **sonraki tur** için geçerli olur; aktif tur sessizce başka modele taşınmaz. Daha sonra açık “şimdi taşı” eklenirse checkpoint ve yetenek kontrolü gerekir.

### 5.2 Thinking kontrolü

“Düşünmeyi göster” görüntüleme tercihi, `reasoning_effort` sağlayıcı isteği ve `disable_thinking` template kontrolü farklı alanlardır. UI bunları tek anahtar gibi davranamaz. Desteklenmeyen ayar sunucuya gönderilmez; bilinmeyen destek “kapalı” veya “destekli” diye gösterilmez. Ham gizli düşünme metni vaat edilmez; sağlayıcıdan gelen izinli özet varsa ayrı sunulur.

GPT-6.1 Sol low, bu raporu uygulayacak başka hesabın çalışma tercihidir; Fusion'ın kendi ücretsiz model kimliğini değiştirme talimatı değildir. Resmî API belgesinde GPT-6.1 Sol için low desteklenir; none/minimal desteklenmez ve tool calling için Responses gerekir. Mevcut sağlayıcı adapter'ı doğrulanmadan Chat Completions'a tools eklemek yanlış olur. [GPT-6.1 Sol model belgesi](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

### 5.3 İzin ve soru

Tercih sorusu, eksik bilgi sorusu ve işlem onayı ayrı UI durumlarıdır. Tavsiye edilen seçenek kullanıcı yanıtı sayılmaz. Zaman aşımı, pencere kapanması veya ağ kopması onay sayılmaz. Yanıt kimliği ve tur/işlem kimliği eşleşmeden işlem çalışmaz. Onay kapsamı sadece ekranda gösterilen işlem ve hedefi kapsar; argümanlar değişince eski onay yeniden kullanılamaz.

Günlük geri alınabilir proje işleri mevcut onay politikasına göre kesintisiz ilerler. Dış paylaşım, silme veya izin genişletme gibi eylemler için neden ve somut önizleme gösterilir. Kullanıcı her aşamada tekrar aynı genel soruya maruz kalmaz. İzin politikası bütün CLI/Desktop/Kits yollarında aynı host otoritesinden uygulanır.

### 5.4 İş yaşam döngüsü

Kullanıcıya şu ayrımlar gösterilir: hazırlık, çalışıyor, yanıt bekliyor, onay bekliyor, doğruluyor, tamamlandı, kısmen tamamlandı, başarısız, iptal edildi. Bunlar önerilen sunum durumlarıdır; yeni motor durum makinesi oluşturmadan var olan olaylar ve sonuçlar üzerine projection kurulmalıdır.

Durdur düğmesi yalnız UI spinner'ını kapatmaz: owned provider/tool/job task'ını iptal eder, cleanup sonucu kaydeder. Tamamlandı yalnız gerçek final kapısı geçince gösterilir. Çalışan turdan başka sohbete geçmek işi kaybetmez. Yeni kullanıcı mesajı eski işe düzeltme mi, bağımsız görev mi olduğu belirlenerek işlenir; yarım iş sessizce unutulmaz.

### 5.5 Sonuç ve artefakt

Her teslimde çıktı dosyası/URL, çalışma kaydı, doğrulama özeti ve açık eksikler erişilebilir olur. Dosya değişikliğini model metni değil gerçek değişiklik kümesi bildirir. Önizleme başarısı ile yayına alma başarısı ayrı tutulur. Aynı işin tekrar sorgulanması aynı çıktı kimliğini korur.

### 5.6 Bellek

Talimat, kullanıcı tercihi, geçmiş konuşma ve doğrulanmış ders ayrı kaynak türleridir. Kaynak, tarih ve kapsam görünür olur. Eski konuşma bir görevi yetkilendiren yeni kullanıcı talimatına dönüşmez. Bir ders kullanıcı geri bildirimi veya başarısız kabul sonucu ile geçersizleştirilebilir. Öğrenme kötü bir workaround'u kalıcı çözüm diye yaymamalı.

## 6. Arayüz tasarım yönü

Kaynak screenshot'larında üç sütunlu çalışma alanı, düzenli ayarlar ve sade karşılama var. Bunlar korunmalı. Eski sohbet fixture'ında Sohbet/Kod düğmeleri görünürken güncel ürün kararı tek composer; screenshot'ların yenilenmesi gerekir. Mevcut görüntüler tasarım araştırma girdisidir, bugünkü ürün davranışı değildir.

Önerilen ekran yapısı:

- Sol: projeler/sohbetler, arama, yeni sohbet; üretim alanları ikincil gezinmede. Kits ayrı uygulama gibi değil aynı proje bağlamının çalışma yüzeyi olarak anlaşılmalı.
- Orta: birincil sohbet; kullanıcı mesajı, kısa çalışma anlatımı, gerektiğinde açılan adımlar, nihai teslim.
- Alt: composer; ekler, model, düşünme ve onay modu, gönder/durdur. Tüm kontroller her zaman bağırmaz; etkin durum kısa etiketle görünür.
- Sağ veya alt: dosya, diff, terminal, tarayıcı, görsel, belge. Çıktı seçilince ilgili panel açılır; ilgisiz boş panel alan tüketmez.
- Ayarlar: genel, hesap/sağlayıcılar, modeller, araçlar/bağlayıcılar, beceriler/ajanlar, bellek, ses, izinler, gelişmiş/teşhis. Yeni kategoriler ancak mevcut ekranların görevlerini birleştirdikten sonra eklenir.

ChatGPT markasını kopyalama yerine Fusion'ın adı, maskotu ve kaynak/öğretmen gücü korunur. Tasarım token'ları ortak olmalı; App ve Kits'in farklı CSS dosyalarına rastgele aynı renkleri yazmak senkronizasyon değildir. İlk uygulama kararı mevcut token sistemini kaynak kabul etmek; Kits'e sürümlü üretilen token paketi/adaptörü vermektir. İki repo sürümleri farklı olduğundan iki React ağacını hemen birleştirmek önerilmiyor.

## 7. Öncelik ve yayın sırası

| Sıra | Teslim | Bağımlılık | Neden önce |
|---|---|---|---|
| P0-A | Mevcut üç hata, runtime seçimi, test durum kaydı | Yok | Kırık tabanın üzerine özellik koymama |
| P0-B | Olay/sonuç/onay/soru tutarlılığı | A | Yanlış başarı ve yanlış işlem temel güven sorunu |
| P0-C | Model ve thinking sözleşmesi | B | Kullanıcının seçtiği ile kullanılanın uyuşması |
| P0-D | MCP hata ve izin doğruluğu | B | Bağlandı sanılan ama çalışmayan araçları giderme |
| P0-E | Kurtarma, veri kaybı ve tekrar yan etki kapısı | B/D | Uzun işlerde güven |
| P1-A | Sohbet/karşılama/ayarlar görsel ve davranış bütünlüğü | B/C | Kullanıcının günlük ana yüzeyi |
| P1-B | Görsel üretim + artefakt teslimi | C/E | Çalışan üretim ve düzenleme deneyimi |
| P1-C | Kits host/sohbet/belge bütünlüğü | B/E | İki ürün gibi davranmayı önleme |
| P1-D | Ses/tarayıcı/yerel bilgisayar kabulü | D/E/C | Gerçek donanım ve oturum gerektirir |
| P2 | İleri fikirler, otomasyon ve uzman ekip | P0/P1 | Güvenilir taban olmadan büyütmeme |

İlk güvenilir kullanım sürümü, bütün katalog maddelerini tamamlamak zorunda değil. P0 ve günlük kullanılan P1 senaryoları geçmeli; kalan özellikler görünür “deneysel / bağlı değil” durumuyla sakince sunulmalı. Çalışmayan düğmeyi etkin gösterip sonradan açıklama yapmak yerine kullanılabilirlik koşulu baştan belirtilir.

## 8. Başarı nasıl ölçülecek?

Aynı kullanıcı brief'i, aynı başlangıç dosyaları, aynı izin kapsamı ve kayıtlı model/transport ile Fusion, Codex ve Claude çıktıları karşılaştırılabilir. Model erişimi/sağlayıcı kesintisi ayrı etiketlenir. Rastgele farklı işlerden parite yüzdesi üretmeyin.

Her senaryoda kaydedilecek ölçüler: görev sonucu, kullanıcı müdahale sayısı, gereksiz onay/soru, yanlış başarı, veri kaybı, tekrar yan etki, toparlanabilme, gerçek kullanılan model, süre, destekliyorsa token/maliyet, görsel rubrik. Bilinmeyen ölçüm sıfır değildir.

Önerilen sert teslim kapıları: senaryo kapsamındaki veri kaybı, yetkisiz/iki kez yan etki ve yanlış tamamlandı iddiası **0 olmalı**. Bu gelecekte bütün koşullarda sıfır kusur garantisi değil, test edilen yayın kapısıdır. Zaman ve kalite için hedef eşikleri bugünkü benchmark ölçüldükten sonra yazılmalı; ölçmeden “%99.9 güvenilir”, “Claude'dan iyi”, “90% parite” yazılmamalı.

Görsel rubrik: hiyerarşi, okunabilirlik, aralık/tutarlılık, durum geri bildirimi, klavye/erişilebilirlik, teslimin anlaşılması. Her puanın screenshot ve gözlenmiş gerekçesi tutulmalı. Screenshot golden'ı değiştirmek kusuru düzeltmek değildir.

## 9. Uygulama kuralları

- Kullanıcının mevcut branch'i ve değişiklikleri korunur. Bu rapor branch/push/merge talimatı değildir.
- `.env`, API anahtarları, çerez veya özel içerik rapora/test fixture'ına girmez.
- Ücretsiz kullanım kimliği korunur; ücretli sağlayıcı isteğe bağlı yetenek olmalı.
- Aynı davranış için ikinci model/izin/araç/oturum altyapısı açılmaz.
- Yeni parametreleri desteklemeyen eski istemci/çekirdek için geriye uyum testi yazılır.
- Her küçük paket: kırmızı davranış testi → küçük değişiklik → ilgili test → lint/type → gerekli tam kapı → bağımsız inceleme → Türkçe conventional commit. Tam kapı kırmızı iken commit yok.
- Ağır pytest ile `evals.kabul` aynı anda çalıştırılmaz. Canlı kabul işler ve UI browser koşuları kaynak baskısına göre sıralanır.
- Test başarısını canlı ürün başarısı sanmayın. Özellikle MCP OAuth, görsel üretim, mikrofon, pencere öne gelmesi, paket çalışma zamanı gerçek kabul gerektirir.
- Uygulama kodu bu araştırma tesliminde değiştirilmedi. Araştırma taslağının gelecekteki bir uygulayıcı tarafından tamamlanmış iş gibi işaretlenmesi yasaktır.

## Araştırma tesliminin kapsamı

145 ayrı katalog maddesi: U35 + E35 + K35 + R40. Bunlar 16 uygulama paketine birleştirildi. 35 deterministik kabul ve 12 canlı kullanım senaryosu var. Kullanıcı başka hesapta uygulayacak; bu teslimde paketler başlamadı. Bağımsız uygulanabilirlik incelemesinin önemli açıkları D01–D05 ile kapatıldı. Sözleşme çözümlemelerinde 07 karar defteri ana rapor ve paket kısa ifadelerinden önce gelir.


---

Belge: `docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/01-masaustu-sohbet-ayarlar.md`

# Fusion arayüz araştırması — onboarding, sohbet, ayarlar, modeller ve onaylar

## Kanıt sınırı
12 Ekim 2026 tarihli salt okunur kaynak incelemesi. Depo: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`. `.env` veya gizli değer dosyaları okunmadı. Uygulama, tarayıcı ve test komutları çalıştırılmadı. Aşağıdaki “mevcut” ifadeleri kod ve mevcut test tanımlarına dayanır; testlerin bugün geçtiği veya davranışın gerçek masaüstü oturumunda doğrulandığı iddia edilmez. Yollar depo köküne göredir; tam yol oluşturmak için yukarıdaki kök kullanılır.

## Mevcut güçlü taraflar
- `app/src/onboarding/Onboarding.tsx`: altı adımlı kontrollü kurulum, geri/ileri/atlama, başlık odağı, `aria-current`, Alt+ok gezinmesi; dış metinlerde anahtar biçimi maskeleme. `Onboarding.test.tsx` bu davranışlar için testler içeriyor. Mobil düzen ve azaltılmış hareket kuralı `Onboarding.css` içinde mevcut.
- `app/src/screens/RuntimeSetup.tsx`: semantik ilerleme çubuğu ve onarılabilir durumda tek onarım eylemi. `RuntimeSetup.test.tsx` ilerleme, onarım ve uygun olmayan durumda düğmenin gizlenmesini ele alıyor.
- `app/src/screens/Composer.tsx`: Enter/Shift+Enter, IME koruması, ekler ve sürükleme, @ dosya anması, slash önerileri, gerçek izin modu, dikte/ses ayrımı, tur sırasında kuyruklama ve Esc durdurma. `Composer.test.tsx` bu akışları geniş ölçüde kapsıyor. `dosyaAnmasi.test.ts` imlecin cümle ortasındaki davranışını kapsıyor.
- `app/src/screens/Conversation.tsx`: Markdown yanıtlar, gönderilen eklerin izi, diff kartları, görev ilerlemesi, takip önerileri, ekip ve önizleme rolleri; araç ayrıntıları katlanabilir. `Conversation.test.tsx`, `Followups.test.tsx`, `ActivityLine.test.tsx` ilgili davranışları içeriyor.
- `app/src/screens/useStickToBottom.ts`: kullanıcı geçmiş okurken otomatik kaydırmayı durdurma; `useStickToBottom.test.tsx` ilgili ayrımı kapsıyor.
- `app/src/screens/ActivityLine.tsx`: tek canlı gösterge, oturumdan gelen başlangıç zamanı, süre/token bilgisi, kalıcı araç izi ve başarısızlık görünürlüğü. Sohbet akışının tamamını canlı bölge yapmayan tek durum duyurusu mevcut.
- `app/src/screens/ModelPicker.tsx`: etkin model görünür; tembel yükleme, Türkçe arama, görev büyüklüğüne göre gruplama, boş/yüklenen durumlar, Escape ve dış tık. `ModelPicker.test.tsx` bunları ve uzun ad kısaltmayı kapsıyor.
- `app/src/settings/Settings.tsx`: bölümlü ve aranabilir pencere, Escape, uç kontroller arasında Tab döngüsü, kapanınca odak iadesi, yükleme hatasında gerçek neden ve yeniden deneme. `Settings.test.tsx` hata, bölüm, tema, model, izin ve gelişmiş kontrolleri kapsıyor.
- `app/src/settings/sections/Models.tsx`: ajan modeli ve Fusion motoru ayrılmış; bağlı öğretmen açıklanıyor. Düşünme düzeyi bilinçli kaldırılmış; `Settings.test.tsx:231` bunu açıkça doğrulayan test tanımı taşıyor. Dolayısıyla mevcut düşünme seviyesi seçicisi var denmemeli.
- `app/src/dialogs/Approval.tsx`: izin ve soru aynı kompakt kartta fakat farklı protokol alanlarıyla iletiliyor (`secim` / `metin`); hedef, diff, tehlike, ayrıntı, serbest cevap ve klavye seçenekleri var. `Approval.test.tsx` bunları kapsıyor.
- `app/src/screens/ApprovalModeMenu.tsx`: açıklamalı beş mod, roving odak, menü radyo semantiği; bypass Shift+Tab döngüsünden çıkarılmış. `Composer.test.tsx` bu ayrımı kapsıyor.
- `app/src/screens/ContextGauge.tsx`: ölçü bilinmiyorsa sahte sıfır yok; özetleme doluluğu ve model token penceresi açıkça ayrılıyor. `ContextGauge.test.tsx` eşikleri, ölçü yokluğunu ve açılır ayrıntıları kapsıyor.
- `app/src/sessions/useSessions.test.tsx`: kuyruk, başarısız model değişimi, model seçicisinin sohbeti komut cevabıyla kirletmemesi, bağlam/maliyet ölçümü ve durdurma üst sınırı için testler mevcut.

## Öncelikli açıklar ve 35 uygulanabilir geliştirme
Öncelik: P1 temel doğruluk/erişilebilirlik ve toparlanma; P2 akış kolaylığı; P3 olgunlaştırma. “Eksik” ifadeleri incelenen bileşen sınırına aittir; tüm ürün için mutlak yokluk iddiası değildir.

### U01 — **P1 — Keşif hatasını görünür yap.** `SessionApplication.tsx:ConnectedOnboarding` iki keşif isteğini `Promise.all` içinde birleştirip `.catch(() => undefined)` ile yutuyor. Kaynak/sağlayıcı bazında ayrı hata ve yeniden deneme ekle; bir servis hatası diğerinin başarılı sonucunu saklamasın.
### U02 — **P1 — Keşfediliyor ile bulunamadı ayrımı.** Aynı bileşen kaynakları baştan `not-found`, çırağı `active:true` başlatıyor. Sonuç gelene kadar “Denetleniyor/bilinmiyor” göster; yükleme durumunu erişilebilir duyur.
### U03 — **P1 — Gerçek öğe sayısı.** `ConnectedOnboarding` bulunan her kaynak için `itemCount:1` üretiyor; `Onboarding.tsx` bunu “1 öğe” olarak basıyor. Gerçek sayı gelmiyorsa yalnız “Bulundu” göster veya çekirdekten ölçülen sayı getir.
### U04 — **P1 — Sağlayıcı sağlığı ve anahtar varlığını ayır.** `ConnectedOnboarding` yalnız `kurulu===true` üzerinden “Hazır” oluşturuyor. Yapılandırılmış, doğrulanmış ve hata durumlarını ayrı göster; hazır etiketi başarılı bağlantı kontrolüne dayansın.
### U05 — **P1 — Çırağa dönüşte sonuç ve hata.** `handleResetToApprentice` yükleniyor, `ok:false` veya catch göstermiyor. İşlem sürerken düğmeyi kilitle ve başarı/hata sonucunu yaz.
### U06 — **P2 — Kurulumda bağlantıya doğrudan yol.** `ProvidersStep` kurulum gerekli satırlarında eylem yok. Sağlayıcı seçip bağlantı kurmaya götüren düğme ve geri dönüş ekle.
### U07 — **P2 — Projesiz devamı açıklaştır.** `Onboarding.tsx` proje seçilmezse İleri kapalı, metin atlanabileceğini söylüyor; “Şimdilik atla” bütün kurulumu bitiriyor. “Proje seçmeden devam et” ile tamamlandı adımına geç.
### U08 — **P2 — Kurulum ilerlemesini sakla.** `ConnectedOnboarding` adım/seçim yalnız React state. Kapanma sonrası adım ve güvenli proje kimliğini geri getir; yeniden başlat seçeneği sun.
### U09 — **P1 — Depolama hatasında uygulama açılabilsin.** `App.tsx` onboarding localStorage okuma/yazmasını korumasız yapıyor. Başarısız depolamada oturum içi tamamlamayı koru; depolama istisnası render veya tamamlamayı çökertmesin.
### U10 — **P2 — Kaynakların boş durumunu dürüst başlıkla sun.** `SourcesStep` her koşulda “Kaynaklarınız bulundu” diyor. Hiç kaynak yoksa kurulum/içe aktarma yönlendirmesi olan alternatif başlık ekle.
### U11 — **P1 — Gönderim hatasında taslağı kurtar.** `Composer.send` taslağı `onSend` öncesi temizliyor ve callback void. Başarısız gönderimi taslak/kuyruk durumuyla sakla; “Yeniden gönder” sun.
### U12 — **P2 — Eklerle boş metin davranışını açıklaştır.** `send` ve gönder düğmesi yalnız `draft.trim()` ile çalışıyor. Yalnız görsel/dosya gönderimine izin ver veya ek altında gerekli metni açıkça belirt.
### U13 — **P1 — Shift+Tab geri gezinmesini koru.** `Composer.onKeyDown` izin callback'i varsa Shift+Tab'ı her zaman mod değişimine çeviriyor. Standart geri Tab dolaşımını koruyan alternatif kısayol ve açıklama sun; ekran okuyucu/klavye testi ekle.
### U14 — **P1 — Slash/dosya önerilerini textarea ile bağla.** `Composer.tsx` listbox var ama textarea `aria-controls`, `aria-expanded`, `aria-activedescendant` taşımıyor. Aktif öneriyi erişilebilir duyur ve uygun combobox örüntüsünü kur.
### U15 — **P2 — Dosya aramasının yüklenme/boş/hata durumları.** @ önerisi yalnız sonuç varsa açılıyor. Aranıyor, eşleşme yok, erişim hatası ayrımı ve tekrar dene ekle; kullanıcı sessiz boşluğu yorumlamak zorunda kalmasın.
### U16 — **P2 — @ aramasını istek yaşam döngüsüyle düzenle.** `mentionQuery` her değişimde callback tetikliyor; bileşende gecikme/iptal yok. Üst katmandaki davranışı doğrula; gerekiyorsa debounce ve eski sonucu atma sözleşmesi ekle.
### U17 — **P2 — Kuyruğu görünür yönetilebilir yap.** `useSessions.ts` kuyruk Map'i ve `Composer` “Sıraya ekle” var; composer prop'larında kuyruk listesi/sayısı yok. Bekleyen mesaj sayısı, düzenleme, kaldırma ve sırayı göster.
### U18 — **P2 — Çalışırken etkin model kimliğini görünür tut.** `Composer` çalışan dalında ModelPicker çizilmiyor. Değiştirme kapalı kalabilse bile mevcut model adını göster; kullanıcı uzun turun hangi modelde olduğunu bilsin.
### U19 — **P2 — Çakışan hata mesajlarını ayrı göster.** `attachmentError || dictationError` birini gizliyor. İki işlem aynı anda hatalıysa ikisini ilgili denetim yanında göster.
### U20 — **P2 — Yapıştırılan görselleri destekle.** `Composer` dosya drop ve ekleme var, textarea paste handler yok. Pano görselini ek önizlemesine dönüştür; boyut/biçim doğrulamasını mevcut ek kanalıyla paylaş.
### U21 — **P1 — Kopyalama sonucunu bildir.** `Conversation.AssistantMessage` clipboard promise'i geri bildirim ve catch olmadan çağırıyor. “Kopyalandı” durumunu ve başarısız kopya için görünür hata/fallback ekle.
### U22 — **P2 — Okurken yeni yanıt göstergesi.** `useStickToBottom` geçmiş okumayı koruyor; `Conversation` en alta dönme denetimi taşımıyor. Yeni çıktı rozeti ve “En yeni mesaja git” düğmesi ekle.
### U23 — **P2 — Gönderilmiş ekleri açılabilir yap.** `SentAttachments` span/44px resim gösteriyor. Klavyeyle açılan resim büyütme ve dosya açma eylemi ekle; dosya erişilemezse açık hata göster.
### U24 — **P1 — Mesajlara kalıcı kimlik.** `Conversation` dış haritalamada `key={index}` kullanıyor. Mesaj kimliği sözleşmesi ekle; geçmiş eklendiğinde katlanmış ayrıntı/odak yanlış mesaja taşınmasın.
### U25 — **P2 — Uzun geçmişi kontrollü çiz.** `Conversation` tüm mesajları map ediyor; `Conversation.perf.test.tsx` mevcut. Kaydırma konumu, erişilebilirlik ve seçilmiş metni koruyan sayfalama/sanallaştırma değerlendir; gerçek büyük geçmiş ölçümüyle karar ver.
### U26 — **P1 — Model listesinde klavye ve odak.** `ModelPicker` Escape/dış tık var, aramaya ilk odak, oklarla seçenek, Home/End ve kapanınca trigger odağı yok. Bunları ekle ve mevcut testlere klavye odak senaryoları ekle.
### U27 — **P1 — Model liste semantiğini düzelt.** `role=listbox` altında search input ve grup başlıkları var. Aramayı listbox dışına al, grup etiketlerini erişilebilir bağla veya bütün seçiciyi combobox örüntüsüne taşı.
### U28 — **P1 — Model yükleme hatasını boş listeden ayır.** ModelPicker props yalnız busy/options içeriyor. error/retry ekle; “sağlayıcıya bağlan” metni ulaşım hatasında yanlış yönlendirme olmasın.
### U29 — **P2 — Model bağlama eylemini tıklanabilir yap.** Boş listedeki “Ayarlar'dan … bağlan” yalnız metin. Kullanıcıyı gerçek sağlayıcı bağlantı ekranına götür; Ayarlar/ControlPanel ürün ayrımını koru.
### U30 — **P2 — Düşünme seviyesini yeteneğe göre tasarla.** `Models.tsx` ve `Settings.test.tsx` düşünme ayarını bilinçli kaldırmış. Genelleştirilmiş `/level` geri eklemek yerine sağlayıcının doğruladığı reasoning seçenekleri varsa göster; desteklenmeyende açıklama ver. Bu yeni özellik önerisidir, bug değildir.
### U31 — **P2 — Ayar aramasını içerik üzerinden zenginleştir.** `Settings` araması yalnız bölüm etiketinde includes yapıyor. “tema”, “geçmiş”, “gateway”, “bellek” aramasını ilgili satıra götür; eşleşme yok durumunu ve sonuç sayısını göster.
### U32 — **P1 — Ayar mutasyonlarında başarı kontrolü.** `toggleGateway` ve `selectMode` sonuç `ok:false` kontrolü yapmıyor; yalnız promise rejection hata sayılıyor. Başarısız sonucu gerçek hata olarak ele al, bekleme/yeniden deneme ve doğru durum göster; load'taki yaklaşımı paylaş.
### U33 — **P1 — Soru kimliği değişince yerel cevap state'ini sıfırla.** `Approval` digerAcik/digerMetin'i sadece mount başlangıcında belirliyor. Ardışık soruda önceki metin taşınmasın; soru kimliğine göre reset/key uygula. `serbestCevap=false` iken rakam kısayolunun Diğer'i açmasına da izin verme.
### U34 — **P1 — Onayda tek gönderim ve odak iadesi.** `Approval` seçenekler callback sonrası disable olmuyor, önceki odağı saklamıyor. Cevap iletilirken tekrar tıklama/sayı engeli, hata sonrası retry ve kart kapanınca composer odağı ekle; asenkron protokol testi yaz.
### U35 — **P1 — Esc açıklamasını gerçek davranışla eşleştir.** `Approval.vazgec` izin kartında deny yoksa hiçbir işlem yapmıyor ama hint “Esc kapat” diyor. Çekirdek sözleşmesine uygun açık iptal/kapat callback'i tanımla veya metni değiştir; ayrıca `ApprovalModeMenu` ve `ContextGauge` kapanınca tetikleyiciye odağı geri getir.

## Ayrı doğrulama gerektiren noktalar
- Yukarıdaki semantik ve state bulguları doğrudan kaynakta görülebiliyor; renk kontrastı, gerçek dar pencere taşmaları, VoiceOver duyuruları, web oturumu gecikmeleri ve büyük geçmiş performansı çalıştırılmadan doğrulanamaz.
- CSS içinde responsive/azaltılmış hareket kuralları olması, gerçek WCAG uyumu veya yerel macOS pencere deneyiminin sorunsuz olduğu anlamına gelmez.
- Mevcut test adları davranış sözleşmesini kanıtlar; bu araştırma testleri çalıştırmadı. Sonraki doğrulamada seçili bileşen testleri, gerçek Tauri oturumu ve klavye/VoiceOver geçişleri ayrı kanıt olarak kaydedilmeli.

## U maddeleri için kesin test/teslim grupları

Aşağıdaki grup her U maddesindeki kısa öneriyi uygulanabilir kabul sözleşmesine bağlar. “Yeni” dosya araştırma önerisidir; varmış gibi import edilmez.

| Maddeler | Test dosyası ve ek assertion |
|---|---|
| U01–U05/U08 | Yeni `app/src/onboarding/ConnectedOnboarding.test.tsx`: discovery A reject/B ready, unknown count, pending apprentice, reset ok:false, resume step. ConnectedOnboarding test edilebilir export/adapter'a taşınır; ikinci provider store kurulmaz. |
| U06/U07/U10 | `Onboarding.test.tsx`: bağlan action doğru bölüm, projesiz devam complete, sıfır kaynakta “bulundu” başlığı yok. |
| U09 | `App.runtime.test.tsx` + App onboarding testi: storage get/set SecurityError uygulamayı çökertmez. |
| U11/U12/U17/U18 | `Composer.test.tsx` + `useSessions.test.tsx`: reject taslak ve ek snapshot'ı korur; text-empty attachments kararı açık; queue length/order/edit; busy requested/observed model label. |
| U13–U16/U20 | Composer/dosyaAnmasi testleri: normal Shift+Tab erişim, aktif descendant, stale mention response, empty/error, clipboard image mevcut attachment validator'dan geçer. |
| U19/U21–U25 | Conversation/useStickToBottom/perf testleri: iki eşzamanlı hata görünür; clipboard reject; yeni çıktı düğmesi; ek açma failure; prepend sonrası mesaj detail state'i kimlikle korunur. |
| U26–U29 | ModelPicker/useSessions: autofocus, Arrow/Home/End/Escape return, error≠empty, retry ve provider connect. |
| U30 | Settings/model_catalog/provider tests: bilinen supported effort, unknown farkı, adapter'a geçersiz parametre yok; kaldırılmış eski universal level testi yeni capability sözleşmesiyle bilinçli güncellenir. |
| U31/U32 | Settings.test.tsx: içerik araması satıra götürür; selectMode/toggleGateway ok:false önceki değeri korur; pending double-click engeli. |
| U33–U35 | Approval.test.tsx + protocol/voice: q1 Other text q2'ye taşınmaz; disabledOther numeric shortcut kapalı; answer sent once; fail retry; no-deny Escape metni doğru; focus restore. |

Yalnız attachment gönderimine izin verme U12 için önerilen ürün kararıdır: dosya/görsel tek başına gönderildiğinde genel inceleme istemi UI'da açıkça gösterilerek host'a gönderilir; modelin kullanıcı niyetini kesin bildiği varsayılmaz. Gönderim güvenli bir ask/describe görevinden başlar; dış etki yetkisi türetilmez. U13 için Shift+Tab mod çevrimi korunacaksa kullanıcı ayarıyla opt-in yapılır; varsayılan normal klavye gezinmesidir. Bunlar araştırmanın önerdiği kararlardır, geçmiş kullanıcı onayı diye sunulmaz.


---

Belge: `docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/02-mcp-agent-donguleri.md`

# Ajan motoru, MCP ve yürütme güvenilirliği

**Kanıt düzeyi:** Bu bölüm 12 Ekim 2026 tarihinde kaynak ve test tanımlarının salt okunur incelemesine dayanır. Testler, sağlayıcı çağrıları, OAuth akışları ve gerçek MCP sunucuları çalıştırılmadı. “Mevcut” kaynakta bulunan mekanizmayı; “öneri” yapılması gereken işi ifade eder. Test dosyasının bulunması, testin bu ortamda geçtiği anlamına gelmez. Depo kökü `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; aşağıdaki yollar bu köke göredir.

### Mevcut güçlü taraflar

1. **MCP bağlantısı tur yerine oturum kaynağı.** `src/fusion_cli/mcp_bridge/pool.py` sunucu başına supervisor görevi açıyor; anyio kaynakları açıldığı görevde kapatılıyor. Sunucular paralel bağlanıyor, yalnız değişen bağlantı yenileniyor. `_draining` bağlantı kurulurken iptal edilen supervisor görevlerini de topluyor. `tests/test_mcp_pool.py` yeniden kullanım, eşzamanlı bağlanma, aynı görevde kapanış ve iptal sızıntısı senaryolarını içeriyor. Bu, yalnız soyut bir havuz tasarımı değil, ölçülen gecikme ve iptal sorunlarını hedefleyen uygulama.
2. **Kalıcı ve geçici MCP arızaları ayrılıyor.** OAuth girişi gerektiren veya çalıştırıcısı olmayan sunucular park ediliyor; geçici ağ hataları sonraki turda yeniden deneniyor. Kimlik tekilleştirme ve bağlantı servisi ayrı modüllerde: `mcp_bridge/identity.py`, `failures.py`, `service.py`. `tests/test_mcp_identity.py`, `test_mcp_failures.py`, `test_mcp_connect_failures.py` ve `test_mcp_noninteractive.py` ilgili test yüzeyleri.
3. **Onay kararı tek protokolden geçiyor.** `engines/agent/approval.py` auto/edits/security/plan/bypass kiplerini aynı `ApprovalPolicy` arayüzüne topluyor. `ApprovalMemory` turlar arasında oturum iznini koruyor; yıkıcı işlem bu hafızaya alınmıyor. Gerçek insan reddi (`DENIED`) ile sorulamayan oturum (`BLOCKED`) ayrılıyor. Çağrı bazlı `effect_resolver` uzak yetenek ağ geçitleri için düşünülmüş. `test_agent_approval.py` ve `test_approval_modes.py` bu ayrımları açıkça test ediyor.
4. **Paralel delegasyonun temel çatışma modeli var.** `engines/agent/team.py` salt okuyucuları ve ayrık yazma alanlarını aynı dalgada, belirsiz yazıcıları tek başına koşturuyor; semaphore ile eşzamanlılık sınırı var. Persona, agent_id ve başlangıç/bitiş olayları arayüzün ajanları ayrı göstermesini sağlıyor. Alt ajan kendi görev listesine sahipken `touched` ve `changes` ana ajanla paylaşılıyor; ana doğrulama kapısı alt ajan dosyalarını da görebiliyor. `tests/test_team.py` gerçek coroutine eşzamanlılığını ve yazma alanı sınırını test ediyor.
5. **Kurtarma “aynısını tekrar dene” düzeyini aşmış.** `engines/agent/recovery.py` hata sınıfını doğrulama bulgularıyla birlikte değerlendiriyor; `RetrySafety.NEVER` ve izin hatasında otomatik tekrar yapmıyor. `OBSERVE_FIRST` dış durumun önce okunmasını istiyor. Aynı onarım yönergesiyle kör tekrar sınırlanıyor; farklı doğrulama bulgusu üçüncü denemeyi mümkün kılıyor. `tests/test_recovery.py`, `test_recovery_new_information.py` ve `test_plan_asset_recovery.py` mevcut kanıt yüzeyi.
6. **Checkpoint yalnız metin özeti değil.** `memory/checkpoint_store.py` şema v4 içinde plan adımlarını, bağımlılıkları, retry güvenliğini, doğrulama kontrollerini, kanıtı, bütçe kullanımını, sıkıştırma sayısını ve onarım durumunu saklıyor. Atomik replace uygulanmış. `engines/agent/plan_checkpoint.py` artifact değişimini ve bağımlı adımların invalidasyonunu ele alıyor. `tests/test_checkpoint_repair.py` idempotent restore, bozuk sayaç, özel kaynak yolu ve ham araç çıktısının saklanmaması senaryolarını içeriyor.
7. **Beceri keşfi ve bağlam ekonomisi var.** `tools/capabilities.py` beceri/ajan kütüphanesini keşfediyor, arama sıralaması yapıyor, uzun beceriyi devam offset'i ile okutuyor. `engines/agent/expertise.py` geniş referansı her turda basmak yerine tek yüksek güvenli beceriyi 4.000 karakterle ekliyor. Kaynak yorumu, 1.696 araç çağrısında beceri çağrısının sıfır olduğuna ve geniş uzmanlık bağlamının yanlış sınıflandırmayla zarar verdiğine ilişkin geçmiş ölçümleri anlatıyor; bu ölçümlerin yeniden üretildiği bu incelemede doğrulanmadı.
8. **Model uygunluğu ile model sıralaması ayrılmış.** `core/model_capability.py` native/emulated/none/unknown araç desteğini ayrı tutuyor. `engines/capability_probe.py` modelin kendi yetenek beyanını değil ayrıştırılabilir araç çağrısını ve görüntü işaretini kanıt kabul ediyor. `core/routing_strategy.py` priority, latency, headroom, least_used, random, round_robin ve escalate yollarını saf, enjekte edilebilir fonksiyonla sıralıyor. Escalate modelleri düşürmeden döndürüyor. `tests/test_capability_probe.py`, `test_capability_probe_wiring.py`, `test_eligibility.py` ve `test_single_loop_routing.py` bu mimari sınırları destekleyen test dosyaları.
9. **Sessiz model çağrısı için canlılık kontrolü var.** `engines/agent/liveness.py` ilk parça 90 saniye gelmezse aynı modele fallback olmadan küçük istek atıyor; web oturumu modellerini yan etki nedeniyle yoklamıyor. Sağlıklı cevapta çalışmaya devam ediyor, yoklamada hatada nedeni döndürüyor. `tests/test_liveness.py` ve `test_agent_loop.py` zamanlama yüzeyleri; gerçek sağlayıcı sağlığı bu incelemede ölçülmedi.

### Öncelikli somut bulgular

- `mcp_bridge/tool_effect.py:effect_from_annotations` önce `readOnlyHint`, sonra `destructiveHint` değerlendiriyor. İki ipucu da true ise okuma sınıfı dönüyor. Bu, kaynakta doğrudan görülen öncelik çatışmasıdır; gerçek bir sunucuda sömürüldüğü iddia edilmiyor.
- `team.py:schedule_waves` yazma alanlarını doğrudan `Path(raw)` ile karşılaştırıyor; kanonik kök çözümlemesi yapmıyor. `a/../b` ve `b`, symlink ve mutlak/göreli alias senaryolarında scheduler kararının gerçek dosya kimliğiyle tutarlı olduğu ayrıca sınanmalı.
- `team.py:run_team` çocukları bir `TaskGroup` içinde çalıştırıyor, `run_subagent` için exception sonuç kapsülü/finally bitiş olayı görünmüyor. Bir beklenmedik çocuk istisnası grubun diğer görevlerini iptal edebilir; “tek ajan başarısız oldu, kalan sonuçlar korunur” davranışı mevcut kaynakta garanti değil.
- `approval.py:_scope` shell için komut bazlı, diğer araçlar için yalnız araç adı bazlı oturum izni üretiyor. Uzak yazma izninin kaynak/hesap/eylem sınırına daraltılması ürün kararı olarak ele alınmalı.
- `checkpoint_store.py:save` geçici dosya adını yalnız PID ile türetiyor, ardından replace yapıyor; fsync ve eşzamanlı save revision kontrolü görünmüyor. `_path` güvenli karakter dönüşümünden sonra farklı plan kimlikleri aynı ada düşebilir. Bunlar somut geliştirme adaylarıdır.
- `clarify.py` yalnız ilk tur, yeni proje, 200 karakter altı ve sınırlı Türkçe/İngilizce kelime deseninde soru notu ekliyor. Bu bilinçli dar heuristik; “her belirsiz isteği yakalıyor” iddiası doğru olmaz.
- `routing_strategy.py` cost_optimized için yalnız `:free` proxy'si kullanıyor; gerçek token fiyatı ve görev başına toplam maliyet optimizasyonu henüz bu fonksiyonun davranışı değil.

### 35 uygulanabilir iş maddesi

Bütün maddeler **öneri**dir. Mevcut mekanizmayı yeniden yazmak yerine belirtilen açığı doğrulamayı veya yeteneği genişletmeyi hedefler. P0: izin/izolasyon ya da devam doğruluğu; P1: güvenilirlik; P2: ürün/verimlilik. Test yolu “yeni” yazmıyorsa mevcut dosyanın genişletilmesi önerilir.

| No / öncelik | İş ve dosya | Test ve kabul ölçütü |
|---|---|---|
| E01 P0 | MCP çelişkili ipuçlarında yıkıcılığı öne al; `src/fusion_cli/mcp_bridge/tool_effect.py`. | `tests/test_mcp_tool_effect.py`: readOnly=true/destructive=true kombinasyonu REMOTE_DESTRUCTIVE; `test_agent_approval.py`: auto her çağrıda sorar. |
| E02 P0 | MCP okuma ipucunu sunucu güven politikasıyla sınırla; `mcp_bridge/client.py`, `tool_effect.py`. Mevcut ipucu dönüşümüne güven seviyesi ekle. | `tests/test_mcp_tool_effect.py`, `test_mcp.py`: güvenilmeyen sunucunun okuma beyanı yazma iznini otomatik gevşetmez; güvenilen okuma sunucusu gereksiz sorulmaz. |
| E03 P1 | MCP keşfinde değişen araç şemasını parmak iziyle izle; `mcp_bridge/client.py`, `pool.py`. | `tests/test_mcp_pool.py`: aynı isim yeni şema aldıktan sonra yeni çağrı doğrulanır, eski schema sessizce kullanılmaz. |
| E04 P1 | Keşif/call/close için ayrı süre bütçesi ve yapılandırılabilir üst sınır; `mcp_bridge/client.py`, `pool.py`. | `tests/test_mcp_connect_failures.py`, `test_mcp_pool.py`: asılı list_tools bir sunucuyu sınırda bırakır; çalışan diğer sunucunun araçları hazır kalır. |
| E05 P1 | Geçici MCP arızalarına server bazlı jitter/backoff ekle; `mcp_bridge/pool.py`, `failures.py`. | `tests/test_mcp_pool.py`: ardışık turlar ağ arızasına saniyelik fırtına üretmez; süre dolunca yeniden bağlanır, explicit reconnect beklemeyi kaldırır. |
| E06 P1 | OAuth yenileme yarışını tek uçuşla koru; `mcp_bridge/oauth.py`, `tokens.py`. | `tests/test_mcp_oauth.py`: aynı token için 10 paralel çağrı bir refresh yapar; iptal başka bekleyenin tokenını bozmaz; token çıktıya girmez. |
| E07 P1 | MCP shutdown drenajı için süre ve süreç kaçak kanıtı ekle; `mcp_bridge/pool.py`. | `tests/test_mcp_pool.py`: connection-open iptali ve close iptali sonrası supervisor yok; yerel fixture süreci kalmıyor. Gerçek stdio smoke kabulü ayrıca kayıtlı. |
| E08 P2 | MCP sağlık olaylarını yapılandırılmış olarak sun; `mcp_bridge/service.py`, `core/events.py`. | `tests/test_mcp_service.py`: parked/transient/connected ayrımı, latency ve toparlanma zamanı arayüze gelir; credential ve ham authorization header yok. |
| E09 P0 | Delegasyon yazma alanlarını kök ve symlink ile kanonikleştir; `engines/agent/team.py`. | `tests/test_team.py`: `a/../b`, `b` ve symlink alias aynı dalgada yazamaz; kök dışına çıkan scope açık hata verir. |
| E10 P0 | Çocuğun scope'u ebeveyn scope'unun kesişimi olsun; `team.py:derive_sub_context`. | `tests/test_team.py`: parent yalnız src iken child tests veya `../` alanıyla yetki genişletemez; dar child alanı çalışır. |
| E11 P1 | Alt ajan exception/cancellation'ını sonuç kapsülüne çevir; `team.py:run_subagent`, `run_team`. | `tests/test_team.py`: bir çocuk çökerken bağımsız kardeş tamamlanır; her Started için tam bir Finished/cancelled terminal olayı vardır. |
| E12 P1 | Takım çağrı/doğrulama/süre bütçesini mevcut ana bütçeyle paylaş; token bütçesi için önerilen additive sayaç ve provider usage entegrasyonu tasarla (mevcut TurnBudget token saymıyor); `team.py`, `engines/agent/context_budget.py`. | `tests/test_team.py`, `test_context_budget.py`: 3 çocuk mevcut birleşik çağrı/süre bütçesini aşamaz; usage bilinmiyorsa kesin token tavanı iddiası yok; ana ajan sonuçları ve durma nedenini alır. |
| E13 P1 | Alt görev sonucunu kanıt/changed paths/blocker alanlarıyla tipli hale getir; `team.py:SubRun`, `_team_report`. | `tests/test_team.py`: boş metin başarı sayılmaz; ana doğrulama child'ın gerçek changed paths listesini görür; başarısız sonuç başarılı gibi özetlenmez. |
| E14 P2 | Takım görev sayısı için açık tavan ve adil dalga planlama; `team.py:spawn_agents_tool`, `schedule_waves`. | `tests/test_team.py`: yüzlerce görev reddedilir veya bölünür; okuyucular uzun yazıcı dizisinde açlığa düşmez; input sıra sonuçta korunur. |
| E15 P0 | Uzak oturum iznini sunucu+eylem+hedef/hesap kapsamına daralt; `engines/agent/approval.py:_scope`. | `tests/test_agent_approval.py`: A hesabına verilen izin B hesabında geçmez; aynı güvenli scope sonraki tur tekrar sorulmaz; destructive her seferinde sorulur. |
| E16 P1 | Effect resolver başarısızlığında açık fail-closed karar üret; `approval.py:resolve_request`. | `tests/test_agent_approval.py`: resolver timeout/exception'da araç çalışmaz, gerekçe görünür; eldeki izin yanlış effect'e taşınmaz. |
| E17 P1 | Onay belleğinin revocation ve policy-change davranışını belirginleştir; `approval.py:ApprovalMemory`. | `tests/test_approval_modes.py`: kullanıcı izni kaldırınca sonraki çağrı sorulur; plan kipine geçiş eski session allow ile yazmayı açmaz. |
| E18 P1 | Onay beklerken kullanıcı steer/cancel kararını tek terminal durumuna bağla; `engines/agent/loop.py`, `approval.py`. | `tests/test_agent_loop.py`, `test_agent_approval.py`: onayda iptal aracı koşturmaz; geç gelen once cevabı sonraki çağrıya uygulanmaz. |
| E19 P2 | İzin kararına kaynak/gerekçe kaydı ekle; `approval.py`, `appserver/approval_summary.py`. | `tests/test_approval_summary.py`: auto, preallowed, session, once, blocked ayrımı raporlanır; hassas argümanlar maskelenir. |
| E20 P1 | Belirsizlik için kritik eksik bilgi kontrolü ekle; `engines/agent/clarify.py`. | `tests/test_clarify.py`: uzun ama veri kaynağı eksik yeni proje tek soru alır; mevcut ayrıntılı proje yeniden teknoloji sorusu almaz. |
| E21 P1 | Soru yanıtı, timeout ve “öneriyle devam” ayrımını tipli yap; `engines/agent/engine_tools.py`, `engines/agent/loop.py`. | `tests/test_agent_loop.py` ve yeni `tests/test_question_lifecycle.py`: cevapsız soru varsayılan onay sayılmaz; optional karar açık varsayımla devam eder. |
| E22 P2 | Soru kararını checkpoint'e taşı; `core/checkpoint.py`, `memory/checkpoint_store.py`, `clarify.py`. | `tests/test_checkpoint_store.py`, `test_clarify.py`: resume aynı kararı tekrar sormaz; kullanıcı yeni mesajda kararı değiştirince eski cevap üstün gelmez. |
| E23 P1 | Beceri aramasında Türkçe çekim/ASCII alias ve anlaşılır kaynak gösterimi; `tools/capabilities.py:search_scored`. | `tests/test_capabilities.py`: oluştur/olustur ve animasyonlu sorguları beklenen beceriyi bulur; kısa kelime alt dize yanlış eşleşmesi geri gelmez. |
| E24 P1 | Beceri/ajan bilinmeyen araç isimlerini teşhis et; `tools/capabilities.py:map_tools`. | `tests/test_capabilities.py`: bilinmeyen isim görünür teşhis üretir, bilinen araçlar korunur; yalnız bilinmeyenlerden oluşan liste mevcut boş allow-set ile kalır. Boş liste ve * için mevcut tam-set davranışı ayrı compatibility testidir. |
| E25 P1 | Beceri sayfası değişiminde offset tutarlılığı için içerik hash'i kullan; `tools/capabilities.py:load_skill_page`. | `tests/test_capabilities.py`: ikinci sayfa okunmadan dosya değişirse devam yeniden başlatılır/uyarılır; eski ve yeni talimat birleşmez. |
| E26 P2 | Uzmanlık ipucunu katalog verisinden türet ve seçim gerekçesini ölç; `engines/agent/expertise.py`, `tools/capabilities.py`. | `tests/test_expertise.py`: birden çok güçlü eşleşmede çelişen beceri otomatik yüklenmez; açık Remotion/Godot ayrımı korunur; prompt 4.000 karakter bütçesini aşmaz. |
| E27 P0 | Checkpoint dosya kimliğini çakışmasız hale getir; `memory/checkpoint_store.py:_path`. | `tests/test_checkpoint_store.py`: `a/b` ile `a_b` ayrı kaydedilir; path traversal yok; eski adların migration okuması bozulmaz. |
| E28 P0 | Checkpoint save için benzersiz temp, durable fsync ve revision CAS; `checkpoint_store.py:save`. | `tests/test_checkpoint_store.py`: aynı PID iki paralel save bozulmaz; eski revision yeniyi ezemez; replace öncesi hata eski geçerli dosyayı korur. |
| E29 P1 | Bilinmeyen gelecekteki şemayı reddet veya explicit migration uygula; `checkpoint_store.py:_from_dict`. | `tests/test_checkpoint_store.py`: desteklenen v1-v4 okunur, v999 sessiz bugünkü yapı sayılmaz; UI devam etmeme nedenini verir. |
| E30 P1 | Resume dış etkileri tekrar etmeden önce fresh observation zorunlu kıl; `engines/agent/plan_checkpoint.py`, `recovery.py`. | `tests/test_plan_resume.py`, `test_recovery.py`: dış işlem gerçekleşmiş/yerel cevap kaybolmuş fixture'da işlem ikinci kez yapılmaz; kanıt eskiyse yeniden okunur. |
| E31 P1 | Hata sınıflandırmasını metin eşleştirmeden structured error code'a yükselt; `recovery.py:classify_failure`, `core/failure.py`. | `tests/test_recovery.py`: kullanıcı metnindeki “permission” başarısızlığı yanlış permission yapmaz; gerçek timeout/contract/permission kodları tutarlı sınıflanır. |
| E32 P1 | Sağlık yoklamasını model başına paylaş ve maliyetini kaydet; `engines/agent/liveness.py`. | `tests/test_liveness.py`: 3 sessiz alt ajan bir ortak ping üretir; ping iptali ana çağrıyı iptal etmez; web modeli ping almaz. |
| E33 P1 | Capability probe kanıtına zaman, sürüm ve native doğrulama ekle; `engines/capability_probe.py`, `core/model_capability.py`, `providers/capabilities.py`. | `tests/test_capability_probe.py`, `test_capability_probe_wiring.py`: model sürümü değişince eski vision/tool kanıtı eskir; metin emülasyonu native sanılmaz; unavailable unknown kalır. |
| E34 P2 | Cost optimized'ı gerçek katalog fiyatı ve toplam görev maliyetiyle sıralandır; `core/routing_strategy.py`, `gateway/routing.py`. | `tests/test_routing_strategy.py`: ücretli ucuz model pahalıdan önce, fiyat bilinmiyorsa açık priority fallback; retry dahil toplam maliyet telemetride görünür. |
| E35 P1 | Agent loop'un değişmez güvenlik geçitlerini modüllere ayır; `engines/agent/loop.py` (3.605 satır), `execution_policy.py`, `turn_evidence.py`. | `tests/test_agent_loop.py`, `test_single_loop_routing.py`, `test_agent_completion_report.py`: refactor öncesi/sonrası aynı olay sırası ve stop reason; izin/doğrulama kapısını geçmeden success üretilemiyor. |

### Canlı doğrulama için dar kabul paketi

Uygulama sonrası önce yalnız ilgili unit dosyaları çalıştırılmalı; ardından secrets kullanmadan yerel fixture MCP ile connect/list/call/cancel/close senaryosu, sahte sağlayıcı ile interrupted turn + checkpoint resume senaryosu ve geçici çalışma klasöründe çakışan scope delegasyonu yapılmalı. OAuth ve gerçek sağlayıcı için ayrıca kullanıcının mevcut bağlantısında açıkça yetkilendirilmiş smoke run gerekir; bu kaynak incelemesi onların çalıştığını kanıtlamaz. Zamanlama kabulü duvar saati yerine fake clock ve barrier ile deterministik unit test; süreç sızıntısı kabulü ise yerel subprocess fixture ile runtime olmalıdır.

## Politika ve protokol notu

E01 bir Fusion politika güçlendirme önerisidir; mevcut read-first önceliği tek başına MCP standardı ihlali veya gerçek sömürü kanıtı değildir. Güncel Codex resmî belgesinde de read annotation önceliği anlatılır. Fusion için önerilen daha ihtiyatlı çelişki kararı compatibility testleri ve görünür politika açıklamasıyla uygulanmalıdır. E02 sıradan güvenilen okuma araçlarına gereksiz onay fırtınası üretmemeli. MCP 2026-07-28 geçişi ayrı sürüm matrisi/adaptör işidir; çalışan eski sunucuların initialize desteği kaldırılmaz.


---

Belge: `docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/03-kits-gorsel-uretimi.md`

# Fusion Kits ve görsel üretim: kaynak incelemesi

İnceleme salt okunur yapıldı; ürün dosyası değiştirilmedi, ağır test çalıştırılmadı, .env veya sır dosyası açılmadı. Aşağıdaki test isimleri doğrulama önerisidir; mevcut testlerin geçtiği iddia edilmiyor. Kökler: K = `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`, F = `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`. Kesin gözlem ile ürün fırsatı ayrı ifade edilmiştir.

## Güçlü taraflar

- Kits boş bir sohbet kabuğu değil: belge editörü, sayfa kitaplığı, bağlamlı sohbet, Kit karakterleri, görev kartları, ses ve bilgisayar çalışma alanı mevcut. `K/src/client/{SpaceWorkspace,PageDocument,Chat,ComputerPanel}.tsx` somut ürün yüzeylerini oluşturuyor.
- Belge kaydı sürüm denetimli: `editor/autosave.ts` expectedRevision, bekleyen kayıt, AbortController, timeout ve conflict durumunu yönetiyor; taslağı sessizce ezmiyor. `tests/autosave.test.ts`, `page-snapshots.test.ts` iyi genişletme noktaları.
- Sohbet bağlamı yüklenmeden gönderim engelleniyor; başlangıç istemi, tur hatası ve asistansız sonuç için kontroller var (`Chat.tsx`). Belge değişikliği `PageReviewCard` ile insan onayından geçiyor.
- Yerel bilgisayar köprüsü origin + event.source + nonce denetliyor; yalnız okuma için host iznine dayanıyor (`local-computer-bridge.ts`). Bilgisayar panelinde iptal ve lease/insan devralma kavramları var; yerel bilgisayar sınırları ayrı modüllerde ve testlerde işlenmiş.
- Anahtarsız yerel ses ve Realtime ses aynı CallView sözleşmesine uyuyor. Yerel ses cümle bazında konuşuyor, Kit konuşurken mikrofonu kapatıyor; kendi sesini kullanıcı sözü saymıyor.
- Görsel üretim masaüstü ve ajan tarafından aynı `providers/image_generation.py` çekirdeğini kullanıyor. NIM ve web üretimi ayrılmış, referans yeteneği açık, web oturumunda hesap bazlı kilit var.
- Görsel akışları DAG sıralaması, girdi imzasıyla gereksiz yeniden üretimi atlama, hedef dalı çalıştırma ve kısmi varyasyon başarısını koruma sunuyor. Galeri referansı sunucuda dizin sınırıyla denetleniyor; JSON akışı alan ve boyut limitleriyle temizleniyor.

## 35 uygulanabilir geliştirme

Öncelik P1 güvenilirlik/temel kullanım; P2 ürün derinliği; P3 ileri kullanım. Satırlar mevcut özelliğin yokluğunu tüm depoda kanıtlamak yerine incelenen yüzeydeki somut eksikliği veya geliştirme ihtiyacını belirtir.

| No | Öncelik ve iş | Kaynak / bulgu | Kabul ve test | Bağımlılık |
|---|---|---|---|---|
| K01 | P1 Sohbet eşitlemesinde gerçek sayfalama | `K/src/client/ThreadList.tsx` yalnız `local.map` çizer; remote fetchMore başlığı eşler, remote-only sohbeti çizmez. | İkinci sayfadaki remote-only sohbet görünür, aynı kimlik çift çizilmez; `tests/local-threads.test.ts` + yeni bileşen testi. | local/remote birleşik liste sözleşmesi |
| K02 | P1 Sohbet gönderiminde tekrar deneme | `Chat.tsx` kullanıcı mesajını ekleyip taslağı temizliyor; runAgent hatasında yalnız hata metni kalıyor. | Hatalı tur tek kullanıcı mesajıyla yeniden çalışır, istem ve kaynak korunur; `transcript.test.tsx`. | tur kimliği/idempotency |
| K03 | P1 Bağlam isteğinde iptal | `Chat.tsx` timeout var ama unmount yalnız active flag kullanıyor. | Sohbet değiştirme gerçek fetch'i abort eder; eski bağlam yeni sohbeti etkilemez; `page-context.test.ts`. | API AbortSignal mevcut |
| K04 | P2 Sohbet taslağını sakla | `Chat.tsx` draft/source yalnız React state. | Sohbet değiştirip dönünce gönderilmemiş metin geri gelir; yeni UI testi. | conversationId bazlı taslak deposu |
| K05 | P2 Kullanıcının yukarı okumasına saygı | `Chat.tsx` mesaj sayısında her zaman scrollIntoView. | Yukarı kayan kullanıcı yerinde kalır; yeni mesaj düğmesi aşağı götürür; transcript UI testi. | scroll konum ölçümü |
| K06 | P2 Bağlantı durumunu açıklama | `Chat.tsx` loaded, running, error ayrı; reconnect catch yerel seste yutuluyor. | Kesinti → yeniden bağlanma → hazır görünür; taslak korunur, iki transcript oluşmaz. | ortak connection state |
| K07 | P1 Sayfa yenilemelerini çakıştırma | `SpaceWorkspace.tsx` her 3 saniye timeout/abort olmadan load. | 10 saniyelik ağda aynı anda tek istek; alan değişince iptal; `page-snapshots.test.ts`. | tek uçuş/backoff |
| K08 | P2 Görünürlük bazlı yenileme | Aynı polling arka planda sürüyor. | Gizli sekmede yenileme durur, görünür olunca sürüm tazelenir. | visibilitychange veya olay akışı |
| K09 | P1 Alan değişince eski listeyi temizle | `SpaceWorkspace.tsx` pages/loaded alan değişiminde sıfırlanmıyor. | Yavaş B alanı yüklenirken A sayfaları B başlığı altında görünmez. | alan kimliğiyle cache/state |
| K10 | P1 Sayfa oluşturmayı tekilleştir | create() için pending engeli yok. | Hızlı çift tıklama tek sayfa yaratır; hata tekrar denemeye izin verir; `page-routes.test.ts`. | istem kimliği veya UI kilidi |
| K11 | P1 Kalıcı belge taslağı | `editor/autosave.ts` taslağı bellekte koruyor. | Kayıt hatası sonrası uygulama kapanıp açıldığında taslak geri gelir; `autosave.test.ts`. | revision bazlı yerel taslak |
| K12 | P2 Çatışmada karşılaştırma ve birleştirme | autosave conflict mesajı kopyalamayı öneriyor. | Kullanıcı yerel/uzak farkı görüp seçerek birleştirir; eski revision üzerine sessiz kayıt yok. | diff UI + revision sözleşmesi |
| K13 | P2 Belge sürüm geçmişi | mevcut Page snapshot güncel sürüme odaklı. | Kullanıcı önceki sürümü önizleyip yeni revision olarak geri alır; `page-service.test.ts`. | geçmiş depolama/migrasyon |
| K14 | P2 Kitaplık tercihini koru | `SpaceLibrary.tsx` layout/sort/query yerel state. | Alanlar arasında dönünce görünüm/sıralama geri gelir. | alan bazlı preferences |
| K15 | P2 Büyük kitaplık araması | SpaceLibrary tüm content üstünde her query değişiminde tarıyor. | 5.000 sayfada arama gecikmesi ölçülür; sunucu paginated search ve sonuç sayısı doğru. | index + search endpoint |
| K16 | P2 Türkçe arama tutarlılığı | `.toLocaleLowerCase()` ve localeCompare açık dil kullanmıyor. | I/ı, İ/i başlıkları Türkçe kuralla aranır/sıralanır; `library.test.ts`. | tr locale politikası |
| K17 | P2 Belge dışa aktarma paketi | `PageDocument` ve editor markdown mevcut; tam alan paketi ürün fırsatı. | Hiyerarşi ve ekler korunarak Markdown/HTML dışa aktarılır; `markdown.test.ts`. | dosya/asset manifest |
| K18 | P1 Yerel TTS hata görünürlüğü | `local-voice/useLocalVoice.ts` speak hatasını catch ile yutuyor. | TTS başarısızlığında altyazı korunur, ses sorunu ve tekrar seçeneği görünür; `local-voice.test.ts`. | ses motoru error sınıfları |
| K19 | P1 Ses turu iptali | Yerel utterance api çağrısı signal kullanmıyor; hangup cancelled flag ile sonuç atlıyor. | Arama bitince bekleyen HTTP iptal olur; arka planda tur üretmez veya sunucu iptal durumunu belirtir. | sunucu cancellation |
| K20 | P2 Ses kalite/erişilebilirlik ayarları | CallView mute, speaker mute, captions sağlar. | Kullanıcı motor, dil, hız, mikrofon seçimini değiştirir; seçilen motor görünür. | VoiceEngine capabilities |
| K21 | P2 Yerel seste söz kesme | Yerel engine yarım çift yönlü; speaking sırasında listen yok. | Güvenli barge-in düğmesi konuşmayı kesip yeni sözü başlatır; `local-voice.test.ts`. | engine.stopSpeaking desteği |
| K22 | P1 Arama bitişini dayanıklı kaydet | useLocalVoice keepalive fetch/end hataları bazı yollarda yutuluyor. | End kesintisinde pending receipt saklanır ve yeniden gönderilir; aynı çağrı iki kez kapanmaz. | receipt idempotency |
| K23 | P1 Bilgisayar sekmelerinde klavye modeli | `ComputerPanel.tsx` aria-selected sekmeleri var. | Ok tuşu, Home/End ve roving tabIndex ile tab/tabpanel bağları doğrulanır; `controls.test.tsx`. | ortak Tabs bileşeni |
| K24 | P2 Bilgisayar işlem geçmişi | Panel browser/files/shell eylemlerini ayrı sunuyor. | Son işlemler, hedef, sonuç, süre ve izin durumu sohbet/görevle ilişkilidir. | işlem olay şeması |
| K25 | P1 Host köprüsünde iptal | `local-computer-bridge.ts` 120 saniye timer ve message listener; çağıran signal yok. | Panel kapanınca listener temizlenir, host istek iptal bildirimi alır; `local-computer-bridge.test.ts`. | AbortSignal + host cancel protokolü |
| K26 | P2 Kits → ana galeri entegrasyonu | Kits belge/chat yüzeyleri ve F görsel çekirdeği ayrı; açık ortak asset sözleşmesi gerekli. | Sohbette üretilen görsel galeriye ve belgeye aynı assetId ile eklenir, path string taşınmaz. | host asset bridge |
| K27 | P1 Görsel başlangıç hatalarını göster | `F/app/src/imagecreate/ImageCreate.tsx` sağlayıcı/galeri/akış yükleme catch'leri undefined. | Ağ hatası boş sağlayıcı gibi görünmez; bölüm bazlı retry; `ImageCreate.test.tsx`. | typed load state |
| K28 | P1 Görsel işi iptal et | `akisCalistir.ts` request fn/seneklerde signal yok, UI çalışıyor bool. | Kullanıcı iptal eder, sonraki varyasyon başlamaz; üretilen dosyalar korunur. | RPC jobId + cancellation |
| K29 | P1 Akış doğrulamasını derinleştir | `image_flows.py::validate_flow` ids set yapıyor; duplicate ID ve döngü açıkça reddedilmiyor. | duplicate/self/cycle/non-finite koordinat server-side reddedilir; `test_image_flows.py`. | DAG doğrulayıcı |
| K30 | P1 Akış kaydını atomik yap | `save_flow` doğrudan write_text. | Kesilen yazım eski akışı bozmaz; temp + atomic replace; `test_image_flows.py`. | aynı dizinde geçici dosya |
| K31 | P2 Capability bilgisini UI'ya geçir | `ImageChoice.exact_size` var, `image_providers` yalnız referans döndürüyor. | Oranın tam ölçü mü istem önerisi mi olduğu seçimde açıklanır; `test_image_create.py` + UI. | capability schema |
| K32 | P2 Görsel soy ağacı ve yeniden üretilebilirlik | sidecar yalnız istem/sağlayıcı saklıyor; işlem, referans, oran ve seed yok. | Galeride kaynak/işlem/model/ölçü/seed/zaman görülebilir; yeniden kullanma aynı sözleşmeyi kurar. | metadata versioning; NIM seed açılımı |
| K33 | P2 Galeri yönetimi ve sayfalama | `list_gallery` tüm dizini tarıyor; ImageCreate tüm galeri state tutuyor. | 10.000 assette sayfalama, arama, silme/çöp kutusu; akış referansı silinmeden uyarı. | asset manifest/index + GC |
| K34 | P1 Görsel viewer odak yönetimi | ImageCreate viewer modal role/focus var; snippette focus trap/geri dönüş yok, img alt boş. | Tab modal dışına çıkmaz; kapanınca açan karta döner; anlamlı açıklama; UI accessibility testi. | ortak Dialog |
| K35 | P2 Kısmi varyasyon ve hesap kuyruğu | akisCalistir kısmi üretimi bitti+hata tutuyor, downstream ilk sonucu alıyor; web_image hesap kilidi bekliyor. | Eksik varyasyonu tamamla, kullanılan varyasyonu seç, hesap kuyruğu/süre aşımı görünür; akis testleri + `test_web_image.py`. | job progress + seçili asset alanı |

## Uygulama sırası ve risk

Önce 1–3, 7–11, 18–19, 25, 27–30, 34: veri kaybı, görünmeyen hata, gereksiz maliyet ve temel gezinme risklerini azaltır. Ardından 12–17, 20–24 ve 31–35 ürünün günlük kullanışlılığını artırır. 26 ortak asset kimliği ve host sözleşmesine bağlı olduğu için galerinin manifest tasarımıyla birlikte ele alınmalı. NIM dosyasındaki canlı ölçüm yorumları 29–30 Eylül 2026 tarihli kod kanıtıdır; güncel sağlayıcı erişimi, fiyatı veya kullanılabilirliği olarak sunulmamalı. Web selector kırılganlığı için kontrollü fixture ve kullanıcı hesabıyla isteğe bağlı smoke test tercih edilmeli; araştırma sırasında dış hesaba üretim isteği yapılmadı.


---

Belge: `docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/04-ortak-gelistirme-listesi.md`

# Ortak geliştirme listesi ve Fusion'a özgü ileri fikirler

Bu 40 madde **öneridir**. U/E/K maddeleriyle ilişkileri belirtilir; aynı iş iki kez yapılmaz. P0 kritik doğruluk ve veri koruma; P1 günlük profesyonel kullanım; P2 taban güvenilir olduktan sonraki ürün derinliği. Dosyalar Fusion CLI köküne göre verilmiştir; `Kits:` satırları kardeş fusion-kits deposudur. Önerilen yeni dosyalar açıkça “yeni” işaretlidir. Eşikler benchmark'tan önce uydurulmaz.

## A. Modeller, düşünme ve gerçek yetenek

### R01 — P0: Model seçiminin uygulanma makbuzu

**Durum:** Model seçici ve başarısız model değişimi testi mevcut; UI etiketinin bütün yüzeylerde gerçek seçime bağlılığı araştırılmalı. **İş:** seçim isteği pending; sonuç başarılıysa seçimi güncelle, başarısızsa önceki model ve taslak korunsun. **Sahip:** `app/src/sessions/useSessions.ts`, `app/src/screens/ModelPicker.tsx`, `src/fusion_cli/appserver/model_catalog.py`. **Kabul:** geciken A seçimi ardından B seçimi olduğunda A sonucu B'yi ezmez; reddedilen model görünürde etkinleşmez. **Test:** mevcut useSessions/ModelPicker testleri + istek sıralama fixture'ı. **İlişki:** U26–U30; ortak model paketi.

### R02 — P0: İstenen/gözlenen/fallback modeli aynı kartta

**Durum:** `ModelFallbackActivated` ve sonuçta gözlenen model bilgisi var. **İş:** bunları App, CLI ve Kits'te aynı kısa makbuza dönüştür: “İstenen … / Kullanılan … / Geçiş nedeni …”. Bilinmeyene “doğrulanamadı” yaz. **Sahip:** `core/events.py`, `core/types.py`, `app/src/protocol/olayAkisi.ts`; Kits `TaskPresentation.tsx`, Fusion event adapter'ı. **Kabul:** Gemini Pro→Flash geçişi görünür; anonim oturum premium sanılmaz; her token için aynı bildirim tekrar basılmaz. **Test:** olay replay + sağlayıcı fake. **İlişki:** E33.

### R03 — P1: Model yetenek ve kanıt rozeti

**İş:** tools(native/emulated/unknown), vision, reasoning, image edit ve context bilgisini kaynak/tarih ile göster. Görseli göremeyen modelin yanına “görsel girdisi doğrulanmadı” açıklaması koy. **Sahip:** `core/model_capability.py`, `engines/capability_probe.py`, `appserver/model_catalog.py`, `ModelPicker.tsx`. **Kabul:** unknown yanlışlıkla false/verified'a dönmez; model adı benziyor diye yetenek kopyalanmaz. **Test:** capability probe + katalog + UI. **İlişki:** E33, K31.

### R04 — P1: Sağlayıcıya özgü thinking seçenekleri

**İş:** genel düşünme düğmesi yerine kanıtlı supported effort değerleri göster; görüntüleme tercihini ayrı tut. **Sahip:** `core/model_capability.py`, `core/types.py::CompletionRequest`, config/provider adapter'ları; `settings/sections/Models.tsx`, composer. **Kabul:** desteklenmeyen effort gönderilmez; yeni seçilen model eski effort'u desteklemiyorsa açık düşürme/varsayılan mesajı; busy turun effort'u değişmez. **Test:** request fixture'ında native API parametresi, web/template ayrımı. **İlişki:** U30. Bu özellik eski kaldırılma kararını gerekçeli şekilde yeniden değerlendirir.

### R05 — P1: Model bağlama için tek bağlantı yolculuğu

**İş:** katalogdan “bağlan” seçilince gerçek sağlayıcı ekranına git; bağlama → giriş → küçük gerçek yanıt → araç ölçümü ayrımını sun. **Sahip:** `providers/web_control.py`, `appserver/accounts.py`, `app/src/account`, `control`, model picker. **Kabul:** yalnız profil klasörü bulundu diye bağlı sayılmaz; pencere açıldıysa gerçekten görünür mü kontrol edilip status anlaşılır gösterilir; hesabı değiştirince doğru profil kullanılır. **Test:** user-visible login lifecycle fake + gerçek pencere smoke. **İlişki:** U04/U06/U29; bu oturumda yaşanan görünür pencere sorunu kabul vakasıdır.

### R06 — P2: Kullanıcı görev profilleri

**İş:** “Hızlı günlük iş”, “Dengeli üretim”, “Derin inceleme” profilleri model kimliği, effort ve bütçenin gerçek bileşimleri olsun; varsayılan ücretsiz rota korunsun. **Sahip:** mevcut config tier/router, `settings/sections/Models.tsx`. **Kabul:** profil açıklaması gerçek ayarı gösterir; “derin” etiketi salt farklı renge dönüşmez; kullanıcı özel model seçimi ezilmez. **Test:** config roundtrip ve request snapshot. Model/limit sayıları ölçüm ve kullanıcı tercihiyle belirlenir.

## B. Sohbet, iş yürütme ve güven

### R07 — P0: Sürümlü olay projection'ı

**İş:** gerçek core olaylarını sunum durumuna çeviren tek reducer/adaptör kullan; schemaVersion ve session/turn/event kimliği eklemeyi mevcut protokol uyumuyla tasarla. **Sahip:** `core/events.py`, `appserver`, `app/src/protocol/{types,olayAkisi}.ts`; Kits event adapter. **Kabul:** duplicate replay aynı kartı ikinci kez oluşturmaz; geç olay başka sohbete yazılmaz; tanınmayan additive alan crash üretmez. **Test:** sırası bozuk/tekrarlanan stream fixture'ı. **İlişki:** U24, K02/R08. Yeni paralel event bus kurulmaz.

### R08 — P0: Gönderim makbuzu ve tekilleştirme

**İş:** kullanıcı mesajı queued/accepted/running/failed/cancelled durumunu korusun; yeniden gönderim aynı requestId ile kontrollü yürüsün. **Sahip:** useSessions, Composer, appserver session; Kits Chat ve local threads. **Kabul:** bağlantı kaybında taslak ve ekler kaybolmaz; hızlı iki Enter tek görev oluşturur; tekrar dene iki kullanıcı mesajı üretmez. **Test:** UI→host protokol fixture'ı. **İlişki:** U11/U17, K02/K04.

### R09 — P1: Çalışırken düzeltme mesajı

**İş:** “Şunu da ekle”, “bunu yapma”, “durum ne” ve bağımsız yeni iş farklı semantics ile kuyruğa alınsın; kullanıcı sıradaki işlemi görebilsin. **Sahip:** useSessions, `engines/agent/loop.py`, `appserver/session.py`. **Kabul:** durum sorusu aktif işi iptal etmez; durdur açıkça iptal eder; düzeltme uygulanmadan dış etki başlamaz. **Test:** fake provider barrier ile mid-turn steering. **İlişki:** U17/E18.

### R10 — P0: Durdurma makbuzu

**İş:** cancel requested→cleanup→cancelled veya cancel_failed ayrımı, owned işler listesi. **Sahip:** appserver/session, tools/jobs, provider çağrıları, MCP pool, UI activity. **Kabul:** düğme kaybolduğu halde render/MCP işi sürüyorsa “iptal edildi” yazmaz; tamamlanmış dosyalar korunur; parent cancel bağımsız başka sohbeti kapatmaz. **Test:** subprocess + provider/MCP timeout fixture'ı. **İlişki:** E07/E11, K19/K25/K28.

### R11 — P1: Kanıta bağlı teslim kartı

**İş:** gerçek changed paths, artefakt, doğrulama kontrolü, açık bulgu ve gerçek model tek kapanış kartında. **Sahip:** mevcut `TurnOutcome`, `FilesChanged`, `core/artifacts.py`, completion report, Conversation. **Kabul:** “dosya oluşturuldu” için mevcut dosya; “test geçti” için doğru exit/rapor; partial görünür; eksik screenshot'a görsel onay yazılmaz. **Test:** `test_agent_completion_report.py`, `Conversation.test.tsx`. **İlişki:** U21/U23; ürün kalitesi artar, modelin diliyle kapı aşılmaz.

### R12 — P1: Kanıt ekranı ve önce/sonra

**İş:** dosya diff'i, web önce/sonra görüntüsü, video seçili kareleri, oyun gerçek kontrol sonucu teslimin yanında açılır. **Sahip:** mevcut workspace ChangesPanel/PreviewPanel, artefact provenance. **Kabul:** screenshot kaynak/viewport/zaman taşır; başka görev görüntüsü bu işe atanmaz; açılması hata verirse tekrar yolu. **Test:** workspace visual/evidence fixture. **İlişki:** R11 ve önceki site menü ürün kapısı.

### R13 — P1: Uzun iş zaman çizelgesi

**İş:** plan adımları, araçlar ve onarım denemelerini kısa faz başlığıyla sun; kullanıcı ayrıntı açabilir. **Sahip:** ExecutionStep* olayları, Conversation/ActivityLine, Kits TaskPresentation. **Kabul:** polling ilerleme sayılmaz; bekleyen provider için sahte yüzde yok; tekrar deneme nedeni gerçek kayıt. **Test:** repair ledger replay + UI. **İlişki:** E31 ve mevcut repair_flow.

### R14 — P0: Güvenilir geri dönüş ve devam ekranı

**İş:** kaldığın yer, tamamlanan adım, değişen kaynak ve artık yeniden doğrulanması gereken kontrol açık gösterilir. Kod geri alma ile konuşma geri alma ayrıdır; dış MCP etki geri alınmış gibi gösterilmez. **Sahip:** checkpoint store/plan_checkpoint, history dialogs. **Kabul:** yeniden açılınca kayıp iş bulunur; kaynak değiştiyse ilgili adıma döner; dış gönderim ikinci kez yapılmaz. **Test:** checkpoint/resume + app restart fixture. **İlişki:** E27–E30.

### R15 — P1: Soru kalitesini ölçme

**İş:** gerekli soru, isteğe bağlı tercih, tekrar soru ve gereksiz soru ayrı analiz edilir. Soru sırasında bağımsız işler sürebilir; bağımlı iş bekler. **Sahip:** clarify, engine_tools, Approval, question protocol. **Kabul:** önceden verilen teknoloji tercihi tekrar sorulmaz; eksik hedef hesap varsa dış yazma başlamaz; kullanıcı “sen seç” dediğinde gerekçeli varsayımla ilerler. **Test:** aynı konuşmada 3-turn question fixtures. **İlişki:** E20–E22/U33.

### R16 — P1: Bağlam kaynakları görünümü

**İş:** bu turda kullanılan proje talimatı, skill, dosya, geçmiş ve ders adlarını göster; özel içerik varsayılan açılmaz. **Sahip:** ContextGauge, capabilities, memory, turn report. **Kabul:** bağlama hiç eklenmeyen dosya “kullanıldı” sayılmaz; kapsam ve kaynak çakışması açıklanır. **Test:** prompt assembly metadatası, içerik sızmama. **İlişki:** E23–E26.

## C. MCP, skill ve agent ürün deneyimi

### R17 — P1: Bağlayıcı sağlık merkezi

**İş:** kurulu, yapılandırılmış, giriş gerekli, bağlı, kısmen kullanılabilir, hata ayrımı; gerçek list/call kanıtı ve son denetim zamanı. **Sahip:** mcp_bridge/service/pool + app connectors/control. **Kabul:** bir bozuk sunucu diğer kartları kırmaz; hata kopyalanabilir ama token yok; tekrar bağlan eylemi çalışır. **Test:** fixture MCP ve connectors UI. **İlişki:** E03–E08.

### R18 — P1: Araç kataloğu ve neden seçildi

**İş:** araç adı yanında insan açıklaması, giriş örneği, etki ve kullanılabilirlik; agent seçme gerekçesi yalnız gerçek routing kaydından. **Sahip:** tools registry/capabilities, connectors, ActivityLine. **Kabul:** tool schema değil sade açıklama varsayılan; aynı isim farklı origin ayrılır; yanlış araç adı önerisi gizlice broad yetki açmaz. **Test:** tool discovery collisions. **İlişki:** E24/R16.

### R19 — P0: Origin, version ve trust bilgili skill

**İş:** yerel/proje/plugin/MCP kökenini göster; aynı ad çakışmasında sessiz shadow yok; remote skill izin genişletemez. **Sahip:** tools/capabilities, config skill loader, SkillsCatalog. **Kabul:** iki origin aynı skill adıyla ayrı; uzak allowed-tools yazısı parent yetkiyi genişletmez. **Test:** yükleyici collision ve scope fixtures. **Kaynak:** [Agent Skills formatı](https://agentskills.io/specification), [MCP Skills extension](https://skills.extensions.modelcontextprotocol.io/specification/stable/skills).

### R20 — P1: Çalışan skill'in görünür makbuzu

**İş:** hangi skill ne zaman yüklendi, hangi adımlar uygulandı, tamamlanma kontrolü ne oldu; katalog açıklamasına bakılması invocation sayılmaz. **Sahip:** capabilities/expertise olayları + Conversation/SkillsCatalog. **Kabul:** skill kullanılmadıysa “kullandım” kartı yok; referans okunurken ana skill baştan tekrar yüklenmez. **Test:** lazy-load ve replay. **İlişki:** E25/R16.

### R21 — P1: Uzman ekip gözlem ve sahiplik

**İş:** ajan başına görev, dosya alanı, durum, gerçek sonuç ve birleştirme kontrolü; kullanıcı çocuğu durdurabilir. **Sahip:** team.py, subagent cards, Kits task UI. **Kabul:** ana/alt sonuç karışmaz; bir çocuğun hatası bağımsız başarıyı silmez; aynı dosyaya paralel yazma engellenir. **Test:** team + UI gerçek event fixture. **İlişki:** E09–E14.

### R22 — P2: Kanıtlı öğretmen/çırak açıklaması

**İş:** öğretmene neden başvuruldu, hangi kısım çırak tarafından yürütüldü, doğrulama sonucu ve kotaya etki sade gösterilir. **Sahip:** teacher_flow/apprentice_handoff, model event report. **Kabul:** öğretmen hiç çağrılmadıysa öğretmen rozeti yok; öğretmen ret verince sonuç başarılı sanılmaz; sırlar aktarılmaz. **Test:** fake teacher on/off/fail. **İlişki:** R02/R11.

### R23 — P2: Ders kalitesi ve geri alma

**İş:** başarılı gerçek ölçümden ders; kullanıcı “bu yanlış” dediğinde kapsamlı invalidation ve yeniden doğrulama. **Sahip:** memory ders depoları, `settings/MemoryPanel.tsx`. **Kabul:** hatalı ders sonraki görevde önerilmez; kullanıcı tercihi ve ders karıştırılmaz; silme/geri alma saklama politikasına uygun. **Test:** memory ranking + learning acceptance. **İlişki:** R22.

### R24 — P2: Görev reçeteleri

**İş:** “Site kopyala”, “Video hazırla”, “Reklam hesabını incele”, “Uygulama düzelt” reçeteleri gereken araç, çıktı ve kabulü önden kurar. Sadece örnek prompt değildir. **Sahip:** mevcut config skills/templates ve UI EmptyState. **Kabul:** site için gerçek etkileşim/viewport, video için render, reklam için hesap/read permission kontrolü; reçete tek siteye hardcode edilmez. **Test:** recipe contract + production suite. **İlişki:** R11/R20.

## D. Kits, görsel ve çoklu çıktı

### R25 — P1: Ortak artefakt kimliği

**İş:** main chat/Kits/galeri aynı assetId ve sürümlü metadata referansını kullansın; path güvenli host tarafından çözülsün. **Sahip:** core/artifacts, image_create, library, Kits api/host bridge. **Kabul:** aynı görsel üç yerde üç kopya sayılmaz; referans silinince broken state; kök dışı path reddedilir. **Test:** integration manifest fixture. **İlişki:** K26/K32/K33.

### R26 — P1: Görsel üretim için basit/ileri katman

**İş:** ilk ekran prompt+referans+oran+üret; ileri panelde DAG, varyasyon, seed destekliyorsa seed, sağlayıcı. **Sahip:** ImageCreate/AkisTuvali/akis, sağlayıcı capability. **Kabul:** ilk üretim akış node kurmadan yapılır; edit için hedef açık; desteklenmeyen seed/ratio exact gibi sunulmaz. **Test:** ImageCreate/akis UI. **İlişki:** K27–K35.

### R27 — P1: Referans seçimini kesinleştir

**İş:** “Bu görseli düzenle” tek asset'i işaretler; birden fazla referans açık sıra/rol taşır. **Sahip:** image tools/create/provider + galeri viewer. **Kabul:** son konuşma görseli yanlışlıkla başka asset yerine kullanılmaz; hedef kayıpsa yeni üretim diye devam edilmez. **Test:** image reference resolver. **İlişki:** R25/K32.

### R28 — P2: Görsel yorum ve sürüm karşılaştırma

**İş:** seçili alana yorum, önce/sonra slider, varyasyon seçimi ve “bunları koru” kontrolü. **Sahip:** mevcut viewer üstüne yeni annotation adapter; asset lineage. **Kabul:** yorum doğru asset/revision/koordinata bağlı; zoom sonrası koordinat kaymaz; maske desteklenmiyorsa bölge ipucu diye açıklanır. **Test:** projection/keyboard/browser zoom. **İlişki:** R25/K34.

### R29 — P1: Görsel kalite teslim kapısı

**İş:** gerçek dosya açılabilirlik, boyut/alpha, istenen referans/edit yeteneği, kısmi batch ve kullanım amacı. **Sahip:** image_generation, image_create, mevcut galeri metadata. **Kabul:** HTML login ekranı .png diye kaydedilmez; üretim metni dosya kanıtı olmaz; şeffaflık istenip yoksa açık bulgu. **Test:** bozuk MIME/header/partial provider fixtures. Kaliteye ilişkin semantik yargı görsel inceleme ile ayrı yapılır.

### R30 — P1: Kits aynı görevin devamı

**İş:** masaüstü sohbetinden Kits belgeye geçince proje, görev ve çıktı kimliği korunur; host sözleşmesi capability sürümünü taşır. **Sahip:** prepare-kits/runtime bridge, Kits FusionPanel/PageConversation. **Kabul:** yanlış host sürümünde anlaşılır sınır; çift sohbet oluşmaz; iş sürerken yüzey değiştirmek iptal değildir. **Test:** packaged host fake + gerçek bundled smoke. **İlişki:** K01–K06/R07/R25.

### R31 — P1: Belge değişikliğini somut incele

**İş:** agent önerisi önce draft patch, expectedRevision, diff ve apply sonucu. Kullanıcı düzenlemesiyle çatışınca birleştirme. **Sahip:** PageReviewCard/PageDocument/editor autosave; page services. **Kabul:** onay eski revision'a uygulanmaz; failed save “uygulandı” olmaz; local draft restart'ta kurtarılır. **Test:** concurrent user edit + agent patch. **İlişki:** K11–K13.

### R32 — P1: Sesin metinle aynı işlem otoritesi

**İş:** sesli soru/onay doğru questionId ve task'a bağlı; transcription belirsizse dış etki yok; TTS hatası text'i silmez. **Sahip:** main voice ask bridge, Kits local voice, appserver/session. **Kabul:** gecikmiş “evet” yeni soruyu onaylamaz; mikrofon red durumunda UI açılır; hangup işi gerçekten iptal/kapat durumuna getirir. **Test:** ses engine fake + gerçek mikrofon smoke. **İlişki:** K18–K22/E18/U33.

## E. Güvenilir dağıtım ve ileri fikirler

### R33 — P0: Alt proje runtime sözleşmesi

**İş:** main App Node22, Kits kendi scriptinin Node24 hattı, Python venv ve packaged runtime ayrı doğrulanır; doctor farkı açık söyler. **Sahip:** app/package.json, desktop_build, Kits kits-start/check/doctor scriptleri. **Kabul:** global Node26 varlığında doğru test komutu seçilebilir; yanlış sürüm sessizce test fırtınası üretmez; paket sistem Python'u varsaymaz. **Test:** runtime command resolver + clean install. Bu oturum ölçümü doğrudan gerekçe.

### R34 — P1: Destek paketi ve teşhis

**İş:** son iş durumu, sürüm, hata kodu, bağlı yetenek sağlık özeti; kullanıcı önizleyip dışa aktarır. **Sahip:** mevcut doctor/log/diagnostics + settings advanced. **Kabul:** API anahtarı/çerez/prompt tamamı yok; destek paketi offline açılır; hata nedeni kopyalanabilir. **Test:** credential-shaped sentinel redaction ve export. Her uygulama kullanıcısının dosyasını otomatik maskeleme ürün kararıyla karıştırılmamalı; bu madde teşhis çıktısına ilişkindir.

### R35 — P1: Aynı UI bileşen sözleşmesi

**İş:** Dialog, Tabs, Toast, async-state, ErrorCard, ResultCard token ve davranış katalogu; App/Kits adaptörleri. **Sahip:** mevcut app ui/theme + Kits generated CSS. **Kabul:** focus trap, odak iadesi, hata/retry, dar ekran ve dark/light bütün yüzeylerde aynı; varsayılan tarih/para gösterimi bilinmeyeni uydurmaz. **Test:** mevcut visual suite genişletme, WCAG manuel checklist. Büyük tüm-UI rewrite değil, ihtiyaç çıktıkça taşıma.

### R36 — P2: Göstererek skill çıkarma

**İş:** kullanıcı bir görev akışını gösterir; Fusion adımları önerilen skill taslağına dönüştürür, değişken girdiler ve kabul testi çıkarır. **Sahip:** browser/task evidence + mevcut skill authoring. **Kabul:** şifre/çerez skill içine girmez; kaydetmeden içerik kullanıcıya görünür; tek örnek her sitede çalışır iddiası olmaz. **Test:** sanitize + template generalization. Önce R19/R20 gerektirir.

### R37 — P2: Görev için güvenli prova

**İş:** değiştirici MCP/web işinde taslak ve beklenen etkiyi göster; dry-run desteklemiyorsa “prova yapılmadı” de. **Sahip:** mevcut approval preview/effect workflow. **Kabul:** read-only preview dış gönderim yapmaz; gönderim için aynı taslak/hash ve hedef gerekir; input değişince yeniden preview. **Test:** effect fixture/idempotency. Adım sayısını büyütmeden son eylemi anlaşılır kılar.

### R38 — P2: İşe göre uzman kurul

**İş:** gerektiğinde bir uzman üretir, başka uzman gerekçeli kontrol eder; bütün görevlerde çoklu model açılmaz. **Sahip:** mevcut fusion engine/council, team, teacher bütçe. **Kabul:** taslak/inceleme/final ayrı; disagreement görünür; maliyet/süre bütçesi aşılmaz; araçsız reviewer mutation agent olmaz. **Test:** judge fail/disagreement + budget. Tarihsel çok motorlu arena ertelenmişti; önce kullanıcı günlük ana agent deneyimi tamamlanır.

### R39 — P2: Sessiz sürekli işler

**İş:** mevcut scheduler sürekli işi hedef/çıkış koşulu/checkpoint ile yürütür; değişmeyen durumda spam yok. **Sahip:** mevcut schedule/continuous task yapıları + Kits scheduled bridge. **Kabul:** kullanıcı durdurunca yeniden dirilmez; aynı olay iki teslim oluşturmaz; anlamlı değişimde bildirim ve kanıt gelir. **Test:** fake clock + restart + duplicate delivery. Yeni ikinci scheduler kurma.

### R40 — P2: Kullanıcıya özel ölçülen yönlendirme

**İş:** görev türüne göre gerçek geçmiş başarı/gecikme/yeniden deneme bilgisiyle önerilen ücretsiz model; kullanıcı override korunur. **Sahip:** existing routing_strategy/health/usage + lesson evidence. **Kabul:** üç iyi örnekten kesin üstünlük iddiası olmaz; unavailable ayrı; model değişimi görünür; bilinmeyen maliyet sıfır diye optimize edilmez. **Test:** recorded anonymized stats/fake clock. Önce R02/R03/E34 ve yeterli benchmark.


---

Belge: `docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/05-kabul-senaryolari.md`

# Kabul senaryoları ve gerileme kapısı

Bu matris görev listesinden bağımsız ikinci bir test harness'i istemez. Mevcut `tests`, `app/e2e`, Kits tests/smoke ve `evals/suite/production.yaml` genişletilir. Her senaryo test türünü ve kullanıcı kanıtını ayırır. Yeni test dosyası önerileri uygulanmış dosya diye sunulmaz.

## Deterministik regresyonlar

| ID | Kullanıcı/hata akışı | Kesin beklenen davranış | Kanıt ve mevcut genişletme noktası |
|---|---|---|---|
| A01 | Depolama erişimi reddedilmiş yeni kurulum | App açılır; onboarding tamamlanabilir; depolama sorunu anlaşılır | App/Onboarding tests; Storage fake SecurityError |
| A02 | Kaynak keşfinin biri fail, diğeri başarılı | Başarılı kaynak korunur; hata ayrı; bilinmeyen count uydurulmaz | SessionApplication onboarding integration |
| A03 | Sağlayıcı anahtarı var fakat yanıt yok | Yapılandırıldı gösterilir; doğrulandı gösterilmez | account/control tests + provider fake |
| A04 | Gönderirken bağlantı kopar | Metin/ekler korunur; retry tek task/user message | Composer/useSessions + transport fixture |
| A05 | İki hızlı Enter veya retry | Bir görev; accepted receipt aynı kimlik | client/server idempotency fixture |
| A06 | Uzun turda başka sohbete geçiş | İki sohbet state'i ayrıdır; geç sonuç eski sohbete | useSessions + event replay |
| A07 | Turda yeni düzeltme veya durum sorusu | Düzeltme uygun sınırda uygulanır; status eski işi silmez | agent_loop fake barrier |
| A08 | Onay kartına çift tık | Bir yanıt ve bir executor etkisi | Approval + appserver request fixture |
| A09 | İlk soruya Diğer metni, sonra ikinci soru | Eski metin ikinci soruda yok; yanlış key eski kararı taşımaz | Approval.test.tsx |
| A10 | Onaydan sonra hedef/argüman değişir | Eski onay yeni scope'u yetkilendirmez | agent_approval tests |
| A11 | Onay beklerken stop; geç evet | Araç çalışmaz; geç yanıt yeni soruyu onaylamaz | question lifecycle + agent_loop |
| A12 | Model listesi ağ hatası | Empty değil hata/retry; önceki etkin model korunur | ModelPicker/useSessions/model_catalog |
| A13 | A model seçimi yavaş, ardından B hızlı | Son seçim B; A response B'yi ezmez | model selection request ordering |
| A14 | Pro istenir; Flash gerçek cevabı verir | Requested/observed/fallback görünür; Pro başarı iddiası yok | core events/provider fake + UI |
| A15 | Desteksiz thinking effort | Adapter'a geçersiz parametre gitmez; seçici doğru seçenek | CompletionRequest/provider contract |
| A16 | Araç emülasyon eval başarısız | Sohbet olabilir, mutation agent görevi açılmaz | tool policy/capability probe tests |
| A17 | Bir MCP asılı, bir MCP sağlıklı | Sağlıklı araç hazır; asılı servis hata ve yeniden dene | mcp_pool fixture |
| A18 | MCP annotation çelişkisi/güvenilmeyen origin | Belirlenen Fusion politikası uygulanır; prompt izin genişletemez | tool_effect + approval + trust tests |
| A19 | OAuth refresh paralel çağrı | Tek refresh; bekleyenler doğru sonuç; token log yok | oauth fake transport |
| A20 | Alt ajan scope alias/symlink | Gerçek aynı dosyaya eşzamanlı yazma yok; root escape reddi | team tests tmp_path |
| A21 | Bir alt ajan exception | Bağımsız başarı korunur; her ajan terminal durum alır | team TaskGroup fake |
| A22 | Aynı bitmiş job tekrar sorgulanır | Onarım hakkı/deneme/ilerleme iki kez artmaz | repair_ledger/repair_flow/jobs |
| A23 | Checkpoint eşzamanlı save veya yazımda crash | Eski geçerli snapshot korunur; stale revision reddi | checkpoint_store fault injection |
| A24 | Dış işlem gerçekleşmiş, cevap kaybolmuş; resume | Önce dış durumu doğrular; otomatik duplicate write yok | recovery OBSERVE_FIRST fixture |
| A25 | Kits A alanından yavaş B alanına geçiş | A sayfaları B adı altında gösterilmez; stale fetch iptal | SpaceWorkspace/page tests |
| A26 | Belge kaydı fail; uygulama restart | Taslak kurtarılır; expectedRevision conflict görünür | autosave+page service |
| A27 | User belgeyi düzenlerken agent patch gelir | Eski revizyon sessiz ezilmez; diff/merge incelemesi | PageReviewCard integration |
| A28 | Görsel load fail | Hata/retry; boş galeriyle karıştırılmaz | ImageCreate.test.tsx |
| A29 | Akış duplicate id/self-cycle/cycle/NaN | Server reddeder; dosyaya bozuk akış yazılmaz | test_image_flows.py |
| A30 | Görsel batch ortasında stop veya üçüncü çıktı fail | Sonraki işler başlamaz; ilk doğru çıktılar korunur; partial | akis tests + provider fake |
| A31 | Görsel edit target kayıp | Yanlış görsel veya yeni üretimle sessiz devam yok | image reference resolver |
| A32 | TTS fail, geç sesli evet, hangup | Text korunur; doğru questionId; owned call kapanır | main voice/Kits local-voice tests |
| A33 | Dark/light, dar ekran, sadece klavye | Odak görünür; modal trap/return; tüm kontroller erişilebilir | app/e2e+Kits controls manual audit |
| A34 | Eski istemci/yeni çekirdek ve tersi | Additive alan tolere; unsupported action açık hata; veri bozulmaz | protocol compatibility fixture |
| A35 | Paket sistem Python/Node yokken açılır | Paketli runtime doğru bulunur; çalışan sohbet/ayarlar/çıktı | runtime smoke + clean profile |

## Gerçek kullanıcı kabulü

Canlı model çağrıları ücret/kota tüketebilir; mevcut kullanıcı yetkisi ve bağlı sağlayıcıyla yalnız görev için gereken dar smoke yapılır. Ödeme/yayın gibi dış etkiler yerine güvenli taslak veya yetkili test ortamı kullanılır. Bunlar otomatik olarak onaylanmış production işlemi anlamına gelmez.

| ID | Gerçek görev | Teslim şartı |
|---|---|---|
| L01 | Yeni Mac'te ilk Fusion açılışı | Terminal komutu gerektirmeyen kurulum; gerçek sağlayıcı yanıtı; kullanılabilir modeller; projesiz sohbet |
| L02 | Günlük çok turlu planlama | Önceki tercihleri korur; anlamlı soru; kaynaklı araştırma; açık belirsizlik; gereksiz araç/prompt tekrarları yok |
| L03 | Mevcut projede gerçek bug düzeltme | Önce bug üretimi; değişiklik; test; diff; başarısız test varsa partial; kullanıcı değişikliklerini koruma |
| L04 | MCP iki farklı sunucu | connect/list/read; güvenli taslak write preview; biri kesilince diğeri işler; izin doğru hesap/target |
| L05 | Skill seçerek belge veya rapor üretme | Skill gerçekten okunur; çıktı gerçek dosya; açılır; kalite kontrol; kaynak listesi |
| L06 | Uzun görev + uygulama kapanması | Checkpoint bulunur; devam kaydı; yapıldığı doğrulanmış dış iş tekrar edilmez; draft kaybolmaz |
| L07 | Kits sohbet → belge → kullanıcı düzenlemesi | Tek bağlam; doğru diff; save receipt; conflict çözümü; app restart sonrası korunma |
| L08 | Yeni görsel + referansla düzenleme | Doğru asset; gerçek provider; tüm çıktı gallery; viewer; ölçü/alpha; kısmi batch görünür |
| L09 | Site klonu | Ana/kategori/ürün/sepet gibi brief'teki sayfalar; menü/sekme/ok ve mobil; source aynı viewport kıyası; tek site hack yok |
| L10 | Oyun üretimi | Gerçek başlatma, kontrol, pause, gameover, restart; varlık yükleme; oynama ve screenshot; current failures çözülmüş |
| L11 | Remotion ve animasyon | Gerçek render/kareler; metin taşması/boş son bölüm yok; hareket amaca uygun; reduced motion |
| L12 | Mikrofon, yerel ses ve tarayıcı | Gerçek cihaz izinleri; duyulur TTS; yanlış question onayı yok; stop/insan devralma; profile görünür |

Her canlı koşu klasörü: brief, başlangıç revision/manifest, config'in sır içermeyen özeti, requested/observed model, task/event kimlikleri, tool receipt, exit/acceptance raporu, screenshot/çıktı ve açık bulgu. Ham token/çerez kaydı yok. Kanıt özel proje verisi içeriyorsa paylaşılmadan kullanıcı kontrol eder.

## UI doğrulama çalışma kartı

Mevcut screenshot'lar otomatik onaylanmaz. Güncel fixture'ı güncellemeden önce eski davranışın neden farklı olduğuna karar kaydı yazılır. Native Tauri smoke ile fixture UI görsel testi ayrı tutulur.

- Görünümler: ilk açılış, projesiz boş sohbet, proje boş sohbet, çalışan tur, bekleyen soru, işlem onayı, partial teslim, crashed runtime, model listesi hata, MCP degraded, görsel partial, Kits conflict.
- Temalar: açık/koyu/sistem. Geniş pencere ve dar pencere. Metin ölçeği/zoom ile kontrol taşması.
- Klavye: bütün akış Tab/Shift+Tab; popup ok/Home/End/Escape; modal odak ve dönüş; normal composer IME Enter koruması.
- VoiceOver: ekran/denetim isimleri; tek status duyurusu; her token'ı okuyan live region yok.
- Görsel kalite: aynı spacing/token; tekrar eden footer/metin gürültüsü yok; blank inspector gerektiğinde kapalı; disabled kontrol nedeni açıklanır.

## Yayın engelleri

Aşağıdakiler test edilen kapsamda bir kez bile oluşursa o paket yayın kapısını geçmez: veri kaybı, yanlış hesaba iş, onaysız/duplicate destructive etki, başarısız sonucu tamamlandı gösterme, yanlış görseli düzenleme, bozuk checkpoint ile sessiz devam. Sağlayıcı erişimsizliği açık hata ise ürün crash ile aynı kategoride sayılmaz; fakat kullanıcıya gizlenemez.

Performans eşiği önce ölçülür. Büyük sohbet/galeri/kitaplık fixture'ında ilk yükleme, input tepki süresi, bellek, stream frame ve yeniden bağlanma kaydedilir. Önce veriyi toplayıp sonra sürümler arasında karşılaştırın; tahmini yüzdeyle parite ilan etmeyin.


---

Belge: `docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/07-kaynak-ve-karar-defteri.md`

# Kaynak, karar ve bağımsız inceleme defteri

## Kanıt sınıfları

- **Ölçülen:** bu oturumda App Node22 testleri, App/Kits TypeScript, Python tam koşunun üç hatası, gerçek Gemini OK ve fallback.
- **Kaynakta görülen:** U/E/K incelemeleri; kaynak ve test tanımı, runtime başarı iddiası değil.
- **Görsel araştırma:** mevcut depoda kaydedilmiş screenshot fixture'larının gözle incelenmesi; yeni canlı ekran değil.
- **Dış resmî kaynak:** aşağıdaki belgeler 12 Ekim 2026 tarihinde açılarak kontrol edildi. Kaynak erişimi ürün aboneliği/yetenek erişimi kanıtı değil.
- **Öneri:** R listesi, paket planı, yeni interface alanları ve aşağıdaki ürün kararları. Bunlar kullanıcının geçmişte söylediği kararlar diye sunulmaz; araştırmacının uygulamayı netleştiren önerileridir.

## İnceleme sonrası netleştirilen sözleşmeler

Bu bölüm, R08/R09/E02 ve Paket2/5/6'daki genel ifadeleri kesinleştirir. Katalogda bunlarla çelişen kısa ifade varsa burada yazan davranış uygulanır.

### D01 — Kalıcı gönderim tekilleştirme

**Önerilen karar:** tekilleştirme otoritesi host/backend'dir; UI düğmesini kapatmak yeterli değildir. Mevcut conversation/task persistence'e typed receipt adapter eklenir; ikinci agent runtime yapılmaz.

- Anahtar: host kullanıcı profili + kanonik workspace/project kimliği + conversationId + requestId. UI requestId ilk gönderimde üretir ve retry'da korur; backend kabulü aynı anahtarla atomik kaydeder.
- queued/accepted/running aynı kimlikle tekrar gelirse mevcut receipt döner; yeni task açılmaz. completed/cancelled/failed terminal receipt aynen döner, implicit replay yapılmaz.
- Kullanıcının açık “yeniden dene” eylemi aynı **task** altında yeni attemptId oluşturur. Aynı attemptId duplicate gelirse yine aynı receipt. Request submission dedup ile tool side-effect dedup farklı seviyelerdir; ilki ikincisini garanti etmez.
- Core/app restart sırasında unfinished receipt “sonucu belirsiz / kurtarma gerekli” olarak restore edilir; otomatik failed veya completed yapılmaz. Yerel kuyruk kabulü hiç gerçekleşmemişse aynı requestId ile gönderilebilir; kabul edilmiş belirsiz iş önce observation/checkpoint ile ele alınır.
- Dış etki gerçekleşmiş olabilir: external idempotency key/receipt varsa onu doğrula; yoksa mevcut recovery OBSERVE_FIRST yolunu kullan. Sonuç gözlenemiyorsa otomatik yeniden yazma yok; kullanıcıya somut belirsizlik ve karar sunulur.
- Receipt saklama: transcript/checkpoint yaşam döngüsüne bağlı. Unfinished/ambiguous kayıt kullanıcı açıkça çözene veya ilgili konuşmayı yetkili biçimde silene kadar TTL ile düşürülmez. Terminal receipt, konuşma saklandığı sürece korunur. Uygulamanın mevcut retention politikasında konuşma silinirse aynı kimliği tekrar üretme; sonraki bağımsız işe yeni requestId ver.
- Test: accepted write+lost response+restart+retry yalnız bir executor effect. UI crash ve backend crash ayrı fixture. Terminal failed tekrar isteğinde yeni attempt açık eylem olmadan açılmaz.

Sayı temelli retention günü bu araştırmada uydurulmaz. Storage quota/migration uygulanırken kullanıcıya retention seçenekleri ayrıca ürün ayarı olarak sunulur; açık/ambiguous işin güvenlik kaydı silent eviction olmaz.

### D02 — MCP güven ve migration

**Önerilen karar:** yeni sunucunun başlangıcı “güven doğrulanmadı”. Yerel STDIO veya localhost olması otomatik güven vermez. Bağlandı/giriş yapıldı/trusted farklı alanlardır.

- Güven kullanıcı tarafından sunucu kimliği, origin/executable kaynağı ve açık yetenek açıklaması görüldükten sonra sunucu kapsamında verilir. Trust, bütün araçlara genel write izni değildir; mevcut ApprovalPolicy ayrı uygulanır.
- Mevcut configured sunucular migration'da legacy/unreviewed olarak işaretlenir. Daha önce kullanıcının açık verdiği dar izinler korunur; konfigürasyonda bulunmak yeni read exemption yaratmaz. Yeni/destructive/changing scope izin genişletmesi eski onaydan türetilmez.
- Güvenilmeyen sunucuda readOnlyHint yalnız iddiadır, tek başına onayı gevşetmez. Kullanıcı açık dar read scope allow vermişse o kayıt işler; bu legacy permission preservation davranışı “sunucu trusted” diye gösterilmez.
- Sunucu kimliği/origin/executable source veya araç etki sözleşmesi değişirse ilgili trust/allow scope yeniden değerlendirilir; her metin açıklama değişimi bütün izinleri silmez. Schema signature değişimi E03 denetimine girer.
- Çelişkili readOnly=true/destructive=true için öneri daha ihtiyatlı destructive kararıdır. Bu, standart zorunluluğu veya Codex davranışının bug olduğu iddiası değildir. Kullanıcıya politika değişikliği gösterilir.
- Onay fırtınasını önleme: bütün read çağrılarını “bu tur once” sormak yerine açık server+read scope izni ve iptal yönetimi sunulur. İlk trust gözden geçirme yapılınca sonraki aynı scope gereksiz tekrar sorulmaz.
- Test: existing explicit allow migration, unreviewed configured server, new local stdio, changed origin, contradictory annotations ve revoke. Bağlandı kartı trust rozeti üretmez.

### D03 — Çalışırken gelen mesajın otoritesi

**Önerilen karar:** aktif iş sırasında normal composer gönderimi varsayılan olarak **aktif göreve ek talimat**tır. Ayrı “Sonraki görev olarak sıraya ekle” eylemi bağımsız iş üretir. Gönderim yanında kısa mod etiketi görünür; kullanıcı tercihine göre varsayılan değiştirilebilir. Bu, bugünkü queue-only davranışını değiştiren yeni ürün kararıdır.

- Talimat güvenli tool boundary'de ana döngüye eklenir; host queued/applied receipt verir. Model yanıtı gelmeden veya sıradaki mutasyon başlamadan yeni talimat kuyruğu kontrol edilir. Already running dış işin geçmişteki etkisi bu mesajla geri alınmış sayılmaz.
- Kesin iptal için mevcut **Durdur** eylemi host cancellation'dır ve model sınıflandırmasına bağlı değildir. Doğal dil “bunu yapma” yeni kısıt olarak ana modele taşınır; hedef tekil ve belliyse pending scope durdurulur. Belirsiz hedefte yeni dış mutation bekletilip kısa soru sorulur. İn-flight tamamlanan etki “talimat gelmeden başlamış/tamamlanmış” makbuzuyla görünür; undo varsa ayrı onaylı workflow.
- “Durum” UI eylemi read-only status projection'ıdır. Yazılı durum sorusu agent tarafından yanıtlanırken original task korunur; status cevap yeni task tamamlanması sayılmaz.
- Mesaj hangi işte uygulandı ve hangi boundary'de alındı görünür. Kullanıcı görev değiştirmek istiyorsa açık sıra eylemi kullanır; model gizlice diğer conversation'a görev açmaz.
- Test: uzun fake provider beklerken steer, pending tool öncesi steer, in-flight external receipt, status preserved, independent queue ve stop. Parent task kimliği ve bütçe süreklidir.

Bu karar bütünüyle inference classifier'a bırakılmaz. Varsayılan göndermenin hedefi UI ve host kimliğinden bellidir; model sadece talimatın içeriğini yorumlar. Onay ve cancellation host sınırında kalır.

### D04 — Paket kapsamı ve token bütçesi

R22/R23 (öğretmen açıklaması/ders geri alma) P2; Paket7'nin zorunlu teslimi değil. Paket7 skill/ajan scope ve kanıt işlerini yapar. R24 task reçetesi Paket9'da yalnız teslim kanıtı uyumu, Paket14'te seçilen gerçek görevler kapsamında; geniş reçete kataloğu P2 olarak kalır.

Mevcut TurnBudget token sayacı içermez. E12'nin token ortak tavanı yeni additive usage entegrasyonu önerisidir. Provider token usage bildirmiyorsa kesin token üst sınırı kanıtlanamaz; mevcut çağrı/doğrulama/süre sınırları yine uygulanır. UI unknown maliyeti veya token'ı sıfır gibi göstermemeli.

### D05 — MCP yeni ve eski adapter

Yeni 2026-07-28 protokol ile legacy initialize/initialized akışı ayrı desteklenir. Yeni adapter handshake/Mcp-Session-Id göndermez; protokol version, method/name headers, `_meta`, optional `server/discover` fixture'ı vardır. Legacy adapter eski sunucuları çalıştırır. SDK sürüm destek matrisi yapılmadan mevcut initialize yolu silinmez. Bu ayrı migration paketidir; günlük MCP hardening'e sıkıştırılmaz.

## Resmî kaynaklar ve kullanım amacı

| Kaynak | Raporda desteklediği dar ilke |
|---|---|
| [OpenAI GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | low desteği, none/minimal ayrımı ve Responses tool-calling; hesabın ücretsiz erişimi iddiası yok |
| [ChatGPT projects](https://learn.chatgpt.com/docs/projects) | proje/sohbet/dosya/talimat bağlamı |
| [Agent approvals](https://learn.chatgpt.com/docs/agent-approvals-security) | izin ile teknik sandbox ayrımı; read annotation önceliği örneği |
| [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) | STDIO/Streamable HTTP ve authentication; host ortak config yaklaşımı |
| [Build skills](https://learn.chatgpt.com/docs/build-skills) | progressive disclosure ve explicit/implicit skill |
| [Image generation](https://learn.chatgpt.com/docs/image-generation) | referans, viewer, yorum ve seçili görsel iş akışı |
| [Claude permissions](https://code.claude.com/docs/en/permissions) | host tarafından izin enforcement; prompt grant değil |
| [Claude checkpointing](https://code.claude.com/docs/en/checkpointing) | kod/konuşma/summarize farklı rewind türleri |
| [Claude subagents](https://code.claude.com/docs/en/sub-agents) | izole alt görev context/scope yaklaşımı |
| [Claude skills](https://code.claude.com/docs/en/skills) | skill workflow ve subagent farkı |
| [MCP annotations](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/) | hint≠enforcement, untrusted beyan |
| [MCP2026 duyurusu](https://blog.modelcontextprotocol.io/posts/2026-07-28/) | stateless yeni core ve migration zorunluluğu |
| [Agent Skills formatı](https://agentskills.io/specification) | frontmatter ve progressive yükleme; allowed-tools experimental |
| [MCP skills extension](https://skills.extensions.modelcontextprotocol.io/specification/stable/skills) | per-origin namespacing, remote allowed-tools implicit grant değil |
| [WCAG2.2](https://www.w3.org/WAI/WCAG22/quickref/) | erişilebilir UI kabulünün kapsamı |

## İnceleme sonucu

Bağımsız builder, D01/D02/D03 açıklarını ve R22/R23 kapsam çelişkisini buldu. Yukarıdaki önerilen ürün kararları ve plan güncellemesiyle giderildi. Teknik reviewer E12 token sayacı ve E24 unknown-tool davranışının yanlış çağrışımlarını buldu; düzeltildi. Plan yolu düzeltildi. Her reviewer kaynak/document incelemesi yaptı; bu süreç ürün kodunun runtime doğrulaması değildir.


---

Belge: `docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md`

# Fusion profesyonel kullanım Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion'ın masaüstü, CLI ve Kits yüzeylerinde doğru model, izin, soru, iş durumu ve teslim kanıtıyla güvenilir günlük çalışma sağlaması.

**Architecture:** Mevcut tipli core olayları, ApprovalPolicy, ModelCapability, provider adapter'ları, checkpoint ve tool registry otorite olarak korunur. UI'lar bu verinin uyumlu projection'larını kullanır; ikinci agent loop/model yöneticisi/scheduler yazılmaz. Ana App ve Kits ayrı build/runtime sınırında kalır, sürümlü host sözleşmeleriyle birleşir.

**Tech Stack:** Python 3.11 venv; React/TypeScript/Tauri; App CI Node22; Kits scriptleri Node24.21.0; Vitest/Playwright/pytest; mevcut MCP SDK ve provider adapter'ları.

**Spec:** `docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/README.md` ve 01–07 ekleri. `07-kaynak-ve-karar-defteri.md` D01–D05 normatif öneri sözleşmesidir; belirsizlikte bu kararlar esas alınır. Ana raportaki ürün sözleşmeleri normatiftir. U/E/K/R katalogları öneri kapsamını tanımlar. Buradaki paketler uygulama sırasıdır; bir paketteki ilk test başarısızlığı görülmeden üretim düzeltmesi yazılmaz.

## Global Constraints

- Mevcut branch ve kullanıcı değişiklikleri korunur; push/merge/yeni branch talimatı yok.
- Repo `.env` ve secret içerikleri okunmaz, rapora/teste/log'a yazılmaz.
- Ücretsiz kullanım yolu korunur. GPT-6.1 Sol low uygulayıcı tercihi, Fusion varsayılan modeli değildir.
- Türkçe kullanıcı metinleri/docstring/log; mevcut katman sınırları; core stdlib; typed frozen dataclass.
- CLI/Desktop/Kits'te aynı izin ve sonuç otoritesi. Zaman aşımı ve kapanma onay değildir.
- Değiştirici işin tekrarında external idempotency kanıtı yoksa otomatik retry yok; önce observation.
- Eski protokolü kıran değişiklikler migration ve compatibility test olmadan uygulanmaz.
- App ve Kits runtime'ları ayrıdır. Global Node26 test sonucu desteklenen Node sonucu diye sunulmaz.
- Ağır pytest ve `evals.kabul` paralel koşturulmaz. Kullanıcı web profiline ağır otomasyon testleri uygulanmaz.
- Tam kalite kapısı geçmeden kod commit yok; conventional Türkçe commit, author/co-author ekleme yok.
- Bu rapor araştırma teslimidir. Uygulama başka hesapta paket paket yapılacaktır; tüm listeyi tek turda kodlamak yasaktır.

## Review Focus

1. Geç gelen cevap/model seçimi/olay başka tur veya sohbetin state'ini değiştirmemeli: paket 2/4/5.
2. UI kapanırken taslak, belge ve tamamlanmış artefakt kaybolmamalı: paket 2/3/8/11.
3. RequestId tekrarında dış mutasyon ikinci kez yapılmamalı: paket 2/5/8.
4. Sağlayıcı yeteneği bilinmiyorsa model adı veya UI seçimi kanıt yerine geçmemeli: paket 4/10.
5. Eski çekirdek/istemci additive alanı tolere etmeli; yeni kritik eylemi yanlış başarıya çevirmemeli: paket 2/12.

## Ön kontrol ve yürütme yöntemi

Katalogdaki “kaynakta eksik” her maddede önce güncel revision'ı oku. Başka hesap uygulamaya başladığında dosyalar değişmiş olabilir. İlgili davranış artık doğruysa yeniden yazma; test/kanıtla “zaten mevcut” işaretle. Line number'lara kör güvenme, sembol adına git.

Paket başına kapsamlı plan büyütmek yerine burada verilen imza/test/alanları kullan. İsimler **önerilen yeni interface** ise aşağıda belirtilir; mevcut API olduğu varsayılmaz. Yeni tip eklenecekse mevcut eşdeğer tip olup olmadığını önce ara.

Çalışma ağacı şu an menü/oyun kanıtı değişiklikleri ve iki önceki belge içeriyor. Araştırma dosyaları bunların üstüne ekleniyor. `git add .` yerine paket dosyalarını seç. `node_modules/` ekleme.

### Ortak doğrulama komutları

Fusion CLI kökünde:

```sh
.venv/bin/pytest -q tests/ILGILI_DOSYA.py
.venv/bin/ruff check .
.venv/bin/ruff format --check src tests evals prompt_opt desktop_build
.venv/bin/mypy
.venv/bin/pytest -q
git diff --check
```

`ILGILI_DOSYA.py` gerçek paket testine değiştirilir; placeholder komut koşturulmaz. Tam format `.` tarihi Markdown codeblock'larında yedi eski farklılık bulmuştu; ürün kod kapısını geçmek için unrelated tarihî belgeleri yeniden formatlama. Format kapsamı ve nedeni kapı kaydında açık yazılır.

App kökünde:

```sh
PATH=/opt/homebrew/opt/node@22/bin:$PATH npm test -- --maxWorkers=1
PATH=/opt/homebrew/opt/node@22/bin:$PATH npm run build
```

Bu Node yolu bu Mac'e ait; başka Mac'te Node22 executable bulunup aynı version check yapılır. Kits kökünde package.json `kits:check` Node24.21.0 hattını kullanır. Önce scripti oku; canlı model/haricî servis çağıran smoke'ları unit kapısı diye koşturma. `npm run typecheck`, ilgili Vitest ve mevcut build/lint/format scriptleri ayrı kontrol edilir. Tauri/Rust değiştiğinde App `check:ci` ve platform smoke gerekir; yalnız Markdown değiştiğinde ürün kapısını tekrar çalıştırma.

## Paket 1 — Kırmızı tabanı teşhis et ve runtime'ı görünür kıl

**Kapsam:** README başlangıç tablosundaki üç pytest başarısızlığı + R33. **Dosyalar:** `tests/test_kabul_html_game.py`, `tests/test_remotion_kit.py`, `tests/test_remotion_observe.py` ve teşhisin gösterdiği mevcut ürün modülü; App/Kits runtime scriptleri gerekiyorsa. **Ürettiği:** doğru temel kapı kaydı; diğer paketler bunu tüketir.

- [ ] Üç testi tek başına, sıralı koştur; eski tüm koşuyla aynı/assertion farklı mı kaydet.
- [ ] Root cause için browser/render hazır olma sinyali, süreç başlangıcı ve state hook sonucunu incele. Sabit sleep uzatarak assertion gevşetme.
- [ ] Ürün kusuruysa gerçek regresyon; test senkronizasyonuysa event/barrier temelli regresyon yaz. Yeni testi fail gör.
- [ ] Yalnız sorumlu kodu düzelt; Node22/App ve Node24/Kits ayrımını script/doctor'da belirginleştir. Runtime resolver eklenirse signature `resolve_runtime(project_kind, installed_versions)` saf karar olarak mevcut config katmanında tutulur; shell komut metnine secret ekleme.
- [ ] İlgili üç test; lint/type; gerekli tam Python kapısı; değiştiyse App/Kits kontrolü. Sonucu devam dosyasına yaz ve temizse yalnız ilgili paketi commit et.

## Paket 2 — Olay, mesaj ve gönderim kimliği

**Kapsam:** U11/U17/U24, K02/K04, R07/R08. **Dosyalar:** `core/events.py`, `appserver/protocol.py`, `appserver/session.py`, App protocol/types, sessions/types/useSessions, Composer; Kits Chat/local-threads/Fusion event adapter. **Önerilen yeni interface:** `SubmissionReceipt { requestId: string; sessionId: string; turnId: string | null; state: 'queued'|'accepted'|'running'|'failed'|'cancelled'; error: string | null }`. TS yalnız UI adapter'da bu biçime normalize eder; wire Türkçe isimlerini korur. `onSend` void yerine receipt/promise kabulü tasarlanır; eski callback uyumu tek adapter'da.

- [ ] A04/A05/A06/A34 için fake transport testleri yaz: send reject taslağı korur; iki Enter tek accepted; stale event başka sohbete gitmez; duplicate replay çoğaltmaz.
- [ ] Testleri kırmızı gör. Mevcut client request id ve backend request id'yi yeni paralel UUID sistemi kurmadan genişlet.
- [ ] D01 durable backend dedup ve task-attempt yaşam döngüsünü uygula. Backend accepted makbuzunu gerçek task kabulünde üret; failed teslimde taslak/ek snapshot'ını retry için tut. Mesajın kalıcı id'si React key olur; eski geçmiş için deterministik migration id üretilir.
- [ ] UI reducer duplicate event'i ayıklar; tur tamamlandı event'i tek kez. Bilinmeyen optional alan tolere, bilinmeyen critical action unsupported döner.
- [ ] Unit/protocol testleri + full gates; integration transcript örneğiyle yeni ve eski istemciyi doğrula. Commit sonrası receipt interface'ini devam dosyasına yaz.

## Paket 3 — Karşılama ve async UI doğruluğu

**Kapsam:** U01–U10/U19/U21/U31/U32, K27. **Dosyalar:** `App.tsx`, `SessionApplication.tsx::ConnectedOnboarding`, onboarding, Settings, ImageCreate. **Önerilen yeni ortak interface:** `AsyncState<T> = {status:'loading'} | {status:'ready';value:T} | {status:'error';message:string}`; “boş” ready value'dur. Genel state store yazılmaz; ekran adapter'ında kullanılır.

- [ ] A01/A02/A03/A28: localStorage throw, bağımsız keşif fail, count unknown, provider configured-but-unverified ve image load error fixture.
- [ ] Mutasyon sonucu `{ok:false}` ile promise reject ayrı tests; her ikisinde görünür hata ve önceki state. Kırmızı testleri gör.
- [ ] `Promise.allSettled` veya eşdeğer bağımsız sonuç işle; doğrulanmamış apprentice active false demek yerine pending/unknown olsun; kaynak sayısı yoksa “Bulundu”.
- [ ] Projesiz devam ve kurulum restore; güvenli storage adapter; reset/load/save için pending ve retry. Kopyalama başarılı/başarısız makbuzu.
- [ ] İlgili Vitest + visual mevcut fixture'ı güncel karar ile kıyasla; test/build. Native ilk açılış kabulü daha sonra paket16'da.

## Paket 4 — Model ve thinking sözleşmesi

**Kapsam:** U18/U26–U30, E33, R01–R06. **Dosyalar:** `core/model_capability.py`, `core/types.py`, `appserver/model_catalog.py`, provider capabilities, config, ModelPicker/Models/Composer, protocol; Kits model adapter.

**Önerilen additive interface:** mevcut ModelCapability'ye `supported_reasoning_efforts: tuple[str,...] = ()`, `reasoning_efforts_verified: bool = False`. Boş verified=false bilinmiyor; boş verified=true desteklenmiyor. UI `requestedModel`, `observedModel: string|null`, `fallbackReason:string|null` metadata'sını mevcut olaylardan alır. Sağlayıcı bu effort listesini gerçekten bildirmiyorsa doküman/ölçüm kaynağı ayrı kaydedilir; model adından tahmin yok.

- [ ] A12–A16: stale model selection, rejected selection, fallback, unknown observed, unsupported effort ve mutation eligibility.
- [ ] Kırmızı testleri gör; API adapter contract ve web/template kontrolünü ayır. GPT-6.1 Sol adapter seçilirse resmî Responses tool contract; Fusion defaults değiştirilmez.
- [ ] Model katalogu typed capability projection üretir; UI arama, klavye, loading/error/retry, bağlan eylemi. Çalışan turda model bilgisi görünür, değişiklik sonraki turda.
- [ ] Thinking gösterim ayarı gerçek effort'u değiştirmez; template disable toggle yalnız destekleyen adapter'a gider.
- [ ] Capability/model/approval testleri, UI test/build, full Python. Gemini requested/observed örneği gerçek smoke ile doğrulanır; yedek modeli primary başarı gibi raporlama.

## Paket 5 — İşlem onayı ve soru yaşam döngüsü

**Kapsam:** U33–U35, E15–E22, R09/R15/R32. **Dosyalar:** `engines/agent/approval.py`, engine_tools/loop/clarify, appserver question/approval summary, App Approval/types, voice answer bridge. **Tüketir:** paket2 session/turn/request ids; D03 aktif göreve steer / açık bağımsız queue kararı.

**Önerilen interface:** mevcut SessionQuestion kimliği kullanılır; yanıt envelope'una `questionId`, `turnId` ve `decisionId` korelasyonu eklenir. `decision` izin için once/session/deny; bilgi için text/choice; timeout/cancel ayrı terminal. Existing protocol kelimeleri migration adapter'da korunur. AuthorizationScope sunucu/hesap/eylem/normalize hedef parmak izi tutar; raw secret içermez.

- [ ] A08–A11/A32: ardışık soru state reset, double send, stale ses cevabı, target değişikliği, policy revoke, Escape deny olmayan kart.
- [ ] Fail test; parent request kapsamını callback/key ile doğrula. Timeout önerilen seçeneği yanıt yapmaz.
- [ ] ApprovalMemory'yi mevcut shell scope'u bozmadan uzak hedef kapsamıyla genişlet; kullanıcı geniş izin seçiyorsa scope açık metinle göster. Deny/blocked/optional default ayrı.
- [ ] Kart pending iken disabled; gönderim fail ise retry; kapanışta odak geri. Async optional soru bağımsız işi durdurmaz; required dependent iş bekler.
- [ ] Approval/loop/voice ve UI testler; güvenli fixture dış etki tekliği; full gate. Onay politikası değişikliği görünür release notu.

## Paket 6 — MCP dayanıklılığı ve bağlantı merkezi

**Kapsam:** E01–E08, R17/R18/R19. **Dosyalar:** mcp_bridge tool_effect/client/pool/service/oauth/tokens, config trust metadata, connectors/control.

- [ ] A17–A19: annotation conflict, trusted/untrusted read, asılı list/call, refresh yarış, close cancel. Kırmızı testleri gör.
- [ ] Fusion için çelişkide destructive/unknown kararı uygula; bunun daha ihtiyatlı ürün politikası olduğunu dokümante et. Var olan Codex read-first davranışı standardı ihlal ediyor diye iddia etme.
- [ ] D02 yeni sunucuda unreviewed trust ve legacy explicit scope migration uygula. Server bazlı connect/list/call/close bütçesi ve bounded backoff; token single-flight, typed health/provenance metadata; sır loglama yok.
- [ ] UI bağlandı/parked/degraded/auth gerekli ayrımı ve retry. Bir sunucu fail tüm listeyi boşaltmaz.
- [ ] Yerel STDIO+HTTP fixture connect/list/read/cancel/close smoke; unit/full gate. **Yeni MCP sürüm geçişi bu pakette bütün eski handshake'i silmez.** Ayrı protocol matrix işi paket15'tedir.

## Paket 7 — Ajan ekipleri ve skill doğruluğu

**Kapsam:** E09–E14/E23–E26, R19–R21. R22/R23 bu paketin zorunlu kapsamına dahil değil; P2 ayrı teslim. **Dosyalar:** team, capabilities/expertise, existing subagent card/UI and MemoryPanel. **Ürettiği:** scope-normalized child result ve skill origin evidence.

- [ ] A20/A21: alias/symlink scope çakışması, child parent dışına çıkış, bir child exception ve bütçe. Skill collision/unknown tool/hash değişimi testleri.
- [ ] Fail test; root kanonik çözümlerini mevcut path validator üzerinden birleştir; child yalnız parent kapsamını daraltır.
- [ ] Child terminal sonucu exception/cancel durumunda da bir kez; independent sibling korunur, parent cancel hepsini durdurur. Çağrı/doğrulama/süre bütçesi mevcut TurnBudget otoritesine bağlı. Token sayacı henüz yok; provider usage destekli additive sayaç ayrı E12 alt işi. Usage bilinmiyorsa kesin token tavanı garantisi verilmez.
- [ ] Skill katalogunda origin/version, explicit/implicit loading receipt. Remote allowed-tools grant sayılmaz. Tek yüksek güvenli skill otomatik ipucu yaklaşımı korunur.
- [ ] team/capability unit+full gate; UI team fixture. R22/R23 öğretmen açıklaması ve ders invalidation bu pakette uygulanmaz; P2 ayrı küçük görev olarak planlanır.

## Paket 8 — Checkpoint, devam ve gerçek iptal

**Kapsam:** E27–E32, R10/R14. **Dosyalar:** checkpoint_store, core/checkpoint, plan_checkpoint/recovery/liveness, tools/jobs, appserver cancellation. **Tüketir:** paket2/5 kimlik ve izin sonucu.

- [ ] A22–A24: same-job polling, iki plan adı collision, aynı PID parallel save, crash before replace, stale revision, v999, external executed-response-lost.
- [ ] Fail test; unique temp+atomic replace, durability yalnız platformda desteklenen fsync; revision karşılaştırması lock/protokol ile korunur. Eski path migration read gerekir.
- [ ] Resume completed effect'i yeniden çalıştırmadan observation; kaynak değişimi dependent step invalidation. Ham source/prompt checkpoint'e ekleme.
- [ ] Stop gerçek owned process/task temizliğini bekler ve sonucunu UI'ya yollar; bağımsız başka session'a dokunmaz.
- [ ] Checkpoint/recovery/jobs unit+subprocess fixture; full gate; crash/reopen gerçek native smoke paket16'da.

## Paket 9 — Kanıtlı kapanış ve çalışma akışı

**Kapsam:** R11–R16/R24, U22/U23/U25, E35. **Dosyalar:** core artifacts/events, existing turn/completion report, Conversation/ActivityLine/PreviewPanel/ChangesPanel; no new agent engine.

- [ ] Wrong-success, NoFileChanges, partial, stale screenshot, duplicate final, future schema ve rejected candidate transcript testleri.
- [ ] Fail test; mevcut runtime `TurnOutcome` ve verifier otoritesiyle teslim kartı. Modelin “bitti” metni status değiştirmez.
- [ ] Teslimde dosya/URL açma, screenshot viewport, source, verification receipt; yukarı okuyan kullanıcı scroll korunur, yeni mesaj düğmesi.
- [ ] Uzun geçmiş performansı ölçülür; mevcut perf test karşılaştırılır. Gerekliyse bounded render; erişilebilirliği bozan kör virtualization yok.
- [ ] Completion/unit/UI+visual/full gates. E35 loop modülerleştirme davranış snapshot'ıyla ayrı alt değişiklik; yeni özellik refactor'a karıştırılmaz.

## Paket 10 — Görsel üretim iş protokolü

**Kapsam:** K27–K35, R26/R27/R29. **Dosyalar:** appserver/image_create/image_flows, providers/image_generation/web_image/nim_image, ImageCreate/akis/akisCalistir/AkisTuvali.

**Önerilen interface:** `ImageJobReceipt {jobId:string; state:'queued'|'running'|'partial'|'completed'|'failed'|'cancelled'; assetIds:string[]; error:string|null}`. Gerçek dosya teslimi current image core üzerinden; yeni provider implementasyonu gerekmez. RPC jobId/cancel existing tools/jobs ile eşdeğer ise onu kullan. Cancellation external provider'ı durduramıyorsa kesin “uzak iş iptal edildi” iddiası yok; sonraki varyasyonun başlaması engellenir.

- [ ] A28–A31: initial load error, DAG duplicate/cycle/NaN, atomic save interruption, exact_size unknown, cancel after first image, MIME fake/login HTML, missing target.
- [ ] Fail test; server-side DAG validation ve atomic flow persistence; progress/cancel task ownership, partial results retain.
- [ ] Basit üretim ve advanced flow; provider capability'ye göre oran/referans/seed. Hedef asset görünür; asset yoksa iş durur.
- [ ] Viewer focus trap/return; gallery partial badge; missing variant retry yalnız eksik varyasyona. Test/unit/full gates.
- [ ] Mevcut bağlı sağlayıcıyla dar gerçek generate/edit smoke; dosya açılır, dimensions/alpha ve referans gözle kıyaslanır. Model metni dosya kanıtı değildir.

## Paket 11 — Kits sohbet ve belge dayanıklılığı

**Kapsam:** K01–K17/K23/K25, R30/R31. **Dosyalar Kits:** ThreadList, Chat, SpaceWorkspace/SpaceLibrary/PageDocument/PageReviewCard, editor autosave, api, local-threads/page-service/local-computer-bridge. **Tüketir:** paket2 task receipt; paket5 question; varsa mevcut host bridge adapter.

- [ ] A25–A27: remote-only page2 thread, delayed poll, area switch, double create, draft restart, stale expectedRevision, agent patch conflict.
- [ ] Fail test; real merged pagination, scoped async load with AbortSignal, pending create, Turkish search.
- [ ] Draft persistent key conversation/page+revision; storage failure visible; successful save retires only matching draft. Conflict diff/merge explicit.
- [ ] Host calls cancelled on teardown; keyboard Tabs. Büyük library için önce5.000 ölçüm, gerekliyse sunucu paginated search; 10.000 galeri ayrı paket12.
- [ ] Kits type/lint/unit/build/format ve gerçek host integration smoke. Node22 kullanma; Kits kendi pinned scriptini kullan. Main App code değişmediyse bütün Rust build'i burada tekrar etme.

## Paket 12 — Ortak artefakt köprüsü ve birleşik tasarım

**Kapsam:** K26/K32/K33, R25/R28/R35. **Dosyalar:** core/artifacts, appserver image/library, App library/preview/ui/theme; Kits host api/editor/generated theme scripts. **Önerilen additive interface:** mevcut artefakt tipine `asset_id`, `kind`, `mime`, `relative_path`, `created_by_task_id`, `parent_asset_ids`, `metadata_version`. Boyut/alpha/model/seed yalnız biliniyorsa alan; yoksa null/unknown. Host resolver projenin allowlist kökleriyle path çözümlemeli.

- [ ] Aynı asset chat/gallery/page roundtrip; migration eski path; root escape; missing file; parent deleted; unknown metadata; A34 backward host testleri.
- [ ] Fail test; tek artefact authority; mevcut gallery sidecar ile migration. Galeri index/pagination total order; gerektiğinde corruption recovery scan.
- [ ] Ortak token'lar tek kaynaktan üretilir; shared davranış şartnamesi App/Kits adapter'a taşınır. React major'larını aynı pakete zorla birleştirme.
- [ ] Yeni image comments/compare ayrı küçük UI alt görevi; mask edit unsupported capability açık. Unit/browser/visual; iki repo gate; packaged bridge smoke.

## Paket 13 — Ses ve tarayıcı gerçek kabulü

**Kapsam:** K18–K22/K24/K25, R05/R32. **Dosyalar:** main voice ask/answer, Kits local voice/CallView, web login/browser host, computer panel.

- [ ] A32 + mikrofon reddi, speaker unavailable, TTS fail, hangup pending, same profile lock, visible window false-positive fixtures.
- [ ] Fail test; task/question correlation, owned cancel; TTS fail text preserved; buffer/receipt idempotency.
- [ ] Kullanıcı cihazında native visible login, mikrofon giriş, local STT/TTS ve browser devralma. Şifre/çerez okunmaz. Açılan pencere ekranda doğrulanmadan “açtım” başarı metni yok.
- [ ] Unit/full relevant gates + L12 kanıt. Kullanıcının cihaz adımı gereken yerde gerçek blocker olarak açık söylenir; diğer bağımsız işler sürdürülür.

## Paket 14 — Günlük işler ve üretim kalitesi

**Kapsam:** L02–L11, R24/R37/R38. **Dosyalar:** existing `evals/suite/production.yaml`, `evals/kabul`, skills and actual product tool/engine paths where evidence points.

- [ ] Aynı brief/input/provider/izin ile taban kaydı; günlük araştırma, kod düzeltme, MCP taslak ve belge senaryoları.
- [ ] Site/game/video işler sıralı boş output kökünden Fusion üretimi. Başarısız output'u root elle düzeltip Fusion başarısı sayma.
- [ ] Ürün kusuruna source regresyon; kabul ölçerindeki kusursa evaluator düzeltmesi ayrı. İkisini parite kanıtı diye birleştirme.
- [ ] Gerçek viewport/kare/etkileşim+insan rubriği. Başarısız denemeler ve unavailable ayrı ama saklanmaz.
- [ ] Kalite kapısı ve tekrar aynı kabul. “ChatGPT yerine kullanım” kararı başarısızlık/data-loss/false success matrisiyle verilir; yüzde uydurma.

## Paket 15 — Protokol/dağıtım olgunluğu ve ileri fikirler

**Kapsam:** MCP2026 migration matrix, R34/R36/R39/R40/E34. P2 işlerin hepsi zorunlu ilk yayın değil.

- [ ] Mevcut Python/TS MCP SDK sürümünü lock'tan doğrula; legacy ve yeni stateless adapter için ayrı fixture. Legacy initialize/initialized akışını korur. Yeni 2026-07-28 adapter initialize veya Mcp-Session-Id göndermez; MCP-Protocol-Version, Mcp-Method/Mcp-Name ve _meta taşır; isteğe bağlı server/discover ayrı sınanır. SDK sürümü desteklemiyorsa sürüm-gated experimental adapter/migration gerekir; mevcut istemciye unsupported alan zorla eklenmez.
- [ ] Kaynak/time/observed başarı ve fiyat unknown dataset; routing benchmark. Cost proxy'den gerçek cost'a geçiş tek başına gratuitous default model değişimi yapmaz.
- [ ] Diagnostics export sentinel; recurring restart/delivery duplicate; recorded skill sanitize. Her biri bağımsız küçük paket olarak uygulanır.
- [ ] Yalnız ilgili kapılar ve genişlenen senaryolar. İleri liste kapıları başarısızsa mevcut günlük sürümü kırmadan feature gate/experimental etiketi.

## Paket 16 — Günlük kullanım sürümü kabulü ve devir

**Kapsam:** L01–L12 ve tamamlanan P0/P1 paketleri. **Dosyalar:** runtime/build/install scripts, existing release reports, continuation record.

- [ ] App Node22 test/build; gerekiyorsa Rust/Tauri check:ci; Kits pinned check/build; Python full gates. Koşular kaynak baskısına göre sıralı.
- [ ] Clean user profile/install fixture ve mevcut kullanıcı upgrade; transcript/checkpoint/draft/asset migration.
- [ ] Native UI klavye/VoiceOver/dark/light/zoom; screenshots güncel. Screenshot threshold'u kusuru gizlemek için artırma.
- [ ] Release manifest: commitler, bundled core+Kits sürümleri, model/connector support, test/acceptance kanıtı, bilinen eksikler, rollback yolu.
- [ ] Kullanıcı günlük üç işi Fusion'da yapar; müdahale ve hatalar ölçülür. Geçmeyen yüzeye “tam hazır” etiketi verilmez.

## Katalog kapsam haritası

U01–10→3; U11–17/24→2/5; U18/26–30→4; U19/21/31/32→3; U20→2'ye ek clipboard adapter; U22/23/25→9; U33–35→5. E01–08→6; E09–14/23–26→7; E15–22→5; E27–32→8; E33→4; E34→15; E35→9. K01–17/23/25→11; K18–22/24→13; K26→12; K27–35→10/12. R maddeleri paket başlıklarında ilişkilidir; R06/R22/R23/R36/R38/R39/R40 ileri bağımsız alt paket olarak P0/P1 sonrasında seçilir.

## Tamamlanma kaydı

Bir paketin bitti sayılması için: kapsam ID'leri, red/green test, değişen dosyalar, quality gate çıktısı, canlı kanıt gerekiyorsa yolu, inceleme sonucu, commit, açık eksik. “Tüm taskları tamamladım” doğal dil cümlesi bu kaydın yerine geçmez. Başka hesap kalan paket numarası ve önceki contract'ları `06-baska-hesaba-devret.md` üzerinden devralır.


---

Belge: `docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/06-baska-hesaba-devret.md`

# Başka hesaba devir — GPT-6.1 Sol low uygulaması

Bu dosya kullanıcı tarafından başka hesaba verilecek uygulama talimatıdır; şu anda dış bir hesaba mesaj gönderilmedi. Model adı kullanıcı tercihidir. Aşağıdaki blok mevcut özellikleri silip yeniden yazmaya veya tüm raporu tek turda uygulamaya yetki vermez.

## Başlangıç mesajı

```text
Fusion projemi profesyonel günlük kullanım için geliştireceğiz. GPT-6.1 Sol low ile çalışıyorum; karmaşık kararlarda tahmin ederek geniş değişiklik yapma, mevcut sözleşme ve küçük görev paketi üzerinden ilerle.

Depolar:
/Users/motogate/Desktop/all/01-Projeler/fusion-cli
/Users/motogate/Desktop/all/01-Projeler/fusion-kits

İlk okumalar:
1. fusion-cli/CLAUDE.md ve RULES.md
2. docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/README.md
3. Aynı klasörde 01–07 ekleri; önce mevcut güçlü taraflar ve kanıt sınırı.
D01–D05 kararları 07-kaynak-ve-karar-defteri.md dosyasında; sözleşme uyuşmazlığında önceliklidir.
4. docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md

Mevcut branch ve kullanıcı değişikliklerini koru. Yeni branch/push/merge/hard reset yapma. .env, çerez, token veya API anahtarı içeriklerini okuma. git add . kullanma; node_modules ekleme. Ücretsiz LLM kimliğini koru; GPT-6.1 Sol bu uygulayıcı model, Fusion'ın yeni varsayılanı değil.

Önce git status ve revision ile güncel durumu doğrula. Raporun hazırlandığı revision 644a2e44, Kits 1dd007c1; bunların ilerisine geçilmiş olabilir. Başka oturumun işine dokunma. Yeni full pytest veya kabul koşusu başlamadan mevcut ağır koşuların durumunu denetle; full pytest ile evals.kabul paralel çalışmaz.

İlk iş Paket 1. Python tam koşusunda üç test başarısız olmuştu:
tests/test_kabul_html_game.py::test_restart_only_on_game_over_with_state_hook_passes
tests/test_remotion_kit.py::test_runtime_edilmis_onceki_kare_feature_markerini_yeniden_kullanmaz
tests/test_remotion_observe.py::test_renderer_ayri_gruptaki_direncli_chromium_benzeri_cocugu_temizler
Önce tek tek üretip nedenini bul; kanıtsız flaky etiketi veya sadece sleep artırma yok.

App testleri Node22 ile 122 dosya/956 test geçmişti. Global Node26 jsdom localStorage hatası üretiyor. Kits farklı: engines>=24 ve kits scriptleri Node24.21.0. App ve Kits'i tek Node sürümünde zorla çalıştırma. Python repo .venv kullan.

145 maddelik liste fikir ve geliştirme kapsamıdır. Hepsini tek turda uygulama. 16 paket planını sırayla izle; o paketin rapor ID'lerini oku, önce gerçek davranış testiyle açığı doğrula. Zaten mevcut ve doğruysa yeniden yazma; kanıtla kaydet. Yeni tip/imza önerisini mevcut API diye varsayma; mevcut karşılığı varsa genişlet. Yeni event bus/agent loop/model yöneticisi/izin deposu/scheduler oluşturma.

Her paket için: davranış testi fail → küçük uygulama → ilgili test pass → gerekli lint/type/full kalite kapısı → bağımsız review → Türkçe conventional commit. Kalite kapısı kırmızı iken commit yok. Kullanıcıya durum, kalan iş ve somut engel bildir. Gereksiz aşama onayı isteme; bu talimat kapsamındaki geri alınabilir yerel işleri sürdür. Dış yayın, harcama, silme veya izin genişletme ayrı somut kapsam gerektirir.

Onay/soru/idempotency/fallback/draft/checkpoint gibi sözleşmelerde eksik karar varsa küçük repro/contract testiyle açıklaştır. Sessiz geniş varsayım yerine gerçek blocker'ı belirt; bağımsız çalışmaya devam et. Model yetersizliği hissedersen testi/kanıtı ve dar alternatifleri göster; projeyi baştan kurma.

Bitti iddiası sadece test değil gerçek task receipt/artefakt/acceptance ile. Model bitti dedi diye UI completed olmayacak. İstenen ve kullanılan model farklıysa görünür olacak. Kaynakta özellik bulunması runtime'da çalıştığı iddiası değil. Mikrofon, MCP OAuth, görünür giriş penceresi, paket kurulum ve gerçek üretim ayrıca canlı kabul ister.

Başlarken güncel başlangıç durumunu ve Paket 1'de hangi testi ürettiğini bildir; sonra işi yap. Paket sonunda aşağıdaki ilerleme kaydını güncelle. Tüm Fusion hazır veya ChatGPT/Claude paritesi sağlandı iddiasını aynı brief/ölçüm olmadan yapma.
```

## Tek paketlik dar devam mesajı

```text
Fusion raporundaki Paket N'yi uygula. Önce README davranış sözleşmeleri, Paket N, ilgili U/E/K/R maddeleri ve önceki tamamlanan paketlerin interface kaydını oku. Güncel kaynakta bug hâlâ var mı davranış testiyle göster. Bu tur yalnız o bağımsız paketi tamamla; diğer paketleri kodlama. Paket bittiğinde test/kanıt, dosya listesi, review, commit ve açık eksikleri ilerleme tablosuna yaz. Paket büyürse çalışan ve test edilebilir alt teslimlere böl; kapsam sessiz genişlemesin.
```

`N` kullanıcı/ilerleme kaydındaki gerçek paket numarasıyla değiştirilir. Otomatik olarak N+1 tahmin edilmez; son committed gate kaydı kontrol edilir.

## İlerleme tablosu

Bu başlangıç tablosu **uygulanmadı** durumundadır. Rapor hazırlanması geliştirme paketinin tamamlandığı anlamına gelmez.

| Paket | Durum | Commit | Test/kanıt yolu | Sonraki engel |
|---|---|---|---|---|
| 1 Taban/runtime | Başlamadı | — | Önceki üç pytest fail | Teşhis |
| 2 Olay/gönderim | Başlamadı | — | — | 1 |
| 3 Onboarding/async | Başlamadı | — | — | 2 |
| 4 Model/thinking | Başlamadı | — | — | 2/3 |
| 5 Onay/soru | Başlamadı | — | — | 2 |
| 6 MCP | Başlamadı | — | — | 5 |
| 7 Skill/ekip | Başlamadı | — | — | 5/6 |
| 8 Resume/iptal | Başlamadı | — | — | 2/5 |
| 9 Teslim kanıtı | Başlamadı | — | — | 2/8 |
| 10 Görsel işler | Başlamadı | — | — | 4/8/9 |
| 11 Kits dayanıklılığı | Başlamadı | — | — | 2/5/8 |
| 12 Asset/theme bridge | Başlamadı | — | — | 10/11 |
| 13 Ses/browser | Başlamadı | — | — | 5/8/11 |
| 14 Gerçek üretim | Başlamadı | — | — | İlgili P0/P1 |
| 15 İleri/protokol | Başlamadı | — | — | İlgili taban |
| 16 Günlük kullanım kabul | Başlamadı | — | — | Kritik kapılar |

## Paket sonunda yazılacak kayıt

```text
Paket / kapsam ID'leri:
Başlangıç revision ve working tree:
Davranış testi (önce fail):
Root cause:
Değişen dosyalar:
Yeni/güncellenen interface ve migration:
İlgili test sonucu:
Tam kapı / hangi ortam / exit:
Gerçek kabul gerekiyorsa kanıt:
Bağımsız review sonucu:
Commit:
Açık eksik/engeller:
Sonraki güvenli paket:
```

## Düşük reasoning modunda hata önleme

Küçük kapsam güçlü korumadır. Bir task'ın testini yazıp çalıştırmadan dört başka modülü değiştirme. Gerçek failure ile öneriyi ayır. TypeScript typecheck, Python mypy ve geriye uyum fixtures sezgisel API tahminlerini erken yakalar. Arayüz görselini ancak gerçek host receipt'inden besle. Büyük raporu her tur tamamını prompt'a yapıştırma; ana sözleşme+aktif paket+ilgili ID+önceki interface kaydı yeterlidir.

Çözülmemiş belirsizlikler için modelin confidence cümlesi kanıt değildir. Örneğin “MCP connected görünüyor” yerine fixture'da list/call sonucu; “iptal edildi” yerine owned process terminal makbuzu; “resim hazır” yerine açılabilir gerçek dosya. Bir paketi bitirmek için testi skip etme, assertion azaltma, timeout'u gerekçesiz şişirme veya screenshot fark toleransını büyütme.
