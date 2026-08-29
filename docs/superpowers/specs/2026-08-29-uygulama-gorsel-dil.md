# Uygulama Görsel Dili — Ölçülmüş Referans

**Tarih:** 2026-08-29

Masaüstü uygulamasının (C alt projesi) görsel dili. Değerler tahmin değil:
referans tasarımın Figma'dan render edilmiş görüntülerinden **ölçülerek**
çıkarıldı.

## Kaynak ve yöntem

Referans: SnowUI "Snow ChatGPT UI Kit" Community dosyası
(`Ww1r27dBbLQhdtJGn5e1ub`), ticari kitin ücretsiz önizleme sürümü.

Önizleme dosyası **düzleştirilmiştir**: ölçüldü — 0 metin düğümü, 0 bileşen,
0 tasarım değişkeni, 4.516 vektör. `get_design_context` bir ekran düğümünde
166 adet `<img>` etiketi döndürdü; tek bir renk kodu ya da yazı taşımıyor.
Dolayısıyla bileşen ağacını otomatik koda çevirmek mümkün değil.

Bunun yerine ekranlar Figma'dan render edildi ve değerler görüntüden ölçüldü:

- **Renkler:** bileşen bölgelerinden mod (en sık piksel) örneklemesiyle.
  Nokta örneklemesi yazı ve kenar yumuşatma piksellerine denk geldiği için
  bölge modu kullanıldı; her değerin yanında kapsama oranı doğrulandı.
- **Ölçüler:** kenar geçişleri taranarak piksel sınırları bulundu, sonra
  referans genişliğe oranlandı.

Yöntem doğrulaması: ölçülen kenar çubuğu genişliği 1440px pencerede 281px'e
karşılık geliyor — referans ürünün bilinen değeriyle örtüşüyor.

## Renk paleti (ölçülmüş)

| Rol | Değer | Kapsama | Nerede |
|---|---|---|---|
| Zemin | `#FFFFFF` | %100 | Ana içerik alanı, girdi kutusu, üst bar |
| Kenar çubuğu zemini | `#F9F9FA` | %98 | Sol panel ve alt panel |
| Seçili/vurgulu satır | `#EFEFF0` | %85 | Kenar çubuğunda etkin öğe |
| Kullanıcı mesajı balonu | `#F5F5F5` | %75 | Sağa hizalı mesaj kabarcığı |
| Birincil buton | `#000000` | %68 | Gönder/ses butonu |
| Vurgu hapı | `#EBEBFA` | %68 | Üst bardaki yükseltme rozeti |
| Sönük metin | `#7C7C7D` | — | İkincil etiketler, bölüm başlıkları |
| Ayraç / kenarlık | `#E9E9EB` | — | Panel ayraçları, girdi kutusu kenarı |

Palet neredeyse tamamen nötr: tek renkli vurgu `#EBEBFA` lavanta hapı.
Ürün kimliği renkten değil, tipografi ve boşluktan geliyor.

## Ölçüler (1440px genişlikte pencere referansı)

| Öğe | Ölçülen oran | 1440px karşılığı |
|---|---|---|
| Kenar çubuğu genişliği | %19,5 | 281px |
| İçerik sütunu (girdi kutusu) | %80,5 | ~1159px |
| Kullanıcı balonu en fazla genişlik | içerik sütununun ~%82'si | ~950px |

Kenar çubuğu sabit genişlikte, içerik alanı esnektir.

## Ekran envanteri ve Fusion karşılıkları

Referans kit 54 masaüstü ekranı içeriyor. Çoğunun Fusion'da karşılığı **yok**
(GPT mağazası, görsel üretme, sesli sohbet, builder profili, bağlı uygulamalar).
Fusion'ın ihtiyacı olan ve B'de açılan protokolle birebir örtüşen ekranlar:

| Ekran | Referans düğüm | Protokoldeki karşılığı |
|---|---|---|
| Kenar çubuğu + oturum listesi | `676:4632` | `oturum.durum`, geçmiş devralma |
| Konuşma görünümü | `676:2743` | `tur.calistir`, olay akışı |
| Boş başlangıç ekranı | `676:2591` | — |
| Ayarlar | `676:2122` | `komut.listele`, `komut.calistir` |
| Onay diyaloğu | ayarlar modallarından uyarlanacak | `soru` / `cevap` |
| Model/kademe seçici | ayar seçicilerinden uyarlanacak | `komut.secenekler` |

## Konuşma görünümünün yapısı

Ölçülen düzen:

- **Kullanıcı mesajı:** sağa hizalı, `#F5F5F5` zeminli yuvarlatılmış kabarcık,
  içerik sütununun tamamını kaplamaz.
- **Asistan mesajı:** kabarcık YOK. Zemin üstünde tam genişlikte düz metin;
  başlık, paragraf ve alıntı blokları normal tipografi akışında.
- **Mesaj altı eylemler:** küçük ikon sırası (kopyala, düzenle), yalnız ilgili
  mesajın altında.
- **Girdi kutusu:** alta sabitlenmiş, yuvarlatılmış, `#FFFFFF` zeminli, ince
  kenarlıklı. İçinde yer tutucu metin, sol altta eylem hapları, sağ altta
  birincil siyah buton.

Bu ayrım önemli: kullanıcı ve asistan mesajları **simetrik değil**. İki taraflı
kabarcık düzeni referansın görünümünü bozar.

## Kapsam dışı

Bu belge yalnız görsel dili tanımlar. Uygulamanın mimarisi, çerçeve seçimi ve
paketlemesi ayrı bir tasarım belgesinde ele alınır.

## Bilinen kısıt: dağıtım

Proje sahibinin Apple Developer hesabı yok ve açmayacak. macOS'ta imzasız
uygulama ilk açılışta engellenir; kullanıcı sağ tık → Aç ile geçmek zorundadır.
Bu, mimariyi değil ilk açılış deneyimini ve kurulum yönergesini etkiler.
