# P10 — kalıcı görsel işi için uygulama alt planı

Durum: depo, dosya doğrulama, owned servis ve backend RPC bağlandı; dar
inceleme geçti. UI capability/recovery/cancel bağlantısı henüz tamamlanmadı. Ana 16 paket planının P10 alt işidir.
Kullanıcı bütün kalan paketlerin uygulanmasını yetkilendirdi; yeni onay gerekmez.
Görsel düzen onaylıdır; yeni görünür denetimler eklendiğinde ayrıca gösterilir.

## Mevcut temel ve sınırlar

- `gorsel.olustur` eski eşzamanlı sözleşmesi korunur. AppSession kapanışı artık
  bu işi iptal edip temizliğini bekler. Bu, kalıcı iş protokolü değildir.
- Akış aynı girdili kısmi sonuçtan yalnız eksikleri tamamlar; bitmiş düğümün
  açık yeniden üretimi korunur. Bozuk dosya makbuzu başarı değildir.
- `SubmissionStore` mevcut kabul/deneme otoritesidir. Yeni paralel görev deposu
  kurulmaz; görsel çıktı makbuzu aynı SQLite transaction sınırına eklenir.
- Galeri künyesi atomik yayımlanır. Ham istem, hesap sırrı veya referans dosya
  içeriği yeni iş metadata tablosuna yazılmaz.

## Sözleşme

`gorsel.saglayicilar` yalnız destek gerçekten hazırsa `isProtokolu: 1` bildirir.
Eski sunucu/fixture bu alanı vermediğinde UI mevcut eşzamanlı yolu kullanır.
Bağlantı hatası, bilinmeyen kabul veya zaman aşımı yeniden üretim gerekçesi olmaz.

- Başlat: `gorsel.is.baslat`, istemci `requestId` ve mevcut üretim parametreleri.
- Durum: `gorsel.is.durum`, aynı profile/root/conversation kapsamında `jobId`.
- İptal: `gorsel.is.iptal`, aynı kapsam ve açık kullanıcı eylemi.
- Durumlar mevcut accepted/running/completed/failed/cancelled/recoveryRequired
  sözleşmesini kullanır. İptal isteği, owned cleanup bitmeden terminal değildir.
- Aynı requestId/parametre parmak izi bir iş; değişmiş parametreyle aynı kimlik
  çakışma hatası. ACK kaybında aynı iş okunur, sağlayıcı yeniden çağrılmaz.
- Başarılı çıktı makbuzu ve terminal completed aynı SQLite transaction'dadır.
  Çıktı yolları yalnız gerçek galeri kapsamından; boyut ve içerik parmak izi
  doğrulanır. Metadata, var olmayan veya değiştirilmiş dosyaya başarı vermez.
- Süreç çökmesi sonrası başlamış/belirsiz üretim recoveryRequired olur.
  Otomatik sağlayıcı tekrarı yok; mevcut çıktı gözlemlenir veya kullanıcıya
  belirsizlik gösterilir. Yerel iptal uzak sağlayıcının ücretini geri almaz.

## Uygulama sırası ve kanıt

1. RED: aynı request paralel kabul, değişmiş girdi, ikinci süreç, ACK kaybı,
   stale terminal kayıt, iki root/conversation ayrımı. Mevcut SubmissionStore'a
   kapsamlı görsel çıktı metadata transaction'ı ekle; içerik dışı digest tut.
2. RED: çıktı commit öncesi çökme, çıktı eksik/değişmiş, bozuk/gelecek metadata.
   Galeri çıktı makbuzunu doğrulayıp atomik terminal kayıtla birleştir.
3. RED: pending job iptali, sağlayıcı finally bekleme, iki iptal, session close,
   caller cancellation ve kapandıktan sonra yeni iş reddi. Tek owned task
   kayıt otoritesi kullan. SubmissionStore, görsel işler bitmeden kapatılamaz;
   ses durdurma bu bekleyişin önünde kalmalıdır.
4. Backend üç route ve capability işareti; legacy route regresyonları.
5. UI capability bağlama, aynı requestId ile ACK kaybı uzlaştırması, bounded
   durum sorgusu, client/root sahibi değişince eski sonucu göstermeme.
   Poll başarısızlığı provider retry değildir. Mevcut kısmi sonuçlar korunur.
6. Görünür durum/iptal/yeniden açma, klavye ve mobil ekran kanıtı; kullanıcıya
   yeni görünür denetimleri göster. Sahte fixture ile native kabulü karıştırma.
7. İlgili Python/App testleri, type/lint, inceleme ve son tam kapılar. Native
   kurulum ve gerçek sağlayıcı kabulü P16 matrisiyle ayrıca doğrulanır.

Bu alt plan tamamlanmadan P10'un kalıcı iş/restart/cancel kabulü kapatılmaz.
