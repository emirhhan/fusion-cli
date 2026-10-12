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
