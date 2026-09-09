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
