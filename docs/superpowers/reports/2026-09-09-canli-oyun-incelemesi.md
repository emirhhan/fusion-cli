# Gerçek oyun görevi üzerinden Fusion incelemesi — devam ediyor

Başlangıç: `ae824c7`. Bu kayıt bir başarı veya yayın raporu değildir. Kullanıcının
ilk oyun isteğini Fusion'ın kendisi yerine getirmeden görev tamamlanmış sayılmaz.
Oyun dosyalarını incelemeyi yapan agent elle üretmiyor.

## Görülen mimari ve gerçek kullanım farkı

- `learning_steps` / `memory`: canlı koşularda altı ders geri çağrıldı. Hafıza var
  ve bağlı; yeni bir hafıza modülü eklemek ilk sorunu çözmeyecek.
- `plan_runner`: checkpoint, bağımlılık kanıtı, bounded recovery, yeniden planlama
  ve final kontrol zaten var. Araç sözleşmeleri ile plan evresi uyuşmadığında bu
  katmanlar modelin önünde engel oluyor.
- `providers.factory`: strict seçim fallback'i kapatıyor. Gerçek çağrı modelini
  olaydan, web model kademesini `served_by` alanından izlemek gerekiyor.
- `prompt_opt.optimizer`: varyant üret/değerlendir/yayınla protokolleri bulunan
  offline altyapı var. Okunan üretim akışında bunun otomatik bir öğrenme döngüsüne
  bağlandığı görülmedi; varlığı online fine-tuning kanıtı değil.
- `domains`: Godot gate komutları keşif katmanında kullanılıyor. Alanın kabul
  kriterlerini planlayıcıya taşıyan `acceptance_criteria` için üretim çağrısı yok.
- `verify_plan_acceptance`: dosya/komut/çapraz sahne kontrolleri var. Davranış
  doğrulanmadığında uyarı üretiyor; bunlar oynanış ve görsel kalite kanıtı değil.

## Canlı olarak doğrulanan sorunlar

1. Masaüstünde strict `gemini_web/main/auto` seçili oyun isteği ilk model çağrısından
   önce native-tools/long-running gereksinimiyle reddediliyor. Uzun görevi yürüten
   orkestratör ile model taşıma yeteneği birbirine karışmış.
2. Bu ön kontrol exception olarak kaçınca ilerleme kartı çalışıyor kalıyor.
3. Gemini'nin Fusion'a ait `main` Chrome profilinde oturum açık değil. Görünür
   sayfada “Oturum aç” ve “Flash-Lite” var; eski auth kontrolü yalnız giriş formunu
   aradığı için anonim modele istek gönderiyor. Kullanıcıdan açılan pencerede
   kendi hesabına giriş yapması istendi; hesap bilgileri okunmadı.
4. İlk CLI koşusunda discovery adımı `index.html` / `game.js` yazdı; model asıl
   isteği keşif sırasında assetsiz web oyununa dönüştürdü. Bu adım gerçekten
   salt-okunur değilmiş. Koşu durduruldu; teslim kabul edilmedi.
5. İkinci Gemini koşusu plan alanları çeliştiği için düştü. Plan onarımının yeni
   model turuna ilk şemayı göndermediği görüldü.
6. `allowed_tools=set()` plan üretiminde araçları kapatmak için kullanılıyor,
   ancak yönetim araçları yine ekleniyordu.
7. NVIDIA Nemotron karşılaştırması Godot proje dosyasını oluşturdu. Asset adımında
   Kenney sayfasını okudu, sonra indirme URL'sini tekrar tekrar tahmin ederek
   404 aldı. `web_fetch` gerçek bağlantıları metne çevirirken siliyor; ikili dosya
   indirmek için de yerleşik araç bulunmuyor.

## Uygulanan ve doğrulaması devam eden değişiklikler

- Gereksinim çıkarımı araç desteğini ve gerçek görsel eklerini koruyor; “oyun yap”
  ifadesinden native araç çağrısı zorunluluğu çıkarmıyor.
- Yalnız ilk model seçiminin ConfigError'ı başarısız AgentOutcome'a çevriliyor;
  ekleri taşıyan geçmiş ve normal TurnOutcome/TurnFinished akışı korunuyor.
- Discovery evresi salt-okunur araç kapsamı uyguluyor; plan istemi bunu açıklıyor.
- Boş araç kümesi gerçekten boş; biçim onarımı şemayı ve kullanıcı kısıtlarını
  yeniden gönderiyor.
- Gemini'nin görünür giriş düğmeleri auth sinyali sayılıyor; sıradan sayfa içi
  “Sign in” metni tek başına auth hatası sayılmıyor.
- `download_file` gerçek ikili dosyayı boyut sınırı, hedef/ağ kontrolü, SHA-256 ve
  geri alma kaydıyla indiriyor. Mevcut dosyanın üzerine yazmıyor.
- Sayfa okuyucu indirme bağlantılarını son yönlendirme URL'sine göre koruyor.

## Bitmeden yapılacak işler

- İndirme aracının kod incelemesi ve geniş regresyon doğrulaması.
- NVIDIA çalışmasında gerçek assetlerin indirilmesi, lisans kaydı ve Godot'a
  bağlanması; çıkan her yeni engelin kanıtla teşhisi.
- Kullanıcı girişi tamamlanınca Gemini hesabıyla aynı gerçek görev.
- Oynanış, hikaye/ara sahneler, UI ve asset kullanımının uygulamayı açarak kontrolü;
  eksikleri Fusion'a geri vererek düzeltme.
- Güncel masaüstü paketinin hazırlanması ve aynı davranışların kullanıcı arayüzünde
  doğrulanması. Henüz yeni sürüm kurulmadı ve oyun başarı iddiası yapılmadı.

## Ek canlı bulgu ve doğrulama

`run-06-nvidia` gerçek `download_file` çağrısıyla Kenney platformer ZIP'ini indirdi.
Ancak kalan paketler için arama döngüsüne girdi; adım tamamlanmadığı için rollback
indirilen dosyayı geri aldı. Bu, teslim edilmiş asset veya çalışan oyun sayılmaz.
İlk başarılı mutasyondan sonra keşif uyarısının kalıcı kapandığı bulundu. Sayaç
artık son turdaki mutasyonu karşılaştırıyor; toplam iki uyarı sınırı korunuyor.
Not, indirme görevini kod yazmaya çevirmek yerine gözlenen URL'yi kullanmayı
anlatıyor. İlk yazma ardından dört okuma regresyonu önce başarısız, düzeltmeden
sonra başarılı oldu. Agent/hafıza-hatırlatma testleri ve bağımsız kod incelemesi geçti.

İlk düzeltme grubu `393aad3` commitinde. Tam Python test koşusu, Ruff ve 311 kaynak
dosyalık mypy kontrolü geçti; ardından eklenen değişiklikler ayrıca odaklı sınandı.
Yeni model çağrılarının kalan kalıcı recovery bütçesiyle tekrar başlaması ve tek
adımın dört bağımsız paketi zorunlu tutması hâlâ canlı görevde engel oluşturuyor.
Gemini kullanıcı oturumu ve gerçek oynanabilir teslim henüz doğrulanmadı.

`run-07-nvidia` dokuz adımlı Godot planında `tool.expected` alanını JSON nesnesi
olarak verdi. İki model çağrısı da sırf bu temsil farkından reddedildi. Ayrıştırıcı
artık yalnız TOOL kontrollerindeki nesneyi kayıpsız JSON metnine normalleştiriyor;
diğer kontrol türlerinin şema kısıtları değişmiyor. Gerçek iki başarısız plan yeni
ayrıştırıcıyla geçti. Python literal içindeki küme gibi JSON dışı değerler normal
PlanParseError onarım yolunda tutuluyor. Bu düzeltilmiş akış `run-08-nvidia` ile
aynı özgün istem üzerinden yeniden sınanıyor.

## Dış model için araştırma ile mevcut kodun eşleşmesi

- [ACE](https://arxiv.org/abs/2510.04618) ağırlık değiştirmeden bağlamı geliştirir.
  Fusion'ın mevcut hafızası buna uygun bir başlangıç; başarısız görevi başarılı
  ders olarak kaydetmek doğru değildir.
- [GEPA](https://arxiv.org/abs/2507.19457) gerçek çalışma izleriyle prompt adaylarını
  üretip ölçer. Fusion'ın kökteki `prompt_opt/optimizer.py` modülü benzer bir
  offline seçim arayüzü sunuyor; canlı öğrenme entegrasyonu ayrıca gerekir.
- [Anthropic uygulaması](https://www.anthropic.com/engineering/harness-design-long-running-apps)
  uygulanabilir parçalara bölme, bağımsız ürün değerlendirmesi ve gerçek uygulama
  kullanımıyla iyileştirme gösteriyor. Bu sonuçlar herhangi bir modelin her işte
  Astra ile eşit olduğunun kanıtı değildir. Fusion için ölçü, orijinal kullanıcı
  isteğinin çalışan ürüne dönüşmesi olmalı.

## Gemini auth kapısının gerçek sayfayla tamamlanması

İlk selector düzeltmesi canlı testte yetersiz kaldı: Gemini anonim composer'da
`button:text-is` eşleşmiyordu; görünür simge düğmesinin adı `aria-label` içindeydi.
Ayrıca hazır yanıt yolu, yalnız yanıt beklerken yapılan auth kontrolünü atlıyordu.
Türkçe/İngilizce tam aria-label seçicileri ve `_send_turn` içinde editöre yazmadan
önce güçlü auth kontrolü eklendi. Önceki gerçek probe anonim Flash-Lite ile
başarı dönerken, son probe 3.4 saniyede authentication hatası + failed TurnOutcome
+ TurnFinished üretti. Kullanıcı istemi artık anonim editöre yazılmadan engellenir.
60 web oturumu/tarayıcı/hatırlatma testi ve bağımsız kod incelemesi geçti.

Son geniş pytest koşusu 3448 başarılı, 4 atlanan, 1 eski metin beklentisi hatası
verdi. Test, literal edit_file kelimesi yerine gerçek config.json değişikliğini
kontrol edecek şekilde düzeltildi; 15 senaryo testi yeniden geçirdi. Bu test
commit'i 599f70f, paketlenen fa18faa uygulama kaynaklarını değiştirmiyordu.

## Run09–11: plan kapsamı ve ortam kanıtı

Discovery+command çelişkisi artık yürütme öncesinde mevcut sınırlı onarım yoluna
gider; keşif araç izinleri genişletilmez. Run09 bu engeli geçip doğru macOS Godot
adresini buldu; fakat kurulu Godot'u kullanmak yerine yeniden indirmeye çalışırken
durdu. Ortam bağlamı artık gerçek cwd/OS/mimari ve PATH üzerinde bulunan araçları
taşır; sürüm doğrulanmış gibi gösterilmez.

Devam mesajının asıl görevi değiştirdiği ve yeniden planlamanın bağımsız bekleyen
teslimatları silebildiği de düzeltildi. Checkpoint ana görevi ile yeni yönlendirme
birlikte aktarılır; onarım mevcut planın tamamını görür ve etkilenmeyen adımlar
korunur. Bağımlı dalın anlamsal kapsamı hâlâ ürün değerlendirmesi gerektirir.

Canlı NVIDIA kataloğunda 80 model görüldü; Nemotron Ultra ayrı geçici yapılandırmada
denendi. Kullanıcının model tercihi değiştirilmedi. Run10, içerik beklemeyen
kontrollerde expected:{} üretti. Yalnız command/file_exists/reproduction için bu
boş değer boş metne normalleştirilir; dolu nesneler ve file_contains gevşetilmez.
Gerçek son plan artık 10 adımla ayrıştırılır. Run11 yeni kodla canlı denemedir.

Kullanıcı giriş Chrome'unda no-sandbox uyarısı bildirdi. Playwright bağlamına
chromium_sandbox=True eklendi. Ayrı boş profille canlı Chrome denemesinde
--no-sandbox bulunmadığı doğrulandı. Bu, Google hesabına girişin başarı kanıtı
değildir. Kullanıcıya normal Chrome ile Fusion'ın izole profilinde giriş yolu da
açıldı; kişisel Chrome profili okunmadı veya taşınmadı.

Kullanıcı normal Chrome girişini tamamladı. İlk CLI kontrolü auth hatası verdi;
aynı profilin doğrudan kontrolü oturum açık gösterdi. İkinci gerçek CLI çağrısı
OTURUM_HAZIR yanıtıyla 23.8 saniyede tamamlandı. İlk geçici hatanın nedeni henüz
kanıtlanmadı. macOS giriş akışı artık normal Chrome'u otomasyon bayrağı olmadan
açar; UI Chrome'dan tamamen çıkılmasını ister, açık profile URL devri de profil
sahibinin kapanmasını bekler. Kişisel profil kullanılmaz.

Run11, keşif komutunu TOOL/run_shell diye yeniden yazarak ilk ön kontrolü geçti.
Ön kontrol artık keşif için gerçek izin kümesini kullanır ve bu eşdeğer çelişkiyi
de yakalar. Run12, giriş yapılmış Gemini ile özgün oyun isteğini yürütüyor.

Yeni düzeltmeler için hedefli testler ve bağımsız kod incelemesi geçti. Geniş pytest
koşusu exit 0 ile tamamlandı; koşu başladıktan sonra eklenen native login ve son
keşif kontrolü değişiklikleri ayrıca hedefli testlerle doğrulandı.
Henüz oynanabilir oyun teslim edilmedi; bu belge veya
başarılı altyapı testleri oyun görevinin tamamlandığı anlamına gelmez.

## Run12–14: teslim kanıtı ve devam tuzağı

Run12 yalnız küçük Godot iskeleti ve ASSETS.json üretti. Bildirilen görseller
diskte yoktu; sahne yalnız HUD içeriyordu. Godot açılışında ana sahnenin harf
büyüklüğü uyuşmazlığı ve eksik icon.svg görüldü. Bu sonuç reddedildi.
OTURUM_HAZIR yanıtı da tek başına hesap girişini kanıtlamadı: sonraki model
menüsünde giriş istemi ve Flash-Lite görüldü. Önceki oturum açık yorumu bu
bulguyla geri çekildi. Normal Chrome ile otomasyonun anahtar deposu ayarları
eşleştirildi; kullanıcıdan yeniden giriş isteniyor, doğrulama henüz tamamlanmadı.

Asset envanteri kontrolü artık manifestin varlığıyla yetinmiyor: gerçek, boş
olmayan, proje kökü içindeki dosyaları ve lisans/kaynak kayıtlarını doğruluyor.
Manifestin kendisini veya lisans belgesini asset olarak saymıyor. Son kalite
incelemesi tamamlanma kaydından önce çalışıyor; başarısız düzeltme geri alınıyor,
kalite bulgusu ve harcanan bütçe checkpoint'te korunuyor. Devam komutu eksik
kalite düzeltmesini atlayamıyor.

Run13 eksik assetleri bu kontrolle reddetti. Run14 ayrı geçici DeepSeek
yapılandırmasıyla gerçek indirme bağlantıları buldu, ancak kurtarma adımı
OBSERVE_FIRST nedeniyle yalnız okuma araçlarıyla çalıştı. Tekrar devam etmek
aynı gözlem moduna dönüyordu; bu yürütme engelinin düzeltmesi sürüyor.
Kullanıcının kalıcı model seçimi değiştirilmedi.

## Sohbet ve proje arayüzü

Proje başlıkları altında son beş sohbet, daha fazla göster, sabitleme, doğrudan
silme, Desktop başlangıcı ve composer proje seçicisi eklendi. Görsel/video
girişleri şimdilik “Daha sonra” gösteriyor. Silinen sohbetler için kalıcı silme
kaydı geç gelen yazmaların sohbeti geri getirmesini önlüyor; disk silme hatası
UI'da başarı olarak gösterilmiyor. Son sohbetin silinmesi ve yeniden açılış
tarih sıralaması ayrıca sınanıyor.

Son tam arayüz koşusunda 72 test dosyasında 505 test ve üretim derlemesi geçti.
Python geniş koşusu, Ruff ve mypy geçti; sonraki küçük düzeltmeler için hedefli
doğrulama ve son inceleme sürüyor. Bu değişiklikler henüz kurulu fa18faa
uygulamasında bulunmuyor; son paket, kaynak doğrulaması ve kurulum bekliyor.
