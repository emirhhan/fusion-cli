# Değişiklik günlüğü

Biçim [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) esaslıdır.
Sürümleme [SemVer](https://semver.org/lang/tr/) uyarınca yapılır.

## Yayımlanmamış

- "web push bildirimi", "pushState" gibi isim olarak geçen push artık modeli atlayan git push akışını başlatmaz.
- Gateway bu bilgisayar dışından gelen isteği yalnız belirteçle kabul eder; belirteçsiz ağ bind'i başlamaz (`fusion serve --token`).
- Güvenilmeyen projenin `config.yaml` ve `.fusion/tools` dosyaları MCP süreci, doğrulama komutu veya araç çalıştıramaz; yeni komut `fusion trust`.
- Geri alma kullanıcının commit'lenmemiş işini silmez: yalnız Fusion'ın değişikliği geri alınır, sonradan değişen dosyada çatışma bildirilir.
- Kesilmiş önizleme tam dosya olarak kaydedilemez.
- Kod çalıştıran awk, dosya yazan sed ve dal silen git komutları salt-okur sayılmaz; `git stash drop`, `npm run deploy` ve `curl --json` sorulur.
- Sohbetteki uzak görseller kullanıcı yükleyince istenir; güvensiz bağlantı şemaları çizilmez.
- Telefondan hesapla giriş yapan cihaz o hesaba bağlanır; başka hesabın telefonu masaüstündeki görevleri göremez, iptal edemez, onaylarını cevaplayamaz ve görev başlatamaz.
- Telefon görevleri kalıcıdır: bilgisayar yeniden başlayınca yarım iş "Sonuç belirsiz" görünür ve kendiliğinden tekrar çalıştırılmaz; aynı istek anahtarı farklı içerikle reddedilir; iptal "Durduruluyor" ile başlar, tur gerçekten bitince "İptal" olur.
- `FUSION_WORKSPACE_ISOLATION=1` ile bellek, sır deposu ve tarayıcı oturumları hesaba göre ayrılır; eski ortak veri `fusion adopt-data <hesap>` ile tek bir hesaba kopyalanır.
- Arayüz istekleri son süre ve iptal alabilir; çalışma alanı okumaları 30 sn'de zaman aşımına uğrar.
- Test geçtikten sonra kabukla yapılan dosya değişikliği (`sed -i`, `> dosya`, `cp`) eski başarıyı geçersiz kılar; görev yeniden doğrulama bekler.
- Uzun oturumda bağlam özetlenirken kullanıcının koyduğu kurallar ("asla main'e push etme") özete birebir taşınır.
- Ajanın dosya düzenlemesi CRLF satır sonlarını korur.
- Telefondan ekran izleme masaüstü onayıyla açılır; "hatırla" 7 günlük güven verir. Telefon, işlemin gerektirdiği yetki (ör. `project.write`) olmadan yazma/komut onayı veremez, yalnız reddedebilir.
- Önizleme sunucusu, başka bir sürecin tuttuğu portu boş sanıp açılamamazlık etmez.
- Telefon eşleştirmesinde yanıt ağda kaybolursa telefon aynı cihazı yeniden alır; sırrı hiçbir telefona ulaşmamış "hayalet" cihaz kendiliğinden iptal edilir.
- Chrome yerel bağlantısı yalnız gerçek Fusion Browser eklentisine açılır; aynı adı taşıyan başka bir eklenti kabul edilmez.
- Tarayıcıda tıklama/yazma sonucu gelmezse ajan "sonuç bilinmiyor" görür ve işlemi körlemesine tekrarlamaz; alana yazılan anahtar/belirteç adım günlüğünde gizlenir.
- Tarayıcıda sayfa değiştikten sonra eski öğe referansı yeni sayfada başka bir öğeye tıklamaz; ajan sayfayı yeniden okumaya yönlendirilir (Fusion Browser 0.3.12).
- Web modelinin düzgün kapattığı araç çağrısı bloğu "kapanmamış" sayılıp yeniden istenmez.
- Masaüstü sürümü lint/tip/test kapısı geçmeden yayımlanmaz.
- Masaüstü uygulaması sıkı içerik güvenlik politikasıyla çalışır; arayüz dosya içeriğini ağ isteğiyle okuyamaz, `.ssh`, `.aws`, tarayıcı profilleri ve `.env` gibi hassas dosyalar uygulama içi görüntülemeye kapalıdır.
- Uzak MCP sunucusu giriş ayarlarıyla Fusion'ı iç ağdaki adreslere (bulut metadata, yerel cihazlar) istek atmaya yönlendiremez; eklenen sunucunun kendi adresi dışındaki her hedef genel bir HTTPS adresi olmalıdır.
- Finder'dan açılan uygulamada Homebrew'la kurulu `npx`/`uvx` MCP sunucuları bulunur; "kurulu değil" hatası verilmez.
- MCP sunucusunun "çok fazla istek" (429) ve "zaman aşımı" (408) yanıtları geçici sayılır; bağlantı oturum boyunca kapatılmaz.
- Web sayfası okuma, site tarama ve dosya indirme denetlenen adrese bağlanır: alan adı denetimden sonra iç ağa çözülse de (DNS rebinding) istek gitmez; Tailscale/CGNAT (`100.64.0.0/10`) ve IPv6'ya gömülü iç adresler de engellenir.
- Model kimliksiz ya da aynı kimlikli birden çok araç çağrısı gönderdiğinde her çağrı çakışmayan bir kimlik alır; sonraki tur sağlayıcı tarafından reddedilmez.
- NIM gömme modeli değiştirilince vektörler eski modelin koleksiyonuna eklenmez; her model kendi koleksiyonunu kullanır, varsayılan modelin mevcut dersleri ve kod indeksi korunur.
- Kod indeksi parça sınırına takılınca "İndeks kısmi" uyarısı verir; dışarıda kalan dosyalar sessizce kaybolmaz.
- Kitaplıkta yüklenemeyen dosyanın hatası, ardından gelen liste yenilemesiyle silinmez.
- Telefonun ekran izleme ekranındaki eski "bu telefonda onay ver" metni düzeltildi; izin masaüstünden istenir.
- Günlük ve haftalık zamanlanmış görevler yaz saati geçişinde yerel saatinde kalır (önceden geçişten sonraki gün bir saat kayıyordu).
- Görsel işlerinin yerel kaydında tek bir bozuk kayıt artık sohbetteki bütün bekleyen işleri ve yeni üretimi kilitlemez; bozuk kayıt karantinaya alınır.
- Komut iptali, kendini ayrı oturuma alan (`setsid`) ve çıktıyı açık tutan torun süreçleri de kapatır; geride çalışan süreç kalmaz.
- Güvenlik: `rm --recursive --force`, `sh -c 'git push'`, `eval`, `curl | zsh`, `git restore .`, `git checkout .` ve uzaktan `npx`/`pnpm dlx` paketleri artık onaysız çalışmaz; agent'ın yazdığı betik riskli içerik taşıyorsa çalıştırılmadan önce sorulur.
- Güvenlik: tarayıcı araçları yönlendirme ve alt kaynak isteklerinde de iç ağ adreslerini engeller; dosya yazan araçlar alt ajan yazma alanını aşamaz; önizleme sunucusu gizli dosyaları ve yabancı Host'u reddeder.
- Güvenlik: tehlikeli işlemlerde boş Enter onaylamaz; güvenilmeyen projenin `.claude/settings.local.json` izinleri `fusion trust` olmadan uygulanmaz (eski güven kayıtları için yeniden `fusion trust` gerekir).
- Güvenlik: git push sırlı origin adreslerini ve anahtar dosyalarını kayda/commit'e almaz; dış bellek dosyaları maskelenir; sır deposu atomik yazılır.
- Güvenlik: web öğretmenine sır dosyaları ve proje dışı dosyalar gönderilmez, gönderilenler gösterilir; proje dışına dosya yazma otomatik kipte sorulur.
- Güvenlik: MCP sırları terminal ve `run_shell` çocuklarına geçmez; hata raporu ve denetim günlüğü GitHub belirteçlerini, Basic kimliği ve adreslerdeki parolaları da gizler.
- Onay kartı yazarken beliriyorsa ilk 600 ms'deki rakam/Enter karar vermez; Escape yalnız en üst pencereyi kapatır; seçeneksiz onay kartı kilitli kalmaz.
- İzin modu sohbet başına tutulur; çekirdek reddederse eski mod ve hata görünür. Zaman aşımı, iptal ve bilinmeyen araç sonuçları başarılı görünmez.
- Doğrulama kapısı son düzeltmeyi de ölçer; modelin art arda boş yanıtı başarı sayılmaz; paralel araç sonuçları bağlam temizliğinde korunur.
- Doğrulama komutu zaman aşımında, iptalde ve arka plan çocuğu varken takılmaz; torun süreçler de kapatılır. `git add && git commit`, `cd x && git commit` ve `pytest 2>&1` kanıt sayılır.
- Uzak görevler takılı kalmaz: zaman aşımı ve kök/model hatası görevi başarısız yapar; Telegram köprüsü beklenmeyen hatada kopmaz.
- Büyük dosya okuma ve git sorguları arayüzü dondurmaz; proje kökü doğrulanır, kök değişince ek klasör izinleri sıfırlanır.
- Esc ile kesilen turun geçmişi ve `/undo` kaydı korunur; borulu kullanımda TUI açılmaz.
- Talk: kesilen konuşmanın eski sesi yeni konuşmayı ezmez; sesli onay Fusion'ın kendi sesinden gelen yankıya, kimliksiz ve 2 dakikadan eski sorulara karşı korunur.
- Görsel üretimi sürerken yazılan yeni istem silinmez; akışta dosyası silinmiş üst düğüm yeniden üretilir, eksik referans arayüzü kilitlemez.
- Geçerli Godot 4 `project.godot` (config_version, uid ana sahne) reddedilmez; bozuk Remotion kiti kabuğu kilitlemez; favicon 404'ü ve WebGL canvas yanlış hata üretmez; Remotion videosu gerçek dosya, süre ve çözünürlük kanıtıyla doğrulanır, videoya sabit "Fusion" adı eklenmez.
- Zamanlanmış görevde tek teslim hatası sıradakileri durdurmaz; etkin sohbet kapansa da açık başka oturum üzerinden alınır.
- Zaman aşımıyla iptal edilen model çağrıları maliyet özetinde "en az" diye işaretlenir, sıfır sayılmaz.
- Masaüstü kabuğu: bozuk `active-runtime.json` açılışı ve "Onar"ı engellemez (`.corrupt` olarak yedeklenir); çekirdek ya da ses çıktısındaki geçersiz bayt sonraki satırları susturmaz; takılan terminali kapatmak ve yoğun yazım uygulamayı dondurmaz; çekirdek durdurulurken alt süreçleri de sonlanır (macOS/Linux).
- Çekirdek makbuzu gelmese ya da reddedilse de tur çıktısı görünür; açılışta bağlanamayan kayıtlı sekmeler silinmez, uyarıyla gösterilir; dosya okuma hatası dosya ağacını gizlemez; artık cevap beklemeyen soru kartı kapanır.
- Sesli konuşmada araya girildikten sonra mikrofon sağır kalmaz; Esc menüyü kapatırken ya da turu durdururken sağ paneli kapatmaz; talimat kaydı hataları görünür, okunamayan talimatın üzerine yazılamaz.
- Hesap kurtarma kodu her koşulda gösterilir, pano çalışmasa da devam edilebilir; bağlantı araması GitHub, Notion ve Shopify'ı bulur; beceri listesi tek bozuk öğede boşalmaz; sunucuda kaybolan görsel işi panelden unutulabilir.
- Bellek bir koleksiyon takılınca tamamen kapanmaz, yazılamayan kayıt "eklendi" denmez; akışlı gateway yanıtlarında ve uzak olaylarda sırlar maskelenir; MCP araç hata mesajları modele iletilir; Gemini tarayıcı oturumunda görseller eklenir.
- Sistem istemlerindeki dil ve ilerleme anlatımı çelişkileri giderildi; plan şeması tek geçerli örnek ve `c1`/`c2` kimlikleriyle zayıf modellerde daha az reddedilir; Remotion kart başlıkları uzun Türkçe sözcüklerde bölünmez.
- Sürüm Release'i yüklenen bütün dosyalar için SHA256SUMS, SBOM ve manifest içerir; terminal (PTY) testleri CI'da ayrı işte koşar.
- Görev kutusu: sohbet kipinde Shift+Tab izin modunu değiştirmez; gönderim sırasında yazılan metin korunur, reddedilen gönderim hata gösterir; panodan görsel ek olarak eklenir; açık `@` listesi Esc ile önce kendini kapatır; "/Users/x/main.py incele" gibi yolla başlayan mesaj komut sayılmaz.
- Sohbet arayüzü: sabit sohbetler proje taşınınca kaybolmaz; bozuk proje tercihi ya da tema okuma hatası boş pencere bırakmaz ("yeniden yükle" ekranı); araç/kaynak/önizleme adresleri yalnız http(s) açılır; kritik bağlam doluluğu ayrı renkte; iş sürerken bağlam kartından `/compact` gönderilmez.
- Terminal sekmeleri başka sekmeye geçince kapanmaz; kabuk ve araç çıktısındaki API anahtarı/Authorization değerleri maskelenir; kayıtlı API anahtarı yalnız göz düğmesiyle görünür.
- Sohbet açılırken geç gelen geçmiş ve iptal edilen turun yarım yanıtı kaybolmaz; saklı sohbetler tüm açık projelerden listelenir; 200'den fazla dosyalı klasörler tam listelenir.
- Zamanlama: günsüz haftalık, geçmiş tarihli ve çok kısa aralıklı görevler reddedilir; silme onay ister.
- Talk: tek komut modunda düşünme ipucu çalar, yanıt gelmezse 90 sn sonra hata gösterir, kalıcı tanıma hatasında mikrofon döngüye girmez; sesli "evet" onay kartındaki "İzin ver"i onaylar; eski macOS WebView'lerinde modül kırılmaz.
- Ayarlar: Esc kaydedilmemiş talimatı silmez, arama Ses/İzin/Model bölümlerini bulur, port 1-65535 doğrulanır, "İzinleri atla" onay ister, Chrome eşleştirme anahtarı varsayılan gizli; çalışan görev varken uygulama güncellemesi kurulamaz.
- Görsel oluştur: sayfa değişince istem korunur, üretimde Durdur düğmesi var, bozuk kayıtlı akış arayüzü çökertmez; Bağlantılar'da "Yeniden dene", hata nedeni ve "Vazgeç" var.
- Onay kartı `multi_edit` ve silme düzenlemelerinde de fark gösterir; uzun/sırlı argümanlar kısaltılıp maskelenir; ayar kaydı diske yazılamazsa uyarı döner.
- Chrome eklentisi: kapalı eklenti "yüklendi" sayılmaz, kesilen kopyalama mevcut eklentiyi bozmaz, tuş vuruşları yalnız Chrome öndeyken gönderilir; kod kipindeki panel görevi kod araması yapabilir.
- Uzun boşluksuz metinde sır maskeleme artık dakikalarca sürmez; hata raporu Stripe, Groq, Hugging Face, Google OAuth ve JWT anahtarlarını da gizler; Langfuse'e giden veriler sırlardan arındırılır.
- Ajan: büyük harfli Türkçe istekler ("İNCELE", "SİL") doğru tanınır; zayıf modellerin tip kaymaları (`"true"`, `"1920"`, boş/çitli JSON argüman) ve Claude/Cursor/Windsurf araç adları araçları düşürmez; `council` tur başına 3 çağrıyla sınırlı.
- Öğretmen ulaşılamayınca "Öğretmen devre dışı" bildirimi gelir; öğretmene kimlik dosyalarının (`.env.local`, `id_rsa`, `*.pem`) adı ve farkı gitmez; depo talimatı etiketi kapatılıp sahte talimat eklenemez.
- Doğrulama: çöken tek kapı tüm doğrulamayı düşürmez, atlanan tarayıcı/PHP/görsel denetimi uyarıda görünür; Playwright yoksa "ölçülemedi" denir; keşif `.venv` araçlarını, `cargo check`/`go vet`'i ve uv/poetry/tox/npm `test:*` koşucularını kullanır; zaman aşımına uğrayan komut başarı iddiasını engeller.
- Plan ayrıştırıcı "bağımlılık yok" için `""`/`null`/`"yok"` yazan planı düşürmez; plan modunda ödeme ve silme adımları onaysız planlanamaz.
- Dosya araçları FIFO/aygıtta kilitlenmez; `list_dir` kırpmayı bildirir; görsel dönüşümü saydamlığı korur; arşiv açma şifreli/kesik arşivde çökmez; `tsconfig.json`, yorumlu JSON ve çok belgeli YAML yazımı reddedilmez; büyük dosyada fark özeti verilir.
- Komut politikası: `grep -r x .*`, `tail -f`, `top`, `git rebase`, `DROP TABLE` ve `osascript` tuş otomasyonu sorulur; `npm --version` ve `git commit -m "fix reboot"` sorulmaz.
- `web_fetch` ikili içeriği metne çevirmez, `web_search` boş sonucu hata sayar; önizleme sunucusu çökünce 45 sn beklemez, hata çıktısını gösterir; site kopyalamada "199,90 TL" fiyatları ve Türkçe kategori adresleri desteklenir.
- MCP: uzak araç adları sağlayıcı kuralına uydurulur; giriş akışı yabancı istekte düşmez, tarayıcı açılamazsa adres gösterilir; takılı oturum 3 zaman aşımından sonra yeniden bağlanır; listedeki gömülü anahtarlar maskelenir.
- Sağlayıcılar: kesik araç argümanı ve çöken akış sessizce kaybolmaz; anahtarsız sağlayıcı ve girişsiz Codex yedek zincirinden ayıklanır, Codex iptalde süreci öldürür; web sağlayıcıda iptal sonrası mesaj iki kez yazılmaz; Ollama adresi `OLLAMA_HOST`'tan okunur.
- Bellek: kod indeksi sırları maskeler ve `build/` adlı üst klasörde boş kalmaz; Türkçe İ/I aramada eşleşir; ders metni istem bloğunu bozamaz; tur günlüğü argümanları geçerli JSON bırakarak maskeler.
- Uzak erişim: Tailscale adresine doğrudan bağlanılabilir; cevaplanmayan onay 30 dakika sonra reddedilir; yüksek yetkili kapsamla eşleştirme her zaman masaüstü onayı ister; telefonda gönderim hatasında metin kaybolmaz.
- Masaüstü kabuğu: gömülü terminal giriş kabuğu olarak açılır (Homebrew/nvm araçları görünür); Kits kapanışta donmaz, gizliyken yoklama yapmaz; Windows çalışma zamanı `%LOCALAPPDATA%`'ya uyar; çalışma zamanı kurulumu zaman aşımlı.
- CLI: uzun yol ve komutlar araç kartında ortadan kısaltılır; `fusion uninstall --purge` onay ister (`--yes`); `--quiet` önemli uyarıları yutmaz; `fusion agent` başarısızlıkta sıfırdan farklı çıkış kodu verir; hata satırları stderr'e yazılır; `/providers add` anahtarı aynı oturumda etkin olur.
- Hesaplar: kurtarma kodu 80 bit oldu (eski kodlar çalışır), giriş ve sıfırlamada hesabın varlığı süre farkından anlaşılmaz; avatar yeniden seçimi mevcut avatarı silmez.
- Gateway paneli iframe'e gömülemez; kaydedilmemiş zincir/hakem değişikliği otomatik yenilemede silinmez; web oturumu kartı model ve sağlayıcı adlarını kaçışlar; "Araç yeteneğini ölç" kota harcadığı için onay ister.
- Kitaplıkta arama gecikmeli ve son istek kazanır; Woo aktarımı kök dışı görseli kopyalamaz, fiyatsız ürünü taslak bırakır; web iskelesi `style.css` ve `script.js` taslaklarını yazar; Claude geçmişi boşluklu/noktalı klasör adlarında da bulunur.

## 0.7.18 — 2026-10-21

- Araç çağırmadan "yapıyorum" diyen model, turu başarısız kapatmadan önce üç kez kademeli ve somut uyarıyla araca yönlendirilir.
- Platformlar arası test ve denetim farkları giderildi.

## 0.7.17 — 2026-10-21

- Codex sohbeti devralınırken oturumun çalıştığı klasörler bulunur, erişime açılır ve proje köküyle uyuşmazlık modele bildirilir.
- Proje kökünde bulunamayan dosya Belgeler, Masaüstü ve İndirilenler'de aranır; çoklu eşleşmede kullanıcıya sorulur.
- Dosya hiçbir yerde yoksa gizli ve bağımlılık klasörlerinde aramadan önce her onay kipinde kullanıcıya sorulur.
- Soru kartı kompakt hale getirildi.
- Windows'ta bellek deposu kilidi ve çok platformlu tip denetimi düzeltildi.

## 0.7.16 — 2026-10-20

- Devralınan sohbetlerde devam isteği asıl görevin araç kanıtıyla değerlendirilir.
- Araç kullanmadan iş yapıldığını söyleyen yanıtlar doğrulanır; kanıtsız başarı kaydedilmez.
- Aynı başarısız araç çağrısının sınırsız tekrarı durdurulur; düzeltilen önkoşullar yeniden denemeye izin verir.
- Boşluk içeren proje dizinlerindeki kabuk hataları, doğru tırnaklı yolu ve göreli yol kullanımını gösterir.
- Sohbet geçmişi, çalışma adımları, pencere kontrolleri ve panel düzeni güncellendi.
- Kaynak dağıtımı, kurulum belgeleri ve geliştirme ortamı temizlendi.

## Yayımlanmamış — Chrome eklentisi kurulumu ve paneli

- Ayarlar → Tarayıcı'ya **Eklentiyi kur** eklendi (`fusion chrome-kur`): eklentiyi kalıcı klasöre
  kopyalar, yerel mesajlaşmayı kaydeder (macOS ve Windows), Chrome'u açar; yüklü/eşleşti
  durumunu doğrular. Eklenti kimliği `manifest.json` anahtarıyla yoldan bağımsız sabitlendi.
- Yan panel Kits dilinde yenilendi (sistem yazı tipi, nötr vurgu, açık/koyu tema); ekran, fare ve
  klavye adımları için denetim şeridi ve izin kipi özeti eklendi.

## Yayımlanmamış — ses motoru: EMA Lightning

- Sesli yanıt motoru Piper yerine EMA Lightning (Türkçe, Apache-2.0, ~34 MB) oldu.
  Model ONNX'e çevrilip uygulamaya gömüldü: PyTorch ve ilk kullanımda indirme gerekmez,
  çevrimdışı çalışır. Resmî PyTorch motoruyla çıktı örnek örnek eşleşir (en büyük fark 9e-5).
- EMA tek sesli ve tek parametrelidir: "Robotik" sürgüsü ve "Piper ses modeli seç" düğmesi
  kaldırıldı; eski ayar dosyasındaki `robotik` ve `model` alanları yok sayılır.
- Model dosyaları eksikse macOS sistem sesine düşülür ve sebebi söylenir.
- Yeni bağımlılık: `normalizer-tr==0.8.0` (sayı/tarih okuma); `piper-tts` kaldırıldı.

## Yayımlanmamış — onay ve soru güvenilirliği

- MCP araç ipuçları çeliştiğinde Fusion açık `destructiveHint=true` değerini
  `readOnlyHint=true` değerinden önce değerlendirir. Bu, Fusion'ın ihtiyatlı
  ürün politikasıdır; farklı bir öncelik kullanan istemcinin MCP standardını
  ihlal ettiği anlamına gelmez. İpucu yoksa araç uzak yazma olarak değerlendirilir;
  incelenmemiş veya kaynağı değişmiş sunucunun salt okuma iddiası onayı atlayamaz.
- Uzak işlemlerde oturum izni yalnız doğrulanmış sunucu, hesap, eylem ve hedef
  kapsamında saklanır. Masaüstü ve terminal bu kapsamı seçimden önce gösterir;
  kapsam doğrulanamıyorsa yalnız tek işlem için izin istenir.
- Terminal giriş hatası veya Ctrl+C onaya dönüşmez. İsteğe bağlı soru kanalının
  kapanması bağımsız çalışmayı iptal etmez ve kullanıcı cevabı sayılmaz.
- Geç gelen soru cevapları yeniden açılan oturumdaki sorulara uygulanmaz.
  Yakın cevapların aynı makbuzla tekrarı işlemi ikinci kez başlatmaz.
- Büyük dosyalarda `read_file` ilk bayt penceresinin ötesindeki satırlara ulaşır;
  dosyanın tamamını belleğe almaz ve kısmi okuma tam okuma sayılmaz.
- Terminal konuşma günlüğü ve checkpoint aynı sohbet kimliğini kullanır.
  Eski ortak `repl`/`cli` kayıtları korunur; yeni oturumlara otomatik taşınmaz.
  Geçmiş sohbeti içe alma, eski işlem izinlerini veya workflow'u yeniden başlatmaz.

## [Desktop 0.3.0-alpha.11] — 2026-09-10

- Gerçek macOS uygulamasında saptanan panel genişliği düzeltildi; kontrol paneli
  çalışma alanına yayılır ve içerik ortalanır. Güncelleme düğmeleri ortak ölçülere uyar.
- Terminal/çalışma zamanı sürümü 0.3.0a10 olarak korunur; bu yalnız arayüz güncellemesidir.

## [0.3.0a10] — 2026-09-10

- Paketli uygulamada web girişinin Chrome açılmadan kapanmasına neden olan
  hesap parametresi düzeltildi; gerçek CLI ayrıştırıcısıyla regresyon testi eklendi.
- Yeni Fusion tarayıcı profillerinde Chrome ilk kurulum ve varsayılan tarayıcı
  ekranları atlanır; normal Chrome profili kullanılmaz.
- Kontrol paneli kategorilere ayrıldı; sağlayıcı ayrıntılarının yanlışlıkla
  yan yana çizilmesi düzeltildi ve kenar çubuğu daha kompakt hale getirildi.
- MCP ekleme ve yapılandırma formları odak yönetimi ve Escape desteği olan
  ayrı bir bağlantı penceresinde açılır.

## [0.3.0a9] — 2026-09-10

- Masaüstü kontrol paneline imzalı uygulama içi güncelleme eklendi; GitHub
  Releases için macOS güncelleme arşivi ve manifest üretimi sağlandı.
- macOS'ta Fusion API kasası tekrarlayan Keychain izin isteği olmadan açılır.
  Eski kasa korunur; sessiz geçiş mümkün değilse anahtar yeniden girilir.
- Web bağlantısı yalnız doğrulama sonrası bağlı gösterilir. Kapanmış giriş
  süreçlerinin açık sayılması, hata durumunda takılı kalan düğmeler ve Chrome
  süreç temizliği düzeltildi.
- Etkin Chrome profilinin kilidi korunur; yeni görünür giriş eski elle
  aktarılmış çerezlerle ezilmez.
- API kaydı ve doğrulaması ayrıldı; OpenRouter, OpenAI, Anthropic ve Gemini
  için kimlik doğrulamalı anahtar sınaması eklendi.
- Sol alttaki sabit örnek profil kaldırıldı; bağlantı bilgisi gerçek oturumdan okunur.
- Masaüstü ve terminal kurulumları README'de ayrı açıklandı.

## [0.3.0a8] — 2026-08-30

- Windows çalışma zamanı paketi başarıyla üretildikten sonra CP1252 konsoluna
  Türkçe günlük etiketi yazarken yayın işinin çökmesi engellendi.
- Büyük konuşma performans kapısına paylaşımlı Intel CI çalıştırıcısının
  zamanlayıcı yükünü kapsayan, gerileme yakalama özelliğini koruyan pay eklendi.

## [0.3.0a7] — 2026-08-30

- Windows Rust kalite kapısında hedefe göre kullanılmayan test yardımcı
  parametresinin uyarı-as-error üretmesi düzeltildi.

## [0.3.0a6] — 2026-08-30

- Rust çalışma zamanı testleri Windows hedefi, `.exe` giriş noktası ve Windows
  izin modeliyle derlenebilir hâle getirildi.
- POSIX çalıştırma izni ve kabuk protokolü testleri yalnız Unix hedeflerinde
  derlenecek biçimde sınırlandı.

## [0.3.0a5] — 2026-08-30

- Windows paket ayarı normal Cargo kalite kapısından ayrıldı; temiz makinede
  henüz üretilmemiş runtime arşivini araması engellendi.
- macOS paket komutu, ses tanıma yardımcı ikilisini Swift kaynağından kendisi
  derleyecek hâle getirildi.
- Dosya seçildikten hemen sonra Düzenle'ye basıldığında geciken seçme efektinin
  editörü kapatabilmesi düzeltildi.

## [0.3.0a4] — 2026-08-30

- Ses ayarları ilk açıldığında geciken bir eşitlemenin kullanıcının hızlı sürgü
  hareketini eski değerle ezebilmesi düzeltildi.
- Sürgü kaydetme yarışı tekrarlı regresyon koşusuyla doğrulandı.

## [0.3.0a3] — 2026-08-30

- macOS ve Windows masaüstü paketleme ortamlarına Piper ses motoru bağımlılığı
  eklendi; temiz CI makinesinde çalışma zamanı üretimi artık eksik paket bilgisiyle
  durmuyor.
- Ses sürgüsü testi gerçek tarayıcı `input` olayına geçirildi; macOS Intel ve
  Windows ortamlarındaki sahte olay zamanlaması farkı giderildi.
- Masaüstü CI bağımlılık sözleşmesi regresyon testine alındı.

## [0.3.0a2] — 2026-08-30

- Masaüstü Ayarlar ekranına oturumluk token, tahmini maliyet ve ölçülmüş model
  sağlığı özeti eklendi.
- Ses hızı, tını, özel Piper modeli ve çevrimdışı Türkçe model indirme Ayarlar'a
  taşındı.
- Windows WebView'da sürgü bırakılırken eski değerin kaydedilebildiği olay
  sıralaması düzeltildi.
- Ayarlar'ın kaydırma altındaki kullanım ve ses kartları geniş/dar görsel
  regresyon testlerine alındı.

## [0.3.0a1] — 2026-07-26

İlk kamuya açık alfa. Bu sürümün ağırlığı yeni özelliklerde değil, **sessizce
çalışmayan şeylerin bulunmasında**: aşağıdaki hataların çoğu kod "başarılı"
görünürken arka planda hiçbir iş yapmıyordu.

### Eklenenler

- **`/verify`** — projeyi tanıyıp doğrulama planı çıkarır (pytest, ruff, mypy,
  npm/pnpm/yarn scriptleri, cargo, go, make), planı gösterir ve onaylanırsa
  `config.yaml`'a yazar. Otomatik açılmaz: keşif tahmindir, yanlış tahmin kapıyı
  her turda düşürür.
- **`/undo`** — son agent turunun dosya değişikliklerini geri alır. Yalnızca
  agent'ın dokunduğu dosyalar; kullanıcının elle yazdıklarına dokunulmaz.
- **`--add-dir`** — proje kökünün yanında erişime açılacak dizin.
- **`/provider`** — hangi sağlayıcının kullanılacağını seç (`auto` | `nvidia` |
  `openrouter`). Tek sağlayıcıya kilitlenince ötekine hiç istek gitmez: bir
  sağlayıcının tükenmesi ötekini de tüketiyordu.
- **Kurulum sihirbazı anahtar sorar.** OpenRouter zorunlu, NVIDIA NIM opsiyonel.
  83 küratörlü ders otomatik yüklenir: indiren herkes eğitilmiş başlar.
- **Model zincirleri kurulu anahtarlara göre budanır.** İki sağlayıcıdan biri
  yeterlidir; olmayanın modelleri zincirden düşer.
- **Doğrulanmış sentez** (`verified_synthesis`) — hakem önce çalışır, kararı
  senteze taşınır. Paralel kipte sentez kazananı bilmiyordu.
- **Eval: tekrarlı koşu** (`--repeat N`) ve geçme oranı. Kararsız görevler adıyla
  raporlanır.
- **Eval: tur transkripti.** Her koşu `_transkript.jsonl` bırakır (araç çağrıları,
  sonuçları, model hataları). "Agent neden hiçbir şey yapmadı" sorusu artık
  sonradan cevaplanabiliyor.
- **Eval: kota tükenmesi görev başarısızlığından ayrılır.** Sağlayıcı 429 verdiğinde
  koşu durur ve rapor YAZILMAZ; yarım ölçümü geçerli sanmak yanlış sonuçlara yol
  açıyordu.
- **Eval: `setup`** ile göreve başlangıç dosyası verilebilir; bug fix ölçmenin
  ön koşuluydu. On yeni görev — üçü agent’ın YAPMAMASI gerekeni ölçüyor
  (kök dışına yazma, prompt injection, kullanıcı içeriğini silme).
- **Ders belleği projeye kapsanır.** A projesinde öğrenilen B'de hatırlanmaz;
  genel yordamsal dersler her projede kalır. Göç gerekmez.

### Değişenler

- **Kademe merdiveni NVIDIA NIM omurgasına taşındı.** OpenRouter'ın ücretsiz
  kotası günde 50 istek (≈12 fusion turu); NIM'inki çok daha geniş. Modeller
  katalogdan değil **yoklanarak** seçildi — katalogdaki birçok model `NotFound`
  dönüyor ya da zaman aşımına uğruyor.
- **Dosya erişimi varsayılan olarak proje köküyle sınırlı.** Kısıtlama opt-in
  bırakıldığı sürece kimse açmıyordu.
- **Gözetimsiz kabuk çalıştırma kara listeden beyaz listeye geçti.** Tanınmayan
  her komut sorulur. Kara listeye kalıp eklemek bir sonraki kaçış yolunu kapatmaz.
- **Dersler talimat değil ÖNERİ olarak enjekte edilir** ve güvenlik kararlarını,
  kullanıcı talimatını, araç izin akışını geçersiz kılamaz.
- **Kota hatası gerçekten işe yarayan yönlendirme verir.** Eski mesaj "farklı bir
  model dene" diyordu; sınır hesap başına olduğu için bu yanlış tavsiyeydi.

### Düzeltilenler

- **Doğrulama kapısı hiç düzeltme turu açmıyordu.** Komut çıktısı `DEVNULL`'a
  gidiyor, bulgu üretilmiyor, motor da bulgu yoksa döngüyü kırıyordu: `pytest`
  kırmızıyken agent düzeltmeye hiç başlamıyordu.
- **REPL'de doğrulama kapılarının hiçbiri kurulmuyordu.** `tool_context`
  geçirilmediği için web, tarayıcı ve görsel kapılar sessizce kapalıydı.
- **Boş `.env` satırı gerçek anahtarı gölgeliyordu.** Kurulum "tamam" diyor,
  hiçbir model çağrılamıyordu.
- **`/type` agent turunda uygulanmıyordu**; `task_model_map` REPL'de etkisizdi.
- **Seçim ekranı REPL'in event loop'unda çöküyordu.**
- **`defaults.yaml`'da `tiers` iki kez tanımlıydı**; 166 satır ölü koddu ve
  çalışan merdiven bozuktu (`medium` en büyük modeli, `premium` daha küçüğünü
  kullanıyordu).
- **Uzun model listeleri ekranı taşırıyordu** (327 model); artık sayfalanır.
- **Dosya yazımı atomik değildi**; yarıda kesilme çalışan dosyayı bozabiliyordu.
- **Alt-ajan değişiklikleri doğrulama kapısından kaçıyordu.**
- **Hakem ve sentez aday metnini talimat sayabiliyordu** (prompt injection).

### Bilinen sınırlar

- **MCP yok.**
- **`run_shell` kök kısıtlamasına tabi değil.** Onay katmanı savunmadır, kum
  havuzu değil: sınır aşılabilir ama sessizce aşılamaz. Ayrıntı `docs/BACKLOG.md`.
- **Eval seti dar.** 18 görev. Kolay blok tavana vurmuş (12 görev 3/3); ayırt
  etme gücü beş zor görevde. Tek sağlayıcıya kilitlenmiş ölçümde **14/15 ve 13/15**.
- **Gürültü tabanı ~1-2 koşu (15'te), görev bazında ±2.** Aynı yapılandırmanın iki
  koşusu arasındaki fark bu kadar; daha küçük A/B farkları yorumlanamaz.
- **`workflow_mode` ve `playbooks` varsayılan kapalı.** workflow ölçüldü: kaliteyi
  artırmıyor (8/15 → 9/15, gürültü sınırında), model çağrısını yarıya indiriyor
  ama süreyi ikiye katlıyor. `playbooks` hiç ölçülmedi.
