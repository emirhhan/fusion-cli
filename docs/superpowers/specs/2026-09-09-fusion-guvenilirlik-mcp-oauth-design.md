# Fusion Güvenilirlik, MCP OAuth ve Sağlayıcı Yönlendirme Tasarımı

## Amaç

Fusion'ın uzun araç görevlerinde yanlış plan yüzünden aynı adımı tüketmesini önlemek,
yerel ve uzak MCP sunucularını uygulama içinden gerçekten bağlayabilmek, göreve uygun
sağlayıcıyı seçmek ve bu davranışları gerçek kullanım senaryolarıyla ölçmek.

Bu çalışma beş teslimatı tek uyumlu sürümde birleştirir:

1. stdio ve Streamable HTTP taşıyan MCP istemcisi ile OAuth giriş akışı,
2. başarısız plan adımını yeni kanıta göre yeniden kuran plan motoru,
3. oyun/asset/MCP/mevcut proje/eşzamanlı oturum senaryoları,
4. sağlayıcı yeteneklerine göre seçim ve güvenli geri dönüş,
5. tam doğrulama, commit, uzak dala gönderme, imzalı uygulama ve tek güncel DMG.

## Kapsam ve ürün davranışı

### MCP bağlantıları

`McpServerConfig` iki taşıma türünü açıkça temsil eder:

- `stdio`: `command`, `args` ve isteğe bağlı ortam değişkeni adlarıyla yerel alt süreç.
- `streamable_http`: HTTPS `url`, OAuth kaynak kimliği ve isteğe bağlı kapsamlarla
  uzak sunucu.

Eski `name/command/args` kayıtları değişmeden `stdio` olarak yüklenir. Yapılandırma
dosyasına erişim veya yenileme tokenı yazılmaz. OAuth sırları mevcut `keyring`
katmanında bağlantı kimliğine göre saklanır.

Uzak bağlantıda Fusion şu akışı uygular:

1. MCP uç noktasına başlatma isteği gönderir.
2. `401` ve `WWW-Authenticate` yanıtından korunan kaynak metadata adresini bulur.
3. RFC 9728 ve RFC 8414 metadata belgelerini doğrular.
4. Authorization Code + PKCE ve rastgele `state` üretir.
5. Sistem tarayıcısını yetkilendirme adresinde açar.
6. Yalnızca loopback üzerinde geçici callback dinler; state ve redirect URI'yi doğrular.
7. Kodu token ile değiştirir ve tokenı keyring'e yazar.
8. MCP oturumunu yeniden açar, `initialize` ve `tools/list` ile bağlantıyı sınar.

Yalnızca `http://127.0.0.1`, `http://localhost` ve HTTPS MCP URL'leri kabul edilir.
Tokenlar URL sorgusuna eklenmez. Yetkilendirme iptali tokenı yerelden siler. Sunucunun
revocation ucu varsa iptal isteği de gönderilir. Dinamik istemci kaydı sunucu metadata'sı
desteklediğinde kullanılır; desteklenmiyorsa kullanıcı arayüzü client kimliği ister.

Bağlantıların yaşam döngüsü birbirinden ayrılır. Bir MCP sunucusunun zaman aşımı veya
hatası diğer sunucuları devre dışı bırakmaz. Her sunucunun bağlantı, kimlik doğrulama,
araç keşfi ve hata durumu ayrı raporlanır. Başlatma ve araç listeleme sınırlı süre içinde
bitmezse süreç kapatılır ve kullanıcıya hangi aşamanın zaman aşımına uğradığı gösterilir.

### MCP arayüzü

Masaüstü `Connectors` ekranı bağlantı türü seçtirir. stdio için komut alanı; HTTP için
URL, kapsam ve gerektiğinde client kimliği alanları gösterilir. Her satırda durum ve
eylemler bulunur:

- Yapılandırıldı
- Giriş gerekli
- Giriş bekleniyor
- Bağlı ve keşfedilen araç sayısı
- Hata ve yeniden dene
- Giriş yap / bağlantıyı test et / çıkış yap / kaldır

Bağlantı eklemek sadece kayıt yazıp başarı göstermeyecek. Kayıt sonrası test çalışacak;
OAuth gerekiyorsa tarayıcı açılacak. Appserver protokolü ve eski gateway paneli aynı
çekirdek bağlantı hizmetini kullanacak. Yapılandırma başarılı olduğunda açık Fusion
oturumları yeni bağlantıyı yeniden başlatma gerektirmeden görecek.

### Plan motoru

Plan iki ayrı evreye ayrılır:

1. **Keşif:** mevcut dosyalar, proje türü, kurulu araçlar, ağ/kimlik gereksinimi ve
   kullanıcı isteğinin sınırları belirlenir. Bu evrede gelecekte üretilecek kesin dosya
   yolları başarı koşulu olamaz.
2. **Uygulama:** keşif kanıtından türetilen hedefler, kontroller ve bağımlılıklar kesin
   sözleşmeye dönüşür.

Bir adım doğrulanamadığında kurtarma, aynı adımı yalnızca yeni kanıt varsa tekrarlar.
Yeni kanıt hedefin yanlış olduğunu gösteriyorsa `replan_step` yalnızca başarısız adımı
ve ona bağımlı bekleyen adımları değiştirir; doğrulanmış adımlar korunur. Yeniden plan,
eski hedeflerin neden geçersiz olduğunu ve yeni hedeflerin hangi gözlemden çıktığını
kaydeder.

Her denemenin ilerleme parmak izi; okunan/değişen dosyalar, araç sonuçları, doğrulama
bulguları ve hedef sözleşmesinden hesaplanır. Aynı parmak izi tekrarlandığında çağrı
bütçesi tüketilmez; döngü erken kesilir ve bir kez yeniden planlanır. Yeniden plan da
aynı parmak izini üretirse adım açık ve eyleme dönük bir nedenle duraklatılır.

Asset görevlerinde dosya varlığı tek başına başarı değildir. Beklenen dosya türü için
minimum boyut, okunabilirlik ve gerçek içerik denetimi uygulanır. PNG/JPEG dosyaları
decoder ile açılır; sıfır bayt, 1x1 yer tutucu ve uzantısı içerikle uyuşmayan dosyalar
reddedilir. İndirilen asset için kaynak URL, lisans adı ve lisans kanıtı çalışma alanında
manifest olarak saklanır.

### Sağlayıcı yetenekleri ve yönlendirme

Her sağlayıcı oturumu doğrulanmış bir yetenek profiline sahip olur:

- araç çağrısı: native, emulated veya none,
- görsel girdi,
- web erişimi,
- uzun görev uygunluğu,
- eşzamanlı oturum güvenliği,
- son araç değerlendirmesinin zamanı ve sonucu.

Görev gereksinimleri plan öncesinde çıkarılır. Zorunlu yeteneği olmayan sağlayıcı aday
olamaz. Uzun, çok araçlı ve dosya üreten görevlerde native araç çağrısı olan sağlayıcı
öncelenir. Gemini Web gibi emulated araç sağlayıcıları kısa ve sınırlı görevlerde aday
kalır; görsel veya uzun ajan görevi için otomatik seçilmez. Kullanıcının açık model
seçimi korunur, fakat uyumsuzluk çalıştırmadan önce somut gerekçeyle gösterilir.

Geri dönüş yalnızca aynı zorunlu yetenekleri karşılayan sağlayıcılar arasında yapılır.
Bir web oturumu aynı anda güvenle paylaşılamıyorsa yönlendirici onu kilitler veya başka
hesap/sağlayıcı seçer; iki süreç aynı tarayıcı profilini eşzamanlı kullanmaz.

### Değerlendirme paketi

Yeni `production` profili küçük sentetik kod görevlerinden ayrı raporlanır. Beş görev
ailesi en az üç tekrar çalıştırılır:

1. Boş Godot projesini keşfet, geçerli ana sahne ve gerçek görsel asset üret/indir,
   manifesti yaz ve başlatma kontrolünü geç.
2. Yerel deterministik OAuth MCP sunucusuna bağlan, tarayıcı callback akışını tamamla,
   aracı keşfet, çağır ve çıkış yap.
3. Mevcut projede yanlış önceden varsayılmış dosya hedefini keşif sonrası düzelt ve
   doğrulanmış önceki adımları koru.
4. Büyük araç çıktısını proje sınırı içinde artifact'e taşı ve sonraki model çağrısında
   tekrar kullanılabildiğini kanıtla.
5. İki bağımsız sohbeti eşzamanlı çalıştır; tarayıcı profili çakışması, olay karışması
   ve sohbet geçmişi kaybı olmadığını doğrula.

Test OAuth sunucusu dış kimlik bilgisi istemez ve metadata, PKCE, state uyuşmazlığı,
token yenileme, 401 ve iptal yollarını deterministik olarak sunar. Gerçek Meta bağlantısı
ayrıca manuel smoke kapısıdır: kullanıcı kendi MCP URL'si ve hesabıyla giriş yaptıktan
sonra en az bir salt okunur araç `tools/list` ve çağrı üzerinden doğrulanır. Bu manuel
kapı kimlik bilgilerini loglamaz veya test fixture'ına yazmaz.

Rapor tekil koşu oranını ve bütün tekrarları geçen görev oranını ayrı verir. Yayın kapısı:

- birim ve entegrasyon testlerinde sıfır hata,
- production profilinde her zorunlu senaryo 3/3,
- web sağlayıcılarında araç değerlendirmesi geçmemiş oturumun mutasyon görevine
  otomatik seçilmemesi,
- paket smoke testi ve kod imzası doğrulaması.

## Bileşen sınırları

- `config`: taşıma türü ve güvenli, geriye uyumlu kalıcı yapılandırma.
- `mcp_bridge`: transport, OAuth, token deposu, bağlantı sağlığı ve araç adaptasyonu.
- `appserver/connectors`: masaüstü protokolüne durum ve eylemleri sunan hizmet.
- `app/src/settings`: bağlantı formu, OAuth ilerlemesi ve hata görünümü.
- `engines/agent`: keşif sözleşmesi, ilerleme parmak izi ve adım yeniden planlama.
- `providers` ve `gateway/routing`: görev gereksinimi ile yetenek profilini eşleştirme.
- `evals`: production senaryoları, fixture'lar, tekrarlar ve ayrı raporlama.

OAuth ve HTTP ayrıntıları appserver veya React bileşenine sızmaz. Arayüz yalnızca
bağlantı hizmetinin durum makinesiyle konuşur. Plan motoru sağlayıcı adlarını bilmez;
yönlendiriciden ihtiyaçlarını karşılayan bir model ister.

## Hata davranışı ve gözlemlenebilirlik

Kullanıcıya genel “bağlantı başarısız” veya “bütçe tükendi” yerine aşama gösterilir:

- MCP metadata bulunamadı veya geçersiz,
- tarayıcı girişi iptal edildi,
- callback state uyuşmadı,
- token değişimi reddedildi,
- MCP initialize zaman aşımı,
- araç listesi alınamadı,
- plan hedefi keşif kanıtıyla çelişti,
- aynı ilerleme parmak izi tekrarlandı,
- yeniden plan yeni bir uygulanabilir hedef üretemedi.

Olay kayıtlarında token, authorization code, cookie ve kullanıcı sırrı redakte edilir.
Her plan duraklaması son başarılı adımı, başarısız hedefi, yapılan doğrulamayı, yeniden
plan sayısını ve devam etmek için gereken eylemi içerir.

## Geriye uyumluluk ve geçiş

- Mevcut YAML MCP kayıtları `stdio` kabul edilir ve yeniden yazılmadan okunur.
- `fusion mcp-add` komutunun eski biçimi çalışmaya devam eder; HTTP seçenekleri yeni
  bayraklarla eklenir.
- Mevcut web oturumları yetenek profili yoksa ilk kullanımda değerlendirilir; değerlendirme
  tamamlanana kadar riskli mutasyon görevlerine otomatik seçilmez.
- Eski plan checkpoint'leri okunur. Keşif evresi alanı bulunmayan aktif plan, mevcut
  adımlarını korur ve ilk doğrulama hatasında yeni yeniden plan yoluna geçirilir.

## Yayın ve çalışma alanı güvenliği

Çalışma boyunca kullanıcıya ait izlenmeyen `:memory:.ses`, `app/.superpowers/` ve
`index.html` dosyalarına dokunulmaz. Her bağımsız teslimat testten sonra ayrı commit olur.
Tam kapılar geçince dal uzak depoya gönderilir. Yeni macOS uygulaması paketlenir, imzası
ve paket içindeki runtime'ın kaynak HEAD ile eşleşmesi doğrulanır. Masaüstünde yalnızca
son commit kimliğini taşıyan DMG bırakılır; eski Fusion DMG'leri kaldırılır.

## Kabul ölçütleri

1. Eski stdio Godot bağlantısı çalışır ve bir bozuk MCP diğer bağlantıları düşürmez.
2. Uzak OAuth MCP eklemek tarayıcıyı açar; callback sonrası araçlar yeniden başlatmadan
   görünür ve token yapılandırma dosyasına yazılmaz.
3. Meta benzeri uzak MCP için arayüz giriş gereksinimini ve gerçek hata aşamasını gösterir.
4. Yanlış asset yolu içeren plan aynı hedefi tüketmez; keşif kanıtıyla adımı değiştirir.
5. Sahte/boş görsel başarı sayılmaz; gerçek görsel ve lisans manifesti doğrulanır.
6. Gemini Web uzun görsel/çok araç görevine otomatik atanmaz; uygun native sağlayıcı
   varsa o seçilir.
7. Production değerlendirme profilinin beş zorunlu ailesi üçer kez geçer.
8. Python, TypeScript/React ve Rust kapıları; paket smoke ve kod imzası geçer.
9. Uzak dal tüm yeni commitleri içerir ve masaüstünde yalnızca yeni DMG kalır.

## Kapsam dışında

Bu sürüm Meta Marketing API'nin kendisini yeniden uygulamaz ve belirli bir üçüncü taraf
Meta MCP sunucusuna özel davranış eklemez. Standart Streamable HTTP/OAuth istemci akışı
sağlanır; gerçek sunucunun standart dışı gereksinimi varsa ayrı adaptör olarak ele alınır.
Fusion dışındaki web sağlayıcılarının sayfa yapısı veya hizmet kotası bu çalışmada
değiştirilemez.
