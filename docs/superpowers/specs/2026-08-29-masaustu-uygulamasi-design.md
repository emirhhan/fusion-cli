# Masaüstü Uygulaması Tasarımı

**Tarih:** 2026-08-29

## Amaç

Fusion'ın masaüstü uygulaması. B'de açılan stdio protokolünü tüketir; görsel
dili [2026-08-29-uygulama-gorsel-dil.md](2026-08-29-uygulama-gorsel-dil.md)
belgesinde ölçülerek çıkarılan referanstır.

## Yığın

**Tauri 2 + React + TypeScript.**

Tauri seçildi çünkü alt süreç yönetimi (sidecar) birinci sınıf destekleniyor ve
mimarimiz tam olarak bu: uygulama Python çekirdeğini doğurup stdio üzerinden
konuşuyor. Electron'da aynı köprü elle kurulur.

Rust tarafı İNCE tutulur: süreç başlatma, stdio köprüsü, pencere yönetimi.
Ürün mantığı ve tüm ekranlar TypeScript tarafındadır. Gerekçe: Rust'ta biriken
her satır, hata ayıklarken ikinci bir dile geçmek demektir.

Ön koşullar makinede doğrulandı: Node 22, Xcode Command Line Tools, Rust 1.98.

## Çekirdek bağlantısı

Uygulama açılışta çekirdeği şu sırayla arar:

1. Uygulama paketiyle birlikte gelen sidecar ikilisi.
2. Bulunamazsa sistemdeki `fusion` komutu.

İkinci yol v1'de kullanılacak; birincisi Python paketlemesi yapıldığında
devreye girer ve **uygulama mimarisi değişmez**. Bu sıralama baştan kurulur ki
paketleme sonradan bir yeniden yazım gerektirmesin.

Çekirdek bulunamazsa uygulama bunu açıkça söyler ve kurulum yönergesi gösterir;
boş bir pencereyle sessizce açılmaz.

## Oturum modeli

**Bir pencere bir oturum, bir oturum bir çekirdek süreci.** B'de kararlaştırılan
"bir süreç bir oturum" kuralının doğal sonucu. İkinci sohbet ikinci pencere ve
ikinci süreç demektir.

Pencere kapanınca süreç sonlandırılır. Süreç beklenmedik biçimde ölürse uygulama
bunu gösterir ve yeniden başlatma sunar.

## Durum sahipliği

Uygulama gerçeğin kaynağı DEĞİLDİR. Etkin model, onay modu, komut listesi,
oturum geçmişi — hepsi protokolden gelir ve uygulama yalnız gösterir.

Gerekçe: terminal ve uygulama aynı yapılandırmayı paylaşıyor. Uygulama kendi
kopyasını tutarsa ikisi sessizce sapar; B'nin final denetiminde bulunan
"komutla değişen config tura ulaşmıyor" hatası tam olarak bu sınıftandı.

İstisna: yalnız arayüze ait geçici durum (açık panel, kaydırma konumu, taslak
metin) uygulamada tutulur.

## Ekranlar

| Ekran | İçerik | Protokol karşılığı |
|---|---|---|
| Kenar çubuğu | Oturum listesi, yeni sohbet, geçmiş devralma | `oturum.durum`, `komut.calistir` |
| Boş başlangıç | Ortada karşılama ve girdi kutusu | — |
| Konuşma | Mesajlar ve canlı olay akışı | `tur.calistir`, `olay` |
| Onay diyaloğu | Üç seçenek; yıkıcı işlemde oturum izni gizli | `soru` / `cevap` |
| Seçici | Çok adımlı seçim yükünü çizer | `komut.secenekler` |
| Ayarlar | Komut defterinden kurulur | `komut.listele`, `komut.calistir` |

### Konuşma görünümünün kuralı

Kullanıcı ve asistan mesajları **simetrik değildir**:

- Kullanıcı mesajı: sağa hizalı, `#F5F5F5` zeminli yuvarlatılmış kabarcık.
- Asistan mesajı: kabarcık YOK; zemin üstünde tam genişlikte düz metin.

İki taraflı kabarcık düzeni referansın görünümünü bozar. Bu, ölçülmüş bir
gözlemdir, tercih değil.

### Olay akışının gösterimi

Tur sırasında akan olaylar (araç çalıştırma, model çağrısı, dosya değişikliği,
tur sonucu) konuşma akışında asistan mesajının yanında gösterilir. Ham JSON
gösterilmez; her olay tipinin okunabilir bir karşılığı olur.

Tur sonucu (`TurnOutcome`) açıkça basılır: tamamlandı / kısmi / başarısız.
Bu, terminalde eklenen davranışın aynısıdır ve modelin düz metindeki
iddiasından bağımsızdır.

## Görsel dil

Ölçülmüş palet ve oranlar görsel dil belgesinde. Uygulama bunları CSS özel
değişkenleri olarak tanımlar; hiçbir bileşen ham renk kodu yazmaz.

## Hata durumları

- Çekirdek bulunamadı: kurulum yönergesi gösterilir.
- Çekirdek süreci öldü: uyarı ve yeniden başlatma sunulur.
- Çözülemeyen protokol satırı: atlanır ve geliştirici günlüğüne yazılır;
  kullanıcı arayüzü bozulmaz.
- Cevaplanmamış soru varken pencere kapanırsa: süreç sonlandırılır, çekirdek
  soruyu reddedilmiş sayar (B'de tanımlı davranış).

## Test

- Protokol istemcisi saf: satır girdi → durum çıktısı. Çekirdek süreci
  başlatmadan sınanır.
- Ekran bileşenleri sahte protokol olaylarıyla sınanır.
- Uçtan uca: gerçek `fusion app` süreciyle bir tur çalıştırma. Model çağrısı
  gerektirmeyen isteklerle (`oturum.durum`, `komut.listele`) yapılır.

## Dağıtım

İmzasız. Apple Developer hesabı yok ve alınmayacak. macOS'ta ilk açılışta
uygulama engellenir; kullanıcı sağ tık → Aç ile geçer. İndirme sayfasında bunu
anlatan kısa bir yönerge bulunur.

## Kapsam dışı

- Python paketleme (sidecar yolu hazır bırakılır, doldurulmaz).
- Otomatik güncelleme, çökme raporlama.
- Windows ve Linux derlemeleri.
- Referans kitin Fusion'da karşılığı olmayan 48 ekranı.
- Eşzamanlı çoklu oturumun tek pencerede sekmelenmesi.

## Açık sorular

Yok. Uygulama planına geçilebilir.
