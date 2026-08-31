# ChatGPT Benzeri Fusion Talk Tasarımı

## Amaç

Fusion Talk, yazılı sohbetin sesli uzantısı olacak. Kullanıcı doğal biçimde konuşacak, sözleri konuşma sırasında ekranda belirecek, sessizlik mesaj üretmeyecek ve kullanıcı araya girdiğinde Fusion konuşmayı bırakıp dinlemeye geçecek. Ana uygulama kapandığında mikrofon, tanıma ve seslendirme süreçleri de kapanacak.

Bu tasarım mevcut macOS Talk uygulamasını düzeltir ve Windows sürümünün kullanacağı ortak davranış sözleşmesini tanımlar. macOS ilk teslimat platformudur.

## Ürün sözleşmesi

Talk şu davranışları garanti eder:

- Mikrofon yalnız arayüz açıkça “Dinliyorum” durumundayken ses toplar.
- Sessizlik, ortam gürültüsü veya düşük güvenli tek sözcük bir kullanıcı mesajı oluşturmaz.
- Kısmi metin konuşma sırasında görünür. Yalnız doğrulanmış son metin sohbete gönderilir.
- Doğrulanmış bir konuşma turu aynı sohbete tam bir kez gönderilir.
- Kullanıcı Fusion konuşurken söze girerse seslendirme en geç 250 ms içinde durur ve Talk dinlemeye geçer.
- Kullanıcı doğal bir kısa duraklama yaptığında cümle erken gönderilmez. Konuşma sonu, ses etkinliği ve tanıyıcı kararlılığı birlikte değerlendirilir.
- Her dinleme turu yeni bir oturum kimliği alır. Eski oturumun metni, bitiş olayı veya zamanlayıcısı yeni oturumu etkileyemez.
- Talk penceresini kapatmak yalnız Talk kaynaklarını; Fusion uygulamasını kapatmak bütün Talk, TTS ve yardımcı süreçlerini sonlandırır.
- Görünümü mini veya normal yapmak etkin oturumu yeniden başlatmaz.
- Sesli işlem onayı yalnız açık ve yüksek güvenli kabul/ret sözüyle verilir. Belirsiz metin hiçbir işlem yapmaz.

## Mimari

Sistem dört bağımsız parçaya ayrılır:

1. **Ses yakalama ve etkinlik algılama:** Yerel yardımcı süreç mikrofon tamponlarını alır, ses etkinliğini ölçer ve yalnız gerçek konuşma bulunan aralığı tanıyıcıya iletir. Gürültü tabanı oturum başında kısa bir kalibrasyonla belirlenir.
2. **Akışkan konuşma tanıma:** Platform adaptörü `hazir`, `ses-basladi`, `kismi`, `son`, `ses-bitti` ve `hata` olaylarını JSONL olarak yayınlar. Metin olayları oturum kimliği, segment güveni ve zaman bilgisi taşır.
3. **Talk koordinatörü:** React tarafındaki tek durum makinesi VAD, STT, TTS, onay ve pencere olaylarını birleştirir. Gönderme kararı yalnız bu katmanda verilir.
4. **Seslendirme koordinatörü:** TTS oynatımı iptal edilebilir bir tur kimliği kullanır. Mikrofon gerçek konuşma algıladığında koordinatör oynatımı keser ve yeni dinleme turunu başlatır.

Parçalar birbirinin iç durumunu okumaz. Olay sözleşmeleri oturum kimliğiyle ilişkilendirilir.

## Tanıma ve sessizlik kapısı

Mevcut Apple `SFSpeechRecognizer` çıktısının tek başına final sayılması yasaktır. “Evet” gibi sessizlik halüsinasyonlarını önlemek için bir tur ancak şu koşulların tümünü sağladığında gönderilir:

- VAD en az 250 ms gerçek konuşma algılamıştır.
- Tanınan metin boş değildir.
- En az bir segment kabul eşiğini geçen güven puanı taşır.
- Son kısmi metin, kısa bir kararlılık penceresinde değişmeden kalmıştır veya tanıyıcı gerçek final olayı vermiştir.
- Oturum hâlâ etkin oturumdur.

Tek sözcüklü kısa yanıtlar yasaklanmaz. Ancak düşük güvenli tek sözcükler, özellikle sessizlikte üretilenler, ekranda “Anlayamadım, tekrar söyle” durumuna dönüşür ve sohbete gönderilmez. Sabit bir sözcüğe özel filtre kullanılmaz; karar ses etkinliği ve güven verisine dayanır.

Apple çevrimdışı Türkçe tanıma bu eşiklerle güvenilir sonuç vermezse Fusion otomatik olarak metin uydurmaz. Kullanıcıya iki açık seçenek sunar:

- **Yerel ve özel:** Cihaz üstü tanıma; ses cihazdan çıkmaz.
- **Daha doğru çevrimiçi tanıma:** Yalnız kullanıcı açıkça etkinleştirirse ses seçilen hizmete gönderilir.

Çevrimiçi kip varsayılan değildir ve izin ekranı hangi verinin nereye gönderileceğini açıklar. İlk macOS teslimatı yerel kipi eksiksiz çalıştırır; çevrimiçi sağlayıcı ayrı bir adaptördür.

## Durum makinesi

Durumlar:

- `idle`: Mikrofon kapalıdır.
- `calibrating`: Kısa gürültü tabanı ölçülür.
- `listening`: Mikrofon açıktır, konuşma beklenir.
- `hearing`: Gerçek ses algılanmıştır.
- `transcribing`: Kısmi metin güncellenir.
- `thinking`: Doğrulanmış metin sohbete gönderilmiştir.
- `talking`: Fusion sesli yanıt verir.
- `interrupted`: Kullanıcı TTS'yi kesmiştir; oynatım kapanırken ses tamponları korunur.
- `approval`: Açık bir işlem onayı beklenir.
- `error`: Kullanıcıya neden ve tekrar deneme eylemi gösterilir.

Her geçiş bir tur kimliği taşır. `talking → interrupted → hearing` geçişi barge-in yoludur. `idle`, `error` veya pencere kapanışı mikrofon tap'ini ve ilgili yardımcı süreci bırakır.

## Barge-in ve yankı önleme

Fusion konuşurken mikrofon, yalnız kesme algılamak için düşük gecikmeli dinleme yapabilir. Oynatılan TTS sesi kullanıcı konuşması sayılmamalıdır. İlk macOS sürümü bunu üç savunmayla sağlar:

- TTS oynatımının zaman aralığı ve ses seviyesi koordinatöre bildirilir.
- VAD, hoparlör çıkışıyla yüksek benzerlik gösteren sesi konuşma başlangıcı saymaz.
- Kullanıcı sesi eşiği geçtiğinde TTS oynatımı iptal edilir; tanıyıcıya yalnız kesme anından sonraki temiz tamponlar verilir.

Kulaklık kullanımı doğal olarak en iyi sonucu verir, fakat ürün hoparlörde de çalışmak zorundadır. Yankı önleme başarısızsa Talk sessizce metin göndermez; kullanıcıya anlaşılır bir yeniden deneme durumu gösterir.

## Süreç yaşam döngüsü

Rust `SpeechManager`, etkin yardımcı sürecin tek sahibidir. `TtsManager` etkin oynatımın tek sahibidir. Her ikisi de uygulama kapanışının senkron temizleme zincirine katılır.

Kapanış sırası:

1. Yeni ses ve tanıma olaylarını kabul etmeyi durdur.
2. TTS oynatımını iptal et.
3. Mikrofon tap'ini kaldır ve tanıma isteğini bitir.
4. Yardımcı süreçlere sonlandırma sinyali gönder.
5. Kısa sonlanma süresini bekle; süre aşılırsa süreçleri zorla kapat.
6. Pencereleri ve ana süreci kapat.

Talk penceresinin kırmızı düğmesi aynı temizliği yalnız Talk kaynakları için uygular ve ana pencereyi geri getirir. Uygulama menüsündeki Çık ve son pencerenin kapanması bütün kaynakları temizler. Fusion kapandıktan sonra `fusion-listen`, TTS oynatıcısı veya mikrofon göstergesi kalamaz.

## macOS Talk penceresi

Talk ayrı bir yardımcı penceredir; web sayfası gibi davranmaz.

- Normal görünüm içerik ağırlıklı, mini görünüm tek satırlı yardımcı paneldir.
- Başlık şeridinin boş alanı gerçek `data-tauri-drag-region` taşır. Düğmeler sürükleme alanına girmez.
- Kırmızı düğme Talk'ı kapatır, sarı düğme küçültür, yeşil düğme mini ve normal görünüm arasında geçer.
- Düğmeler aynı çapta, aynı optik merkezde ve macOS aralık düzenindedir. İkonlar varsayılan durumda görünmez; hover/focus sırasında belirir.
- Pencere yaklaşık 16 px görsel köşe yarıçapı kullanır. Webview kökü ve pencere yüzeyi aynı şekli paylaşır; arkada ikinci dikdörtgen veya çift çerçeve görünmez.
- Yüzey yüzde 90–94 opaktır ve okunabilirliği koruyan hafif materyal etkisi taşır.
- Mini görünümde avatar, canlı durum, mikrofon ve normal görünüme dönüş eylemi kalır.
- Açık ve koyu temalarda Fusion logosu, yeşil marka vurgusu ve erişilebilir kontrast korunur.
- Klavye odağı, VoiceOver adları ve azaltılmış hareket tercihi desteklenir.

## Hata davranışı

Talk teknik hata kodu yerine eyleme dönük durum gösterir:

- İzin yok: “Mikrofon erişimi kapalı” ve Sistem Ayarlarını Aç.
- Ses var, güvenilir metin yok: “Anlayamadım, tekrar söyle.”
- Tanıyıcı kullanılamıyor: yeniden dene ve tanıma kipi seç.
- Yardımcı süreç kapandı: temiz bir yeni oturum başlat; art arda iki başarısızlıkta otomatik döngüyü durdur.
- TTS kesilemedi: oynatımı zorla kapat ve dinlemeyi başlatmadan önce temizlendiğini doğrula.

Hata sırasında eski transkript gönderilmez. Yeniden deneme her zaman yeni oturum kimliği oluşturur.

## Test stratejisi

### Birim testleri

- Sessizlik ve düşük güvenli “Evet” gönderilmez.
- Gerçek ses ve yeterli güven taşıyan tek sözcük gönderilebilir.
- Eski oturumun kısmi, final, bitiş ve zamanlayıcı olayları reddedilir.
- Final metin yalnız bir revizyon üretir.
- Barge-in TTS iptalini dinleme başlangıcından önce tamamlar.
- Mini/normal geçişi etkin tanımayı değiştirmez.

### Entegrasyon testleri

- Yardımcı süreç VAD ve güven alanlarıyla doğru JSONL yayınlar.
- Talk kapanışı speech ve TTS çocuklarını bırakmaz.
- Ana uygulama kapanışı bütün çocuk süreçleri sonlandırır.
- Hızlı durdur/başlat işlemleri tek etkin yardımcı süreç bırakır.
- İzin reddi ve sonradan izin verme temiz biçimde toparlanır.

### Paketli kabul

- Kullanıcı üç farklı Türkçe cümle söyler; her biri doğru ve bir kez görünür.
- On saniye sessizlik hiçbir mesaj üretmez.
- Fusion konuşurken kullanıcı araya girer; ses durur ve yeni söz yazılır.
- Ana uygulama kapatılır; mikrofon göstergesi, TTS ve `fusion-listen` kapanır.
- Normal ve mini pencere sürüklenir; trafik ışıkları doğru davranır.
- Açık/koyu, normal/mini ekran görüntüleri kullanıcıya gösterilir.

## Başarı ölçütleri

- Sessizlikte yanlış mesaj oranı, on adet 10 saniyelik testte sıfırdır.
- Üç belirgin Türkçe cümlenin en az üçü de anlamını koruyarak yazılır; sürekli aynı sözcük üretme kabul edilmez.
- Kullanıcının söze girmesi TTS'yi 250 ms hedefiyle, en geç 500 ms içinde keser.
- Her konuşma turu sohbette tam bir kullanıcı mesajı oluşturur.
- Uygulama kapandıktan iki saniye sonra Talk'a ait çocuk süreç kalmaz.
- Pencere her görünümde sürüklenebilir, tek yüzeyli ve görsel olarak dengelidir.
- React, Rust, Swift sözleşme, süreç yaşam döngüsü ve Playwright görsel testleri geçer.

## Kapsam dışı

- Sürekli arka plan dinleme veya uyandırma sözcüğü.
- Kullanıcının açık onayı olmadan bulut tabanlı ses aktarımı.
- İlk macOS teslimatında çok konuşmacılı ayırma.
- Ses kaydı arşivi tutma.

