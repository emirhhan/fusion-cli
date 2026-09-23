# Fusion masaüstü ürün eşliği

## Amaç

ChatGPT masaüstü/web kullanımının görünür düzenini ve günlük iş akışlarını Fusion'da
yeniden üretmek; Fusion'ın proje araçları, denetçi, çoklu sağlayıcı, alt ajan ve
kod değiştirme yeteneklerini korumak. Görsel benzerlik tek başına kabul ölçütü
değildir: her düğme gerçek bir işlem yapmalı ve işlem sonucunu göstermelidir.

## Referans ve sınırlar

- Aynı mantıksal ekran boyutunda ChatGPT ve Fusion ekranları karşılaştırılır.
- ChatGPT hesabına ait alanlar yalnız oturum açıldıktan sonra ölçülür; giriş
  gerektiren bir yüzey tahminle "aynı" diye işaretlenmez.
- Fusion yerel proje klasörlerini yönetir. "Projeyi sil" dosya sistemindeki
  projeyi silmemelidir; ayrı ve açık bir sohbet/geçmiş kaldırma işlemi gerekir.
- Web sağlayıcısının belirli modelini seçmek, tarayıcıda o modeli gerçekten
  değiştirmeli ve sonraki turda gözlenen modelle doğrulanmalıdır. Sadece model
  adını menüye eklemek kabul edilmez.
- Paylaşımda kullanıcı açıkça yayımlamadıkça yerel sohbet içeriği dışarı çıkmaz.

## İş akışı envanteri ve kabul ölçütleri

| Yüzey | Kabul ölçütü |
| --- | --- |
| Kabuk ve gezinme | Kenar çubuğu, başlık, dar ekran, boş sohbet, arama ve profil menüsü aynı ölçekte; klavye ve odak sırası çalışır. |
| Sohbet akışı | Kullanıcı balonu, asistan markdown/kod/diff kartı, düşünme ve çalışma durumu tekil; durdurma sonrası sayaç ve animasyon biter. |
| Composer | Ek, komut, dosya anma, model, dikte, sesli konuşma, gönder/durdur ve çalışan turda kuyruk birbiriyle çakışmaz. |
| Modeller | Katalog canlıdır; anahtarsız/bağlantısız/kapalı seçenekler seçilemez. Basit, orta ve büyük görev grupları yalnız doğrulanmış eşlemeden gelir. |
| Web modelleri | Her oturumun erişebildiği seçenekler keşfedilir; seçim sayfada uygulanır; gözlenen model farklıysa Fusion bunu hata olarak gösterir. |
| Projeler | Proje oluşturma/açma/listeden kaldırma; sohbeti başka projeye taşıma; açık süreç ve transcript tutarlılığı. |
| Hafıza | Anı ekleme/listeleme/tekil silme/kapatma; kapalı anı prompta girmez; veri yerel ve kalıcıdır. |
| Paylaşım | Görünür paylaş düğmesi, içerik önizleme ve kullanıcı kontrollü dışa aktarma; ortak bağlantı varsa geri alma. |
| Ayarlar | Görünüm, kişiselleştirme, ses, modeller, izinler, veri denetimi ve güncellemeler tutarlı menüden erişilir. |
| Uzun görev | En az bir gerçek proje üzerinde plan→kod→test→gözden geçirme→uzun yanıt; iptal, yeniden açma ve hata dönüşleri gözlenir. |

## Doğrulama kapıları

1. Python: Ruff, mypy, pytest.
2. Arayüz: TypeScript build, Vitest, görsel ekran görüntüleri ve klavye akışları.
3. Native: Tauri build, ses izinleri/dikte/konuşma, açık süreç ve yerel hafıza.
4. İki pencere karşılaştırması: aynı boyutlarda gerçek ChatGPT ve Fusion;
   yalnız geçen satırlar tamamlandı sayılır.
5. Kurulum ve GitHub release, önceki dört kapı geçtikten sonra yapılır.

## İlerleme

- [x] Composer model menüsündeki rol/model karışıklığı giderildi; canlı, bağlı
  katalog ve görev grupları eklendi.
- [x] Kişiselleştirme için yönetilebilir yerel anı deposu ve ayarları eklendi.
- [x] Sesli konuşmadan ayrı dikte yolu composer'a bağlandı.
- [ ] Gerçek ChatGPT hesabıyla tam ekran envanteri ve piksel karşılaştırması.
  Boş sohbet ve ayarlar 1270×768 ölçüsünde karşılaştırıldı; diğer ekranlar açık.
- [x] Web sağlayıcısında belirli model keşfi, uygulama ve tur doğrulaması.
  Gemini oturumunda 3.1 Pro/3.6 Flash/3.5 Flash-Lite canlı menüden seçildi;
  yanlış gözlenen modelde işlem durduruluyor.
- [x] Proje taşıma/kaldırma ve yerel metin paylaşımı eklendi. Proje kaldırma
  geri alınabilir liste gizleme işlemidir; çalışma dosyalarını silmez.
- [ ] Ayarlar ile sohbet kabuğunun bütünsel görsel/etkileşim uyumu.
- [ ] Uzun görev kabul koşusu, paket, kurulum ve release. Gemini 3.1 Pro ile
  arena survival görevi 19 model çağrısında, 492.8 saniyede davranışsal testi
  geçti (hasar, ölüm/XP, oyuncu hasarı, seviye atlama, konsol temizliği);
  90 saniyelik mevcut hız eşiği geçilmedi.
- [x] 0.4.4 Apple Silicon paketi üretildi, uygulama paketi açılış testini geçti,
  kurulu 0.4.3 sürümü geri alınabilir biçimde Çöp'e taşınarak 0.4.4 kuruldu.
  Gerçek uygulama penceresi açıldı; model menüsü ve Gemini hesabının canlı
  seçenekleri görüntülendi. Eski masaüstü yedek uygulamaları ve DMG Çöp'te.
- [ ] Ürün eşliği kapısı hâlâ açık: ChatGPT'nin yan menüdeki kitaplık,
  zamanlanmış işler ve bazı diğer akışlarının Fusion'da eşdeğer işlemleri yok.
  Fusion'daki görsel/video oluşturma düğmeleri şu anda yalnız "Daha sonra"
  ekranını açıyor. Bu durum giderilmeden tam ChatGPT eşliği iddia edilemez.
