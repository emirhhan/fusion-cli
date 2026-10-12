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
