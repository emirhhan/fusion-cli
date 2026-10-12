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
