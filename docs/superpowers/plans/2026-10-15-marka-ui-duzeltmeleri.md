# Kullanıcının görsel düzeltmeleri

15 Ekim: Şeffaf F onaylandı. 74 ekranın UI onayı verilmedi. Kullanıcı yeşilin kaldırılmasını, logo tonlarını, Kits karakterinde ses/onay yüzeylerini, sağ panelde seçilebilir canlı ajanları ve gerçek Claude/Codex ikonlarını istedi. Bu somut kapsam uygulanacak; sonuç tekrar görsel onaya sunulmadan push yok.

- [x] Ana tema ve Kits: yeşil marka vurgularını mavi/camgöbeği/mor ile değiştir; koyu yüzey hiyerarşisini koru, okunabilir metin ve düğme çiftleri kullan.
- [x] Ses/onay: mevcut davranış ve onay sözleşmesini koruyarak uyumlu yüzey, kenarlık, kapsül düğme ve vurgu renkleri.
- [x] Sağ panel: Ajanlar sekmesi, ajan seçimi, mevcut olaylardan güncel adım ve araç izi; sohbetten kartları kaldır. Oturum değişince seçim sıfırlanır. Durmuş turdaki ajan çalışıyor diye sunulmaz.
- [x] Kaynak ikonları: resmî Claude sitesinin işareti ve kurulu OpenAI uygulamasındaki Codex ikonları; kaynak/SHA kaydı. Ürünle birlikte yerel dosya olarak sunulur.
- [x] Davranış testleri, TypeScript/build, inceleme, açık/koyu ekranlar ve insan onayı.

Son durum: revizyon3 için kullanıcı “Bu UI ve karakter setini onaylıyorum” dedi. Bu görsel kapsam tamamlandı; kalan paketler ve native/günlük kullanım kapıları ayrı takip edilir. Commit/push henüz yapılmadı.
