# Gelecek kontrollü koşuların nihai B briefleri

Bu metinler gelecekteki tek aktarım denemesi için sabitlendi. Geçmiş çıktılara puan/rubrik uygulanmaz. A metinleri kaynak TASK byte'larıdır; değiştirilmedi. Brief hazır olması eş koşullu 12 koşunun hazır olması değildir. Profesyonellik rubriği ayrı kontrollü karşılaştırma sözleşmesindedir. Aşağıdaki işlev kontrol noktaları puan değil, görev tamamlanma kanıtıdır.

## html_oyun B

```text
Yan görünüşlü, üç bölümlü bir platform oyunu üret. Tek klasörde index.html ve yerel CSS/JS/görseller ile hem file:// hem yerel HTTP üzerinden çalışsın. Başla düğmesine gerçek tıklama ilk bölümü başlatsın. Ok tuşları hareket, boşluk zıplama, P duraklatma/devam ve R yeniden başlatma için kullanılsın. Her bölümde toplanabilir anahtarlar, platformlar, hareketli tehlikeler ve çıkış kapısı bulunsun. O bölümdeki bütün anahtarlar toplanmadan kapı açılmasın; açık kapıya ulaşınca yalnız sonraki bölüm başlasın. Üçüncü bölümün açık kapısına ulaşmak kazanma ekranını açsın. Bölümler sırayla oynansın; başlangıç veya yeniden başlatma bölüm atlamasın. Can bitince kaybetme ekranı gelsin. Kaybetme/kazanma ekranında R veya yeniden başlat düğmesi ilk bölüm, can, skor, anahtarlar ve geçici nesneleri sıfırlasın. Geçiş ve duraklatma sırasında fizik/savaş ilerlemesin. Düşman ve efekt üretimi bölüme bağlı, temizlenen ve sınırlı yaşam döngüsüne sahip olsun; zorluk artışı kontrolsüz nesne yığılmasıyla sağlanmasın. Yeni sayısal nesne tavanı ya da oyun süresi zorunlu değildir; seçtiğin bölüm kurallarını oyunda açık anlat. Oyuncu, tehlike, anahtar, kapı, platform ve zemin için ayrı yerel SVG/PNG sprite dosyaları üret ve gerçekten çiz. Tutarlı görsel dil, okunur can/skor/bölüm HUD'ı ve oyunu örtmeyen kontroller kullan. Görsel sprite dış sınırlarını arena sınırında tut. Uzun oynama, bölüm geçişi, duraklatma ve yeniden başlatmada konsol hatası, donma veya yatay taşma olmasın.
```

İşlev kanıtı: gerçek Başla→bölüm1; kilitli kapı geçirmiyor; bütün anahtarlar→kapı→bölüm2→bölüm3→kazanma; can bitimi→kaybetme→R tam sıfırlama; P fizik durduruyor/devam ediyor; hareket/zıplama/yerel sprite kullanımı. **Mevcut arena/nişancı denetçisi B platform işlevlerini doğrulayamaz.** Aynı kontrolleri bağımsız ölçen platform denetimi dondurulmadan B koşusu karşılaştırmaya alınamaz; test için ürünü elle değiştirmek yasaktır.

## remotion B

```text
Remotion ile Fusion ve Fusion Kits için kullanım yolculuğunu anlatan 30 saniyelik, 1920x1080, 30 fps bir lansman videosu üret. fusion-tanitim/ içindeki logo.png, logo.svg, YETENEKLER.md, README.md ve KITS.md dosyalarını oku. Bütün özellik iddiaları bu belgelerden gelsin; doğrulanmayan özellik veya başarı yüzdesi yazma. Anlatı başlıkları sırayla 'Bir fikirden çalışan projeye', 'Fusion ile üretim', 'Fusion Kits ile başlangıç', 'Bir kullanım yolculuğu' ve 'Fusion ile başla' olsun. İlk başlıkta yapılacak işi tanıt; diğer sahnelerde belgelerin desteklediği yetenekleri seçip kısa somut metinlerle göster. Kullanım yolculuğu yalnız belgelerin desteklediği adımları içersin; örneği gerçek başarı kanıtı gibi sunma. Açılış ve kapanışta verilen logoyu gerçekten kullan. A videosunun sahne metinlerini veya düzenini başlangıç çözümü olarak kopyalama; bu brief için yeni düzen kur. Tipografi, hiyerarşi, ritim ve geçişler tutarlı olsun. Metinler okunur olsun, anlamlı içerik taşmasın/çakışmasın, hiçbir sahne veya final boş kalmasın. Hareketi Remotion'un kare tabanlı API'leriyle kur. Strict TypeScript kontrolünü ve gerçek render'ı tamamla; LayoutAudit/SceneFade güvenlik denetimlerini kaldırma. Nihai render out/video.mp4 olsun; yalnız render işini başlatmak teslim değildir.
```

İşlev kanıtı: strict tsc; gerçek yeni MP4, süre/boyut/FPS; bütün sahne ve son saniye kareleri; gerçek logo; belgeye dayalı iddialar; kapıların çalışması. Girdi belgelerinin byte/hash eşitliği zorunlu, metinleri modelin seçmesi bu ortak girdileri değiştirmez.

## animasyon B

```text
'Atölye Günü' adlı kurgusal etkinlik için animasyonlu tek sayfalık program arayüzü üret. index.html ve yerel CSS/JS ile açılsın. Program içeriği tam olarak şu üç kartı içersin: 10:00 'Arayüz Tasarımı' kategorisi Tasarım, açıklaması 'Tipografi ve görsel hiyerarşi üzerine uygulamalı atölye.'; 13:00 'Tarayıcıda Hareket' kategorisi Geliştirme, açıklaması 'Etkileşimlere uygun hareket ve erişilebilirlik üzerine uygulama.'; 16:00 'Prototip Paylaşımı' kategorisi Paylaşım, açıklaması 'Günün prototiplerini sunma ve geri bildirim toplama.' Kategori filtresi Tümü/Tasarım/Geliştirme/Paylaşım seçenekleriyle doğru kartları göstersin. Kart seçimi başlık, saat, kategori ve açıklamayı içeren detay açsın; kapatma düğmesi ve Escape detayı kapatsın, odak seçilen karta dönsün. Klavye ile filtre/kart/kapatma kullanılabilsin. Hero giriş hareketi, kart hover geri bildirimi, filtre geçişi ve aşağı kaydırıldığında görünen 'Nasıl katılırım?' bölümü olsun; bu bölümde 'Programı incele, uygun atölyeyi seç ve etkinlik gününde katıl.' yazsın. Etkinlik kurgusaldır, gerçek kayıt veya ödeme yapma. Özenli tipografi, tutarlı renkler ve amaca uygun easing kullan. Masaüstü ve mobilde içerik/kontroller erişilebilir kalsın; yatay taşma ve konsol hatası olmasın. prefers-reduced-motion etkin olduğunda gereksiz hareketi azalt; içerik, filtre, detay ve klavye işlevleri kaybolmasın. Harici zorunlu varlık yok; gerekiyorsa kendi yerel SVG/PNG görsellerini üret, sahte kırık görsel bağlantıları kullanma.
```

İşlev kanıtı: doğru kategori/kart sayıları; detay içeriği/close/Escape/odak; gerçek hover/scroll/filtre hareketi; mobil yerleşim; reduced-motion ile bütün etkileşimler. Mevcut hareket sayımı tek başına bu görev tamamlanmasını göstermez.

## site_kopyasi B

B, mevcut site_clone ortak TASK_TEMPLATE'in https://www.desa.com.tr ile doldurulmuş byte metnidir. Yeni özellik veya sonuca göre eşik eklenmez. İşlev kanıtı: gerçek WordPress/WooCommerce, kategori/ürün/varyasyon, sepete ekleme, sepet ve kapıda ödeme siparişinin veritabanında oluşması; kaynakla aynı viewport renkli ana/kategori/ürün kareleri; mobil menü, içerik ve checkout odağının korunması; yerel görseller ve taşma. Kaynak snapshotı ve üreticinin onu kullandığı kanıt eksiktir; aynı URL eş koşul değildir.
