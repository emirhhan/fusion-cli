# Birleşik belge teslimi ve kabul bağlamı: bağımsız Python incelemesi

5 Kasım 2026. İncelenen sabit sürüm
`fa8500fc492a464f16cd92913c9135735a04347a`; ayrı `git archive` görüntüsü kullanıldı.
Sonuç: **BEKLET**, aynı kabul edilmiş sohbete dönüldüğünde açık izin geri alma
işleminin çalışan kopyaya ulaşmaması giderilmeden birleşik arka uç onaylanmadı.

## Önceki bulguların durumu

`74f3ec4f` için bildirilen üç sınıfın sekiz bağımsız kırmızı kontrolü bu sürümde
geçiyor: ayrıntı listesi olmadan gelen kritik toplamlar, kaynak URL sorgusunun
yanlış çıktı hedefi sayılması ve açık kod çıktısı isteğinde belge sunumu seçilmesi.
Kaynak yolunun özgün yazımı ve bütünlüğü korunuyor; başarısız veya ölçülmemiş
sayaçlar doğrulanmış başarıya dönüşmüyor.

## YÜKSEK — Sohbete dönünce açık izin geri alma çalışan turda etkisiz

1. `accepted` sohbetinde AUTO kipinde iki hatırlanmış site izniyle bir tur başlat.
2. Sahte yürütücü beklerken `other` sohbetine, ardından `accepted` sohbetine dön.
3. Aynı kabul edilmiş kök/sohbet kimliği görünürken açık SECURITY seç veya tek
   site iznini ayarlardan geri al.
4. Yürütücüyü sürdür: `current_approval()` hâlâ AUTO, kabul anındaki izin kopyası
   hâlâ geri alınan izni taşıyor.

`_same_accepted_chat` bu aşamada doğrudur. Ancak `_sync_active_approval` tam görünür
nesil eşitliğini aradığı için geri almayı kopyaya aktarmıyor. Sonuç/config/history
benimsemesinin eski nesle uygulanmaması doğru korumadır; aynı sahibi hedefleyen
açık güvenlik geri alması bu benimseme koşulundan ayrı değerlendirilmelidir.

Bağımsız üç varyantta SECURITY ve tek-site geri alma kırmızı, değişiklik
yapılmayan izin devamlılığı yeşildir. Tek site A geri alındığında ilgisiz site B
izninin kalması da sınanır; düzeltme kullanıcının diğer izinlerini gereksiz yere
silerek tekrar onay istememelidir. İzinler yalnız yerel sahte nesnelerdir;
hiçbir gerçek tarayıcı/uygulama eylemi gerçekleştirilmedi.

## Doğrulama

- Önceki sekiz kusur, Unicode/redaksiyon/32 KiB/yol/future-version ve gerçek
  RPC → tek günlük satırı → makbuz tekrarı → yeniden açılan sohbet kimliği →
  model geçmişine metadata girmemesi → tombstone kontrolleri dahil **96 test
  başarılı, 16,60 saniye**. Sunum, kabul bağlamı ve otomatik profil modülleri de
  bu koşuya dahildir; önceki iki kök/sohbet sahipliği tekrarı yeşildir.
- Yeni üç izin varyantı: **iki başarısız, bir başarılı, 1,74 saniye**.
- Sekiz değişen Python dosyasında Ruff ve altı ürün dosyasında dar mypy temiz.
- Bütün süreçler terminaldir. Ürün dosyası, gerçek tercih, ağ/model/native veya
  kullanıcı kancası çalıştırılmadı.

Tekrar dosyaları görev çalışma alanında
`work/reliability-v2/document-delivery-python-review-v6/test_projection_contract.py`
ve `test_roundtrip_revocation.py` altında korunur. Ayrı genel incelemenin metadata
null sözleşmesi bulguları bu Python kaydında çözülmüş gibi ileri sürülmez.
