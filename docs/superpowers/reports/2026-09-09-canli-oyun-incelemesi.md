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
