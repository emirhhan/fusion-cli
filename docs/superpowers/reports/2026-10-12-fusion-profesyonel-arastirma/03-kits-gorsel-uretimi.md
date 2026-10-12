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
