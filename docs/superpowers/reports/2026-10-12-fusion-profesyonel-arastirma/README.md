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
