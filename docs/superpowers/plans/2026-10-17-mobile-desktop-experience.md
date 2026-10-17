# Mobil ve masaüstü kullanım iyileştirmeleri

Kullanıcı kapsamı: tüm işlem onayları telefondan da verilir; sohbet onayın birincil yeridir, Onaylar aynı kuyruğun toplu görünümüdür. Ekran izleme tercihi cihaz için hatırlanır. Ek yetki seçimleri ayarlar kapanıp açılınca korunur. Mini dock hem açık uygulama/pencereleri hem Chrome sekmelerini tek dokunuşla seçer. Telefonun izlediği masaüstünü yeniden gösteren popup kaldırılır; yalnız gerçek ajan etkinliğinin önizlemesi gösterilir. Ekran boyutu, eğitim sayfasının kutulu görünümü ve rozetler düzeltilir.

Kullanıcı onayı: 17 Ekim mesajında uygulama ve push istendi; tüm onayların telefonda verilebilmesi ile dock'un her iki hedef türünü içermesi ayrıca doğrulandı. Release yayını ancak kullanıcının son onayından sonra yapılacak.

## Uygulama sırası

1. Onay cevabının AppSession'a ulaşmasını uçtan uca test et. Reddedilmiş/teslim edilmemiş cevap başarı gösterilmesin; sohbet ve Onaylar kartları aynı olaylarla kapanıp görev sürsün. Yüksek etkili işlemler için telefonda da belirli işleme açık ikinci teyit olsun; otomatik toplu yetki yok.
2. Ekran güven tercihini cihaz bazında kalıcı sakla; kullanıcı kesmesi/cihaz iptali güveni ve oturumu kapatsın. Eski süresi bitmiş oturumlar ekran sekmesine girildiğinde tekrar tekrar onay istemesin. Ayrı cihaz ve kanal birbirine yetki taşımamalı.
3. Uzaktan erişim ek kapsam seçimlerini doğrulanmış yerel tercihte sakla; bu seçimler yalnız sonraki eşleştirme isteğine uygulanır, mevcut cihazlara gizlice yetki verilmez.
4. Mobil ekrandaki görüntü kutusunu gerçek kare oranına uydur; tam ekran ve yatay/dikey geçişi doğrula. Onay kartlarının işlem/hata durumlarını ve metin hiyerarşisini düzenle.
5. macOS açık pencere/uygulama ve bağlı Chrome sekmelerini mevcut adaptörlerden listele; mini dock yalnız listelenen hedefi etkinleştirsin. İkonları varsa yerel uygulama ikonundan getir; URL/komut metni yürütme olmasın.
6. Telefon izleme popup'ını kaldır; gerçek ajan masaüstü/tarayıcı işini gösteren önizlemeyi mevcut olaylardan besle. Masaüstü kontrolünde arka plan etkileşimi gerçekten desteklenen adaptörlerde ön plan korunur; sistemin zorunlu ön plan işlemleri arka planda yapılmış gibi gösterilmez. Codex davranışının kapalı kaynak uygulaması kopyalanmış varsayılmaz.
7. Nasıl yapılır sayfasını daha açık satır düzenine ve tema değişkenlerinden gelen tutarlı rozetlere geçir.
8. Python ruff/mypy/pytest, frontend test/build, ilgili tarayıcı/desktop testleri ve bağımsız inceleme. Kabul edilen kapsamın tamamı doğrulanmadan tamamlandı denmez. İlgisiz test_plan_resume.py değişikliği korunur ve commit'e alınmaz.
9. Son kodu Türkçe conventional commit ile commit/push et. Tag/publish/release workflow tetikleme; kullanıcıya test sonuçları ve yayına hazır paket sun.

## Dosya sınırları

- Onay ve ekran sunucusu: remote/{approvals,rpc,backend,screen,devices,controller}.py ve ilgili testler.
- Mobil akış: remote/pwa/{approvals,chat,app,styles,screen-stream}.js/css ve davranış testleri.
- Ayar tercihleri: app/src/settings/RemoteAccess.tsx ve yeni küçük tercih modülü/testi.
- Dock/ajan önizlemesi: yeni odaklı appserver/remote adaptörleri, React/PWA dock bileşenleri; mevcut desktop/browser köprülerini kullanır.
- Eğitim: app/src/guide/guide.css ve gerekirse TopicCard/HowTo.

## Kaynak

OpenAI resmî Computer Use belgesi macOS'ta kullanıcı başka yerde çalışırken arka planda sınırlı uygulama işi yapılmasını ve uygulama bazlı kalıcı onayları açıklıyor: https://learn.chatgpt.com/docs/computer-use . Bu belge Fusion'ın aynı sistem altyapısına sahip olduğu anlamına gelmez; Fusion uygulaması mevcut platform adaptörlerinde doğrulanacak.
