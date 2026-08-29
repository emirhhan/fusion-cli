# Fusion Tam macOS Uygulaması — Ürün ve Mimari Tasarımı

**Tarih:** 29 Ağustos 2026

**Durum:** Uygulama öncesi onaylanmış ürün tasarımı

**Platform önceliği:** macOS

## 1. Amaç

Fusion, kodlama bilmeyen bir kullanıcının da profesyonel yazılım, oyun ve içerik projeleri üretebildiği; buna karşılık deneyimli bir kullanıcının dosyalara, araç çağrılarına, terminallere, testlere, modellere, sağlayıcılara ve çalışma geçmişine kadar her ayrıntıyı denetleyebildiği gerçek bir masaüstü uygulaması olacaktır.

Uygulama yalnızca mevcut web kontrol panelini bir pencereye sarmayacaktır. Tauri 2 tabanlı yerel bir macOS kabuğu, uygulamayla birlikte taşınan Fusion/Python çalışma zamanı ve React tabanlı ürün arayüzünden oluşacaktır. İndirilen DMG içindeki uygulama, sistemde Python veya `fusion` komutu bulunmasa da çalışacaktır.

Bu tasarım mevcut dar masaüstü prototipini genişletir ve ürün kapsamı bakımından `2026-08-29-masaustu-uygulamasi-design.md` belgesinin yerini alır. CLI, `fusion serve` ve ortak Python çekirdeği korunur.

## 2. Ürün ilkeleri

1. **Başlangıç basit, derinlik isteğe bağlıdır.** Kullanıcı ilk ekranda sohbet eder ve proje üretir. Dosya değişiklikleri, ham günlükler, süreçler ve gelişmiş ayarlar gerektiğinde açılır.
2. **Her işlem görünür ve geri alınabilir olmalıdır.** Fusion; hangi dosyayı değiştirdiğini, hangi komutu çalıştırdığını, neyin başarılı olduğunu ve neyin kanıtlanamadığını açıkça gösterir.
3. **Uygulama kendi çalışma zamanını yönetir.** Kullanıcıdan Python, sanal ortam veya terminal kurulumu beklenmez.
4. **CLI, uygulama ve sunucu aynı üründür.** İş kuralları Python çekirdeğinde paylaşılır; üç ayrı uygulamada kopyalanmaz.
5. **Bağlam sürekliliği ile yeni konuşma ayrılır.** “Devam et” açık işi sürdürür; “merhaba” tamamlanmış eski bir görevin araç zorunluluğunu miras almaz.
6. **Güvenlik yeteneği sakatlamaz.** Fusion `.env` dahil proje dosyalarını okuyabilir ve düzenleyebilir. Sırlar arayüzde bütünüyle gösterilmez; günlüklerde maskelenir; kullanıcıya ne yapıldığı sade Türkçeyle anlatılır.
7. **Görsel kalite sistematiktir.** Ekranlar tek bir tasarım dili, ölçü sistemi ve etkileşim modeli kullanır; rastgele kartlar veya “AI tarafından yapılmış” görünen süslemeler kullanılmaz.

## 3. Platform ve dağıtım

### 3.1 macOS uygulaması

- Uygulama Tauri 2 ile paketlenir.
- İlk hedef Apple Silicon ve Intel macOS'tur. Mimariye uygun çalışma zamanı her dağıtımda ayrı üretilir; evrensel DMG ancak iki çalışma zamanı birlikte doğrulandığında sunulur.
- Dağıtım `.app` ve sürükle-bırak kurulumlu `.dmg` olarak yapılır.
- Apple Developer hesabı olmadığı için ilk sürüm imzasız ve notarize edilmemiştir. İndirme sayfası ve DMG, ilk açılış için kısa ve dürüst bir macOS yönergesi gösterir. Uygulama içinden güvenlik mekanizmasını aşan komut çalıştırılmaz.
- Uygulama güncelleme denetimi yapabilir; imzasız dönemde güncellemeyi kullanıcı indirip kurar. Sessiz otomatik kurulum yapılmaz.

### 3.2 Bağımsız çalışma zamanı

Python/Fusion çalışma zamanı PyInstaller `onedir` çıktısı olarak üretilir. `onefile` kullanılmaz; açılışta her seferinde çıkarma gecikmesi ve geçici dosya belirsizliği kabul edilmez.

Uygulama paketi, sürüm numarası ve SHA-256 manifesti bulunan sıkıştırılmış çalışma zamanı arşivini taşır. İlk açılışta:

1. İşletim sistemi ve mimari doğrulanır.
2. Arşiv geçici, uygulamaya özel bir dizine çıkarılır.
3. Dosya özetleri manifestle karşılaştırılır.
4. `fusion app health --json` benzeri protokol sağlık denetimi çalıştırılır.
5. Başarılı sürüm `~/Library/Application Support/Fusion/runtime/<version>/` altına atomik olarak taşınır.
6. `active-runtime.json` yalnız başarılı kurulumdan sonra güncellenir.

Kullanıcı verisi, konuşmalar, ayarlar ve günlükler çalışma zamanı klasöründen ayrı tutulur. Güncelleme başarısız olursa son sağlıklı sürüme dönülür. Ayarlardaki **Çalışma zamanını onar** eylemi paket içindeki doğrulanmış arşivden yeniden kurar; kullanıcı projelerine ve konuşmalarına dokunmaz.

Normal ürün modunda sistemdeki `fusion` ikilisi yedek olarak kullanılmaz. Böylece farklı sürümlerin sessizce karışması engellenir. Sistem çalışma zamanı yalnız açıkça etkinleştirilen, uyarılı **Geliştirici Modu** altında seçilebilir.

Bu yaklaşım Tauri'nin Python CLI/API sunucularını sidecar olarak paketleme modeline, JupyterLab Desktop'ın kullanıcı dizinine sürümlü Python ortamı kurup onarma yaklaşımına ve Spyder'ın kendi Python ortamını taşıyan bağımsız kurulumuna dayanır.

## 4. Sistem mimarisi

### 4.1 Katmanlar

- **React arayüzü:** ürün ekranları, yerel durum, erişilebilir etkileşimler ve görsel sistem.
- **Tauri/Rust kabuğu:** pencere yaşam döngüsü, çalışma zamanı kurulumu, süreç yönetimi, dosya seçiciler, bildirimler ve işletim sistemi entegrasyonu.
- **Fusion uygulama protokolü:** satır bazlı JSON mesajlaşma; istek kimliği, olay sırası, sürüm uzlaşması, iptal ve yapılandırılmış hata taşır.
- **Python çekirdeği:** agent döngüsü, sağlayıcılar, model yönlendirme, araçlar, bellek, beceriler, geçmiş içe aktarma, MCP, yapılandırma ve gateway.

İş kuralları React veya Rust içinde yeniden yazılmaz. Rust yalnız güvenilir süreç ve işletim sistemi sınırını yönetir.

### 4.2 Süreç modeli

- Bir ana uygulama penceresi vardır.
- Her etkin konuşma/iş oturumu kendi `fusion app` alt sürecine sahiptir.
- Süreç yöneticisi oturum kimliği, PID, proje yolu, protokol sürümü, son kalp atışı ve kapanış nedenini izler.
- Arka plandaki oturumlar kontrollü biçimde yaşamaya devam edebilir; kaynak sınırı aşıldığında en eski boş oturumlar durumları kaydedilerek kapatılır.
- Uygulama kapanırken çalışan görevler için kullanıcıya bekleme, durdurma veya arka plan desteği mümkünse sürdürme seçenekleri sunulur.
- Çöken süreç yalnız kendi konuşmasını etkiler. Arayüz son olayı, günlük konumunu ve **Yeniden bağlan** eylemini gösterir.

### 4.3 Protokol alanları

Protokol aşağıdaki alanları tipli istek, yanıt ve akış olaylarıyla kapsar:

- oturum oluşturma, açma, kapatma, iptal ve yeniden deneme;
- mesaj gönderme ve parça parça yanıt;
- plan, araç çağrısı, komut çıktısı, dosya değişikliği, test ve onay olayları;
- proje seçme, dosya ağacı, okuma, güvenli yazma ve diff;
- terminal ve geliştirme sunucusu süreçleri;
- geçmiş kaynaklarını keşfetme, listeleme, önizleme ve sürdürme;
- beceri, ajan, MCP ve proje talimatlarını keşfetme;
- model, sağlayıcı, izin, bellek ve görünüm ayarları;
- gateway durumu, başlatma, durdurma ve güvenli yapılandırma;
- tanılama, sağlık, çalışma zamanı sürümü ve onarım ilerlemesi.

Arayüz ham stdout metnini anlamlandırmaya çalışmaz. Kullanıcıya gösterilecek her önemli durum yapılandırılmış olaydır. Bilinmeyen yeni olay türleri uygulamayı çökertmez; günlükte saklanır ve uyumluluk uyarısı gösterilir.

### 4.4 Durum sahipliği

- Proje dosyaları proje klasöründe kalır.
- Kullanıcı yapılandırması Python çekirdeğinin kanonik yapılandırma katmanında kalır.
- Pencere boyutu, açık paneller ve görünüm tercihleri Tauri uygulama ayarlarında tutulur.
- Oturum ve içe aktarılan geçmiş indeksleri Fusion veri dizininde tutulur.
- Gizli anahtarlar mevcut Fusion kimlik bilgisi katmanından yönetilir; arayüz bunları varsayılan olarak maskeler.
- CLI, uygulama ve gateway eşzamanlı yazımlarında dosya kilidi ve sürüm/karşılaştırma denetimi kullanılır. Eski bir anlık görüntü yeni ayarı sessizce ezemez.

## 5. Bilgi mimarisi

### 5.1 Sol kenar çubuğu

1440 piksel genişlikte sol sütun tam **281 piksel** olur. İçeriği:

- yeni görev;
- konuşma ve proje araması;
- sabitlenen ve yakın projeler;
- yakın konuşmalar;
- kaynak etiketleri: `[fusion]`, `[claude]`, `[codex]`, `[hermes]`;
- Beceriler ve Ajanlar;
- Dersler;
- Kontrol Paneli;
- Ayarlar ve yardım.

Kenar çubuğu daraltıldığında ikon şeridine dönüşür; içerik kaybolmaz. Aktif satır açık gri seçili yüzeyle gösterilir. Sık kullanılmayan eylemler satır üzerine gelindiğinde görünür.

### 5.2 Ana çalışma alanı

Ana alan konuşma ve yürütme akışıdır:

- kullanıcı mesajı sağa yaslı açık gri balon;
- Fusion yanıtı balonsuz, okunabilir tam genişlik;
- canlı düşünme durumu yerine anlaşılır çalışma adımları;
- açılıp kapanan plan, araç, terminal, test ve dosya değişikliği blokları;
- izin/onay kartları;
- görsel, dosya ve klasör sürükleyip bırakma;
- `/` komut menüsü;
- model, kip ve düşünme düzeyi seçimi;
- durdur, yeniden dene, devam et ve geri al eylemleri.

Başarılı araç çıktıları varsayılan olarak kısa özetlenir; hata ve doğrulama kanıtları görünür kalır. Ham günlük bir tıkla açılır.

### 5.3 Sağ denetçi

Sağ panel sekmeli ve bağlama duyarlıdır:

- Dosyalar
- Değişiklikler
- Terminal
- Süreçler
- Testler
- Önizleme
- Beceriler/Ajanlar
- Bağlam/Oturum

Geniş ekranda sabit, orta genişlikte daraltılabilir, küçük pencerede ana alanın üzerine gelen paneldir. Kullanıcının son genişliği hatırlanır.

## 6. Görsel sistem

Verilen ChatGPT UI Kit Figma dosyası ürünün görsel referansıdır; yapı birebir kopyalanırken Fusion'ın marka ve işlevlerine uyarlanır. Ölçüler göz kararıyla değil, ortak tasarım tokenlarıyla uygulanır.

Temel açık tema:

| Token | Değer | Kullanım |
|---|---:|---|
| Ana zemin | `#FFFFFF` | konuşma ve içerik |
| Kenar çubuğu | `#F9F9FA` | sol navigasyon |
| Seçili yüzey | `#EFEFF0` | aktif satır/sekme |
| Kullanıcı balonu | `#F5F5F5` | kullanıcı mesajı |
| Ana metin | `#000000` | başlık ve içerik |
| Vurgu yüzeyi | `#EBEBFA` | seçili yardımcı durum |
| İkincil metin | `#7C7C7D` | metadata ve açıklama |
| Sınır | `#E9E9EB` | ayırıcı ve giriş sınırı |

- Tipografi Inter ve sistem yedekleriyle kurulur.
- Dikey ritim 4 piksel tabanlıdır; ana boşluklar 8, 12, 16, 24 ve 32 pikseldir.
- Köşe yuvarlama öğenin işlevine göre sınırlıdır; her yüzey karta dönüştürülmez.
- Gölge yalnız katman ayrımı gerektiğinde kullanılır.
- İkonlar tek aileden, aynı çizgi kalınlığında ve dekoratif olmayan biçimde kullanılır.
- Hareket 120–220 ms aralığında, kesintisiz ve işlevseldir. Sistem “hareketi azalt” ayarına uyulur.
- Koyu tema aynı hiyerarşiyi koruyan ayrı semantik tokenlarla sunulur.

### 6.1 Kontrol paneli görünümü

Kontrol Paneli eski web yönetim ekranı gibi ayrı bir tasarıma sahip olmayacaktır. Sol navigasyon, üst başlık, satır yoğunluğu, tipografi, renkler, sekmeler, açılır paneller ve form elemanları uygulamanın Figma tabanlı sistemiyle aynıdır.

Kontrol paneli ana bölümleri:

- Genel durum
- Modeller ve sağlayıcılar
- API anahtarları
- Yönlendirme ve yedek zinciri
- İzinler
- Web ve tarayıcı
- MCP sunucuları
- Beceriler ve ajanlar
- Bellek ve geçmiş
- Gateway / `fusion serve`
- Çalışma zamanı ve tanılama

Özet ekranında gereksiz gösterge panosu kartları kullanılmaz. Sağlık, aktif model, çalışan gateway, son hata ve gereken eylemler yoğun ama okunaklı satırlar halinde sunulur. Ayrıntı sayfaları iki sütunlu ayar düzeni ve bağlamsal açıklamalar kullanır.

Mevcut `/dashboard`, bağımsız tarayıcı erişimi gereken kullanıcılar için korunur ve aynı web tokenları/bileşenleriyle görsel olarak yakınlaştırılır. Native uygulamadaki Kontrol Paneli ise protokol üzerinden çalışır; iframe veya localhost web görünümü değildir.

## 7. Oturumlar, geçmiş ve sürdürme

Uygulama bilgisayarda kurulu ve erişilebilir kaynakları keşfeder. Yalnız bulunan kaynaklar önerilir:

- `/resumeclaude`
- `/resumecodex`
- `/resumehermes`

Komut seçildiğinde doğrudan en son sohbet açılmaz. Önce kaynak içindeki sohbetler başlık, tarih, proje ve kısa özetle listelenir. Kullanıcı arar, filtreler, önizler ve hangisini sürdüreceğini seçer. Önizleme; ilgili dosyaları, son talebi, tamamlanan işleri ve açık kalan maddeleri gösterir.

Geçmiş aşamalı okunur; tüm arşiv başlangıçta belleğe yüklenmez. Kaynağa ait talimatlar, proje kuralları, anılar, beceriler ve ajan tanımları ayrı olarak keşfedilir. Kullanılabilir olduklarında kaynak etiketiyle gösterilir; Fusion içine kopyalanan veya o turda etkin kullanılan öğe kullanıcı tarafından görülebilir.

Bir dış sohbet sürdürüldüğünde özgün kaynak değiştirilmez. Fusion kendi devam oturumunu oluşturur ve kaynağa bağlantıyı metadata olarak korur.

## 8. Beceriler, ajanlar ve MCP

**Beceriler ve Ajanlar** ekranı şunları tek katalogda gösterir:

- Fusion'ın yerleşik yetenekleri;
- proje içi talimat ve beceriler;
- Claude, Codex ve Hermes kaynakları;
- kurulu MCP sunucuları ve araçları.

Her öğede kaynak, açıklama, izin kapsamı, etkinlik durumu, son kullanım ve otomatik eşleşme bilgisi bulunur. Otomatik seçim yapıldığında sohbet akışında kısa bir bildirim görünür. Kullanıcı öğeyi oturum için kapatabilir veya açıkça çağırabilir.

Kaynak dosyaları körlemesine çalıştırılmaz. Talimat metni okunabilir; komut veya ağ yetkisi gereken beceriler standart onay sistemi üzerinden ilerler. MCP tanımı eklemek, özellikle yerel komut çalıştıracaksa açık onay ve kaynak gösterimi ister.

## 9. Proje çalışma alanı

Uygulama aşağıdaki üretim akışlarını tek pencerede destekler:

- proje seçme, son projeler ve yeni klasör oluşturma;
- dosya ağacı, metin/kod görüntüleme ve kontrollü düzenleme;
- değişiklik diff'i ve dosya bazında geri alma;
- görsel, ses, video ve PDF önizleme;
- birden fazla terminal ve süreç yönetimi;
- geliştirme sunucusu başlatma/durdurma;
- uygulama veya web önizlemesi;
- test, lint ve build sonuçları;
- Git durumu ve geçmişi;
- agent işlemlerinin Türkçe özeti ve isteğe bağlı ham çıktı.

Fusion'ın oluşturduğu asset'ler dosya ağacında ve konuşmada görünür. Yalnız HTML/CSS ile oluşturulan bir projede asset bulunmamasının nedeni kullanıcıya açıkça söylenebilir; bu durum hata gibi sunulmaz.

## 10. İzinler, sırlar ve onaylar

Fusion'ın amacı kullanıcının bilgisayarında gerçek iş yapmaktır. Bu nedenle genel bir “`.env` okunamaz” kuralı yoktur. Davranış şöyledir:

- Fusion görev için gerekliyse `.env` okuyabilir, oluşturabilir ve düzenleyebilir.
- Arayüz anahtarları tam değerleriyle sohbet metnine veya günlüklere yazmaz.
- Anahtarın bulunduğu ve hangi sağlayıcı için kullanıldığı söylenebilir.
- Bir sır istemeden normal metne yazılmışsa kullanıcıya sade bir uyarı ve gerekirse değiştirme önerisi verilir; bu öneri her turda tekrarlanmaz.
- “Redaksiyon” gibi teknik sözcükler açıklamasız kullanılmaz; “gizli değeri ekranda sakla” denir.

Onay düzeyleri ayarlanabilir:

- yalnız okuma;
- proje içinde düzenleme;
- proje dışı dosya erişimi;
- komut çalıştırma;
- ağ ve dış servis;
- kalıcı yapılandırma veya anahtar değişikliği.

Onay kartı ne yapılacağını, nerede yapılacağını ve olası etkisini tek bakışta gösterir. Aynı güvenli kapsam için oturumluk izin verilebilir. Yıkıcı ve geri alınamaz işlemler daima özel onay ister.

## 11. Gateway ve `fusion serve`

Uygulama, CLI'daki `fusion serve` işlevini yönetebilir:

- başlat/durdur;
- port ve bağlanma adresi;
- yerel ağ erişimi;
- etkin istemciler ve uçlar;
- model/yönlendirme/sağlayıcı durumu;
- istek ve hata günlükleri.

Varsayılan bağlanma `127.0.0.1` kalır. `0.0.0.0` veya yerel ağ seçilirse sonuçları açıkça anlatan uyarı gösterilir. Durum değiştiren HTTP uçları Origin doğrulaması, yerel oturum anahtarı ve CSRF koruması olmadan çalışmaz. Panel anahtarı sağlayıcı anahtarlarından ayrıdır ve döndürülebilir.

Desteklenmeyen yöntemler doğru `405 Method Not Allowed` yanıtı verir. Uygulama, CLI ve panel aynı ayarı eşzamanlı değiştirirse kilit/sürüm denetimi çakışmayı görünür kılar; sessiz kayıp güncelleme olmaz.

## 12. İlk açılış ve dersler

İlk açılış akışı en fazla birkaç kısa adımdır:

1. çalışma zamanı kurulur ve doğrulanır;
2. Claude/Codex/Hermes geçmiş kaynakları bulunur;
3. mevcut sağlayıcılar ve anahtarların yalnız varlığı gösterilir;
4. bir proje seçilir veya örnek proje başlatılır;
5. izin yaklaşımı sade biçimde açıklanır.

Kullanıcı ana ekrana geçmeden hesap açmaya zorlanmaz. Ağ sağlayıcısı yoksa yerel/uygun seçenekler ve kurulum yolu anlatılır.

Etkileşimli dersler:

- ilk proje;
- basit oyun veya web sitesi;
- asset ekleme ve önizleme;
- model ve düşünme düzeyi;
- izinler ve geri alma;
- geçmiş sürdürme;
- beceri ve ajan kullanma;
- test etme, paketleme ve paylaşma.

Dersler ayrı bir doküman okuyucusu değildir; gerçek çalışma alanında güvenli, küçük görevlerle ilerler ve kaldığı yeri hatırlar.

## 13. Hata kurtarma ve tanılama

Kullanıcıya yalnız “işlem başarısız” denmez. Hatalar şu sınıflarla gösterilir:

- model/sağlayıcı;
- izin;
- araç veya komut;
- test/doğrulama;
- çalışma zamanı;
- protokol;
- dosya/config çakışması;
- ağ/gateway.

Her hata kartı kısa açıklama, güvenli sonraki eylem ve ayrıntı bağlantısı içerir. Tanılama paketi oluşturulurken gizli değerler maskelenir; kullanıcı paketin içeriğini kaydetmeden önce görebilir.

Bellek altyapısı yalnız ihtiyaç duyulduğunda yüklenir. `fusion stats` gibi salt istatistik komutları embedding modelini başlatmaz. Veritabanı kilitlenmesinde sonsuz bekleme yerine zaman aşımı, anlaşılır “başka Fusion işlemi kullanıyor” mesajı ve yeniden deneme sunulur.

## 14. Erişilebilirlik ve performans

- Tüm temel işlemler klavyeyle yapılabilir.
- Odak halkaları görünürdür; ekran okuyucu adları ve doğru semantik roller kullanılır.
- Renk tek başına durum taşımaz; metin veya ikonla desteklenir.
- Metin büyütmede ana görevler kaybolmaz.
- İlk pencere çalışma zamanı kurulmamış olsa da hızla açılır ve kurulum ilerlemesini gösterir.
- Büyük konuşmalar ve dosya listeleri sanallaştırılır.
- Arka plandaki ham süreç çıktısı sınırlı tampon ve disk günlüğüyle yönetilir.
- Açılış, yeni oturum, sohbetler arası geçiş ve ilk token süreleri sürüm kapılarında ölçülür.

## 15. Test ve sürüm kapıları

Bir macOS sürümü aşağıdaki katmanlar geçmeden tamamlanmış sayılmaz:

1. Python birim ve entegrasyon testleri.
2. React bileşen, durum ve erişilebilirlik testleri.
3. Rust çalışma zamanı kurulum ve süreç yöneticisi testleri.
4. Protokol sözleşme testleri: CLI, uygulama ve `fusion serve` ortak davranışları.
5. Claude/Codex/Hermes için anonimleştirilmiş geçmiş fikstürleri.
6. Masaüstü uçtan uca testleri: proje açma, mesaj, dosya değişikliği, onay, durdurma, yeniden bağlanma.
7. Figma referans ekranlarına karşı görsel regresyon.
8. Temiz macOS kullanıcı hesabında DMG kurulum testi.
9. Python ve `fusion` bulunmayan makinede açılış testi.
10. Çevrimdışı açılış ve anlaşılır sağlayıcı durumu.
11. Bozuk/eksik çalışma zamanını onarma ve önceki sürüme dönme.
12. `.app` ve `.dmg` smoke testleri; iki mimaride paket bütünlüğü.
13. Gizli değer, izin, path traversal, Origin/CSRF ve gateway erişim testleri.
14. Başlangıç süresi, bellek, uzun sohbet ve paket boyutu bütçeleri.

Görsel kabul yalnız ekran görüntüsüne bakılarak yapılmaz. Boş, yükleniyor, başarı, hata, devre dışı, taşma, küçük pencere, açık/koyu tema ve klavye durumları ayrı test edilir.

## 16. Uygulama sırası

### A. Çalışma zamanı temeli

PyInstaller `onedir` üretimi, arşiv/manifest, ilk kurulum, sağlık, sürüm seçimi, onarım, rollback ve Geliştirici Modu.

### B. Tasarım sistemi ve uygulama kabuğu

Figma tokenları, 281 piksel kenar çubuğu, ana sohbet, sağ denetçi, pencere uyarlaması, açık/koyu tema ve temel erişilebilirlik. Kontrol Paneli de aynı bileşenlerle kurulur.

### C. Oturum ve geçmiş

Çoklu süreç yöneticisi, oturum yaşam döngüsü, arama, projeler ve dinamik `/resumeclaude`, `/resumecodex`, `/resumehermes` akışları.

### D. Proje ve denetçi araçları

Dosyalar, diff, terminal, süreçler, testler, browser/app önizleme, asset görüntüleme ve Git durumu.

### E. Beceriler, ajanlar ve MCP

Kaynak keşfi, katalog, etkinleştirme, otomatik eşleşme görünürlüğü, izinler ve kullanım kayıtları.

### F. Ayarlar, Kontrol Paneli ve gateway güvenliği

Sağlayıcılar, anahtarlar, model/yönlendirme, izinler, bellek, geçmiş, gateway yönetimi, Origin/CSRF koruması ve eşzamanlı config yazımı.

### G. Onboarding ve dersler

İlk açılış, keşif, örnek proje, etkileşimli dersler ve bağlamsal yardım.

### H. Paketleme, E2E ve son kalite

DMG, mimari matris, temiz hesap, çevrimdışı/onarım senaryoları, görsel regresyon, performans ve dağıtım yönergeleri.

Her aşama kendi testleriyle tamamlanır. Mevcut sistem `fusion` yedeği, paketli çalışma zamanı gerçek uygulama ve DMG içinde doğrulanmadan kaldırılmaz; doğrulamadan sonra yalnız Geliştirici Modu'nda tutulur.

## 17. Tamamlanma ölçütleri

Ürün aşağıdakilerin tümü sağlandığında “profesyonel macOS uygulaması” olarak kabul edilir:

- DMG'den kurulan uygulama Python/CLI gerektirmeden açılır.
- Kullanıcı proje seçip gerçek bir görev tamamlayabilir, değişiklikleri ve test kanıtını görebilir.
- Aynı konuşmada bağımsız sohbet edebilir; eski görev yanlışlıkla yeni mesaja araç zorunluluğu yüklemez.
- Claude/Codex/Hermes kaynakları yalnız mevcut olduklarında görünür ve seçilebilir sohbet listesi sunar.
- Kaynak beceri, ajan ve talimatları görülebilir ve güvenli biçimde kullanılabilir.
- Dosya, diff, terminal, süreç, test ve önizleme araçları uygulamadan erişilebilir.
- Kontrol Paneli ve `/dashboard`, Figma tabanlı ortak görsel dili kullanır.
- CLI ve `fusion serve` mevcut işlevlerini korur; ortak davranış sözleşme testleri geçer.
- Gateway localhost saldırı yüzeyi Origin/CSRF ve yerel anahtarla korunur.
- Çalışma zamanı güncellenebilir, onarılabilir ve geri döndürülebilir.
- Sırlar ekranda/günlükte bütünüyle sızmaz; `.env` üzerinde görev için gerekli çalışma engellenmez.
- Tüm kritik akışlar erişilebilirlik, görsel regresyon ve paketlenmiş E2E testlerinden geçer.

## 18. Teknik dayanaklar

- [Tauri 2 sidecar belgeleri](https://github.com/tauri-apps/tauri-docs/blob/v2/src/content/docs/develop/sidecar.mdx)
- [JupyterLab Desktop Python ortamı yönetimi](https://github.com/jupyterlab/jupyterlab-desktop/blob/master/python-env-management.md)
- [Spyder bağımsız kurulum yaklaşımı](https://github.com/spyder-ide/spyder-docs/blob/master/doc/installation.rst)
- [PyInstaller kullanım ve paketleme biçimleri](https://pyinstaller.org/en/stable/usage.html)
- [conda-pack taşınabilir ortam yaklaşımı](https://conda.github.io/conda-pack/index.html)
- [Fusion için verilen ChatGPT UI Kit Figma referansı — ana dosya](https://www.figma.com/design/Ww1r27dBbLQhdtJGn5e1ub/ChatGPT-UI-Kit--AI-Chat--Community-?node-id=0-1)
- [Figma referansı — sohbet ayrıntıları](https://www.figma.com/design/Ww1r27dBbLQhdtJGn5e1ub/ChatGPT-UI-Kit--AI-Chat--Community-?node-id=665-2049)
- [Figma referansı — bileşen/ekran ayrıntıları](https://www.figma.com/design/Ww1r27dBbLQhdtJGn5e1ub/ChatGPT-UI-Kit--AI-Chat--Community-?node-id=609-5682)
- [Figma referansı — ek durumlar](https://www.figma.com/design/Ww1r27dBbLQhdtJGn5e1ub/ChatGPT-UI-Kit--AI-Chat--Community-?node-id=501-3138)

Bu tasarımda açık ürün sorusu bırakılmamıştır. Ayrıntılı uygulama planı bu belgenin kullanıcı tarafından son incelemesinden sonra hazırlanacaktır.
