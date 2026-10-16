# Fusion master plan — mevcut koda göre ön inceleme

15 Ekim 2026. Kaynak belge: kullanıcının FUSION_MASTER_PLAN.md dosyası. Belge ürün hedefi ve koşullu bulgu kaynağıdır; içindeki bütün öneriler otomatik uygulama emri sayılmadı. Kullanıcının mevcut arayüzü koruma, yeni F logosunu aynen kullanma ve önce mevcut paketleri bitirme talimatı önceliklidir.

Ana repo tabanı 03ec832387a42c72bf66111a5e55c3f067cc7ff0; fusion-backup-2026-10-13. İncelenen çalışma ağacı ayrıca commit edilmemiş değişiklikler içeriyor. Aşağıdaki kanıtlar bu çalışma ağacına aittir; sabit sürüm yayını veya tüm platform kabulü değildir. Kits ayrı çalışma ağacıdır ve önceki açık kullanıcı yetkisiyle geliştirilmiştir; master belgedeki tek repo önerisi mevcut Kits yetkisini iptal etmez.

## Koşullu bulgularda doğrulananlar

| Konu | Durum | Kod / kanıt | Karar |
|---|---|---|---|
| Checkpoint kapsamı ve atomik sürüm kontrolü | Kısmen var | memory/checkpoint_store.py, checkpoint_effects.py; schema6, root/conversation kapsamı, revision CAS; test_task8_checkpoint_contract.py | Mevcut depoyu koru; ikinci görev deposu kurma. |
| Yanıtı kaybolan dış işlem tekrarları | Kısmen var | engines/agent/effect_checkpoint.py ve core/effects.py; intent önce diske yazılıyor, belirsiz dış etki gözlem gerektiriyor | Workflow dışındaki genel turlar ve gözlemle uzlaştırma açık. Rastgele dış sistemlerde exactly-once iddiası yok. |
| REPL sabit conversation_id | İzolasyon düzeltildi; açık süreçler arası workflow seçimi hâlâ açık | ReplState sohbet kimliği hem TUI TranscriptStore hem AgentDeps/checkpoint'e aktarılır; plain REPL aynı state kimliğini kullanır | Yeni oturum başka konuşmanın planını bulamaz; eski ortak kayıtlar silinmez veya otomatik taşınmaz. /resume kaynak digest içe alımı korunur; workflow/izin geri yükleme sayılmaz. Gerçek checkpoint izolasyon regresyonu PASS. |
| ChangeSet kalıcılığı | Kısmen var | core/changeset.py bellek içi snapshot; edinilen dosya ve atomik oluşturma ayrı izleniyor | Mevcut güvenli geri alma davranışını koru. Çökme sonrası kalıcı transaction/izole çalışma kabulü açık. |
| BrowserVerifier atlama sonucu | Koşullu | engines/agent/browser_verify.py optional Playwright yokluğunda ok=True döndürüyor; yorumlar bu kapıyı opsiyonel iyileştirme sayıyor | Her opsiyonel kapıyı zorunlu yapmak doğru değil. Zorunlu UI/oyun kabulüyle bağını test etmeden genel davranışı değiştirme. |
| TurnJournal başarısızlık/kesinti | Kısmen var, güçlendirildi | memory/turn_journal.py; atomic replace, dosya kilidi, içerik revizyonu; eski bildirim yeni kaydı ezemiyor | Hata/iptal kaydı korunuyor. Bu kayıt tek başına dış etki yetkilendirme otoritesi değil. |
| Otomatik devam üst sınırı | Var | appserver/session.py MAX_AUTO_CONTINUE_TURNS=3 | Sonsuz göreve dönüştürme; uzun görev ve bütçe sözleşmesi ayrı. |
| Ayrı süreç/PTY yöneticisi | Var | appserver/processes.py ve App processes/TerminalPanel; gerçek süreç grubu kapanışı testleri | Yeniden yazma; mevcut kapanış ve terminal kanıtını kullan. |
| Büyük dosya aralıklı okuma | Hatalı, yerel regresyonla düzeltildi | tools/files_read.py büyük normal dosyada fiziksel satırları sınırlı parçalarla tarar; offset ilk bayt penceresi sonrasına ulaşır | UTF-8 sınırı, CRLF, dev satır, EOF, iptal ve tam bayt sınırı testli. 4 ilgili dosyada79test PASS; artefaktların mevcut sanal segment sözleşmesi korunur. Tam paket kabulü ayrı. |
| Chrome sekme kapatma salt okuma | Hatalı, düzeltildi | tools/chrome.py chrome_action_effect; test_chrome_action.py | REMOTE_DESTRUCTIVE; normal onay kiplerinde sorulur, plan kipinde engellenir. Açık bypass modu ayrı kalır. |
| Chrome tuş/drag/asset limitleri | Belirsiz | tools/chrome.py ve chrome-extension mevcut | Gerçek browser input/indirme/kurulum kabulü olmadan destek veya hata etiketi koyma. |
| MCP sabit kısa timeout | Kısmen giderildi | config/model MCP bağlantı/list/call/close bütçeleri; mcp_bridge/client/pool/lifecycle | Mevcut yapılandırılabilir bütçeleri koru; bütün sağlayıcıların canlı kabulü açık. |
| MCP OAuth hesap/süreç yarışı | Kısmen giderildi | oauth_flow ve pool kaynak/sürüm sahipliği, OS FileLease, keyring worker drain | Mevcut SDK akışı korunuyor. Gerçek sağlayıcı app review veya giriş yapılmış kabulü bu testlerden çıkmaz. |
| İnsan tarafından okunabilir MCP araç kataloğu | Uygulandı, yerel testli | appserver/mcp_catalog.py; ConnectorsScreen/McpToolCatalog | Açık kullanıcı isteğinde yalnız keşif; giriş açma/araç yürütme yok. Kaynak/etki/parametre gösterilir, ham örnek/default taşınmaz. |
| Test/Git paneli ve aynı dosya önizlemesi bayat | Hatalı, düzeltildi | TestsPanel/PreviewPanel revision; WorkspaceFreshness.test.tsx | Mevcut FilesChanged sayacı kullanılır. Web sekmesi korunur. |
| FileExplorer revision key ile taslak kaybı | Hatalı, düzeltildi | SessionApplication key=root; useWorkspace revision refresh; FileExplorer.test.tsx | Açık klasör, seçim ve düzenleme korunur. Eski save ack başka dosyayı veya yeni taslağı değiştiremez. |
| Skill tokenizer/frontmatter | Kısmen var | tools/capability_search.py, capabilities.py ve test_task7_scope_skill_redprep.py | Mevcut arama/metadata yolu korunur; kaynak yüklenmesi işin yapıldığı kanıtı değildir. |
| UNKNOWN native_tools alanı | Ayrıştırma gerekli | providers/capabilities.py native_tools=True olabilir; aynı sonuç evaluation_state=unknown taşır | Kullanılabilir protokol yolu ile doğrulanmış model kabiliyeti farklı. Flag'i tek başına kapatıp bütün bilinmeyen modelleri bozma; kullanıcı gösterimini ve probe kanıtını birlikte incele. |
| macOS native canlı ekran | Tam kabul belirsiz | tools/desktop.py, Tauri/native helper ve izin katmanları mevcut | Canlı stream, kaynak seçimi, sleep/revoke, CPU/RAM ve paketli izin kimliği gerçek cihaz kanıtı gerekiyor. |
| Windows paketleme | Kısmen var | tauri.windows.bundle.conf.json; desktop_build/windows, Windows speech helper | macOS-only varsayımı bütün ürün için doğru değil. Windows gerçek kurulum/izin/DPI/input kabulü henüz yapılmadı. |
| Paketli uygulama/CI/parite | Açık kabul | Mevcut Python/App/Kits/browser testleri; paketli/native ve canlı matris ayrı | Unit test sayısı kurulum, 72 saat dayanıklılık veya Claude/Codex paritesi kanıtı değildir. |

## Geniş fazların sınırı

Ana planın VS Code, kimlikli uzaktan görev servisi, cihaz eşleştirme, Telegram ve mobil PWA fazları için bu ön inceleme uçtan uca mevcut/eksik kararı vermiyor. Mevcut gateway, stdio protokolü veya Kits sunucusu aynı güvenlik sözleşmesine sahip uzaktan görev servisi sayılmayacak. Bu fazları ikinci bir LLM motoru yazarak veya kimliksiz internet bind açarak hızlandırmak uygun değil.

Marka bölümü son kullanıcı yönlendirmesiyle güncellendi: şeffaf F, Inter/JetBrains Mono, sistem SF başlıkları ve mavi/camgöbeği/mor vurgu uygulanıp görsel onay aldı. Kullanıcı sonradan eski yeşilin tamamen kaldırılmasını açıkça istedi; ilk küçük detay sınırının yerini bu yeni istek aldı. Basit soyut ana karakter ve sekiz özgün Kit de 15 Ekim'de tam UI setiyle birlikte onaylandı. Kaynak/üretim/lisans/SHA kayıtları docs/marka/ altındadır. Bu görsel onay kalan güvenilirlik, model ve native kabul koşullarını kapatmaz.

## Sonuç

Bu belge tam master-plan audit'i veya tamamlanmış faz matrisi değildir. Doğrulanan hataları, korunması gereken mevcut mekanizmaları ve yeni regresyon gerektiren noktaları ayırır. Sonraki uygulamada önce açık P5–P16 kabul koşulları kapatılmalı; sonra master maddeleri kaynak ve davranış testleriyle tek tek güncellenmelidir. Push/merge/yayın yapılmadı.
