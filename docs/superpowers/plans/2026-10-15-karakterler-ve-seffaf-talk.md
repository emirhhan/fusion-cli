# Özgün karakter ailesi ve şeffaf Talk

Kullanıcının revizyon-2 reddi sonrası somut isteği: Kits ayar arka planı değişsin; sekiz Kit karakteri yeniden üretilsin, mevcut yumuşak sevimli tipe benzesin ama aynı olmasın; ana Fusion ses karakteri aynı yeni ailede olsun. Talk pencereyi dolduran zemin yerine pet görünümü: karakter ve altında yalnız soru olduğunda tek paragraflık soru özeti, tıklanınca tam metin.

Uygulama kararları: gerçek PNG alfa, mevcut karakter kimlikleri korunur; eski varlıklar kaynak geçmişinde tutulur, yeni v2 dosyalarına referans geçer. Mavi/cyan/mor ailesinde dokuz farklı siluet; eski karakterlerin yalnız renk varyasyonu olmaz. Ses kontrolleri küçük yüzen menüde erişilebilir; hata/dinleme ve kapanış davranışı korunur. Soru açılması cevap göndermez; cevaplar aynı onay kanalında, pending kilidi korunur. Tam soru okunabilir/kaydırılabilir; yeni soru geldiğinde kapalı özetle başlar. Escape önce ayrıntıyı kapatır. Native şeffaflık mevcut, yeniden platform API eklenmez. Native masaüstünde click-through kabulü ancak gerçek ölçümle iddia edilir; tarayıcı testi yeterli sayılmaz.

- [x] Dokuz ayrı yerleşik imagegen çıktısı, alfa ve siluet kontrolü, depoya kopya + prompt/SHA manifest.
- [x] Kits karakter kaynakları ve ayar yüzeyleri iki tema.
- [x] Talk pet düzeni, soru özeti/tam soru, normal/mini geometri uyumu.
- [x] Yaşam döngüsü/durum/onay testleri, type/build/review; yeni görseller ve kullanıcı onayı.

Nihai insan yönü: hayvan taslakları reddedildi; basit soyut mavi örneğin tarzı onaylandı ve v3 ailesi uygulandı. Kullanıcı revizyon3 galerisi için “Bu UI ve karakter setini onaylıyorum” yanıtını verdi. App150dosya1117test ve Kits86dosya404test, iki build ve dar incelemeler geçti. Bu görsel iş tamamlandı; gerçek native click-through ve günlük kullanım kabulü ana planın Paket16 kapısında açık kalır.
