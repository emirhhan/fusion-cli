# P11 — Kits sohbet oluşturma kabul makbuzu

Durum: tasarım hazır; kod henüz yazılmadı. Kullanıcının bütün kalan paketler
ve bitene kadar devam yetkisi kapsamındadır. Yeni görünür toparlanma denetimleri
ayrıca görsel onaya sunulur. Kalan iş, yalnız React pending bayrağı değildir.

## Otorite ve karar

- Mevcut WorkspaceStore SQLite dosyası kullanılır; Pages/ComputerStore gibi aynı
  bağlantıya bağlı küçük ConversationRequestStore eklenir. İkinci görev deposu yok.
- Owner + requestId anahtarında girdi digest'i, önceden ayrılmış threadId ve kabul
  durumu saklanır. Aynı kimlik/farklı Kit veya başlık çakışır. Ham görev istemi,
  provider token veya hesap sırrı makbuza yazılmaz.
- Yanıt kaybı yeni uzak createThread çağrısına gerekçe değildir. Kabul edilmiş
  threadId ile sahip/Kit/archived metadata'sı gözlemlenir. Doğrulanamıyorsa sonuç
  belirsiz kalır; yeni thread üretildi veya eski thread silindi denmez.
- Yerel ensureThread aynı kimlikte idempotent olduğundan pending yerel kabul
  güvenli tamamlanabilir. Uzakta gözlem mevcut restoreThreadBinding doğrulaması
  ile aynı kurala bağlıdır. Geçerli bağ ve completed makbuzu aynı transaction.
- Aynı süreçte duplicate pending istek aynı owned promise'i bekler. Süreçler
  arasında SQLite claim tek sahip verir; ikinci süreç gözlemler, üretimi tekrarlamaz.
- Eski clientsiz requestId sözleşmesi uyum için kalır; yeni UI kimliği ilk POST
  öncesinde owner/Kit kapsamıyla kalıcı saklar. Kayıt bozuk/yazılamazsa oluşturma
  durur. Başarı doğrulanıp marker kaldırılmadan ilk model görevi otomatik yollanmaz.

## Uygulama ve kapılar

1. RED: WorkspaceStore claim parallel/reopen/owner isolation/input conflict,
   binding+receipt atomic commit/rollback/future schema. Aynı bağlantı adaptörü.
2. RED: Platform create response lost, aynı request tekrarında tek create,
   local restart, yabancı owner/Kit gözlemi, read failure/ambiguous. Yeni typed
   kabul hatası; legacy create ve restore regresyonları.
3. Additive API requestId ve scoped request status. Server-side validation ve
   secret-free hata metni; başarısız mutasyon kör tekrarlanmaz.
4. UI ref singleflight + owner/Kit marker; seçili alan değişiminde eski sonuca
   navigasyon yok; ACK kaybında aynı request recovery. Yeni promptu eski işlem
   gibi otomatik göndermeme. Kayıt kaldırma başarısızlığında görünür engel.
5. Node24 unit/type/lint/format ve gerçek yerel API/browser reload/ACK lost
   fixtures. Yeni görünür UI kareleri insan onayına. Kits upstream OpenDots'a
   push yok; doğru hedef mevcut yayın aşamasında ayrıca çözülür.

Main Python tam kapısı sırasında Python src/tests değiştirilmez. Bu alt iş
Kits'te bağımsız ilerler; native/gerçek Intelligence kabulü ayrı P16 kanıtıdır.
