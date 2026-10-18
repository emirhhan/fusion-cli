# Geri yüklenen konuşmanın okunabilirliği

Kullanıcı her ara açıklamanın ayrı bir ana cevap gibi görünmesinden, gereksiz
boşluklardan ve öğretmen metninin ana sohbete karışmasından şikâyet etti.

## Düzeltme

`oturum.gecmis` araç çağrısı taşıyan asistan mesajlarını `ara:true` olarak
aktarır; boş ve harness mesajlarını görünür geçmişe koymaz. Asıl model geçmişi
korunur. Normal açılış ve dış geçmiş devralma aynı görünür mesaj çözücüsünü
kullanır; `ara` ve mesaj kimliği iki yolda da korunur.

Konuşmada ardışık ara açıklamalar ve araç izleri native `details/summary`
altında toplanır. Ana cevap, kullanıcı mesajı, açık hata ve terminal durumları
bu gruba katılmaz. Çalışırken yalnız son kısa açıklama ve gerçekten son çalışan
araç durumu dışarıda kalır. Biten araçlar ikinci kez çizilmez. Görev listesi
sınırında da tek etkin gösterge vardır. Orijinal mesaj indeksleri korunduğu
 için yeni sohbette devam eylemi doğru yanıta bağlıdır. Kullanıcının adımları
 göster tercihi açılır bölümün görünümüne uygulanır.

## Geri yükleme verisindeki düzeltme

Önceki onarım betiği, ilk koşunun iki öğretmen `ModelCallFinished` olayını ana
ajanın cevabı gibi yeniden kurmuştu. Öğretmen yanıtları zaten `ask_teacher`
araç sonucunda bulunuyordu. V2 geri yükleme yalnız asıl ajan rolünün model
cevaplarını alır. İki yinelenen iç yanıt çıkarılır, 34 gerçek araç sonucu ve
kullanıcının görevi korunur. Devam noktası 18 Ekim 23:16 olarak kalır; proje
kaynakları değişmez. Önceki günlük ayrıca yedeklenir. İş başlatılmaz.

## Doğrulama

- 187 arayüz test dosyasında 1376 test geçti.
- İlgili üç Python dosyasının 105 testi geçti; Ruff ve mypy temiz.
- Üretim derlemesi, desteklenen Node 22 hooks lint ve TypeScript kontrolü geçti.
- Playwright açık/koyu tema, 390/1440 px olmak üzere dört senaryoda geçti:
  kapalı ayrıntı, klavyeyle aç/kapat, görünür final, canlı son açıklama ve taşma.
- React, TypeScript ve Python incelemelerindeki bulgular giderildi; son
  incelemelerde engel kalmadı.
- 0.7.11 runtime kaynak hash eşleşmesi ve paketli duman testi geçti.
- Görünüm örneği yedek klasörüne `sohbet-gorunumu-ornek.png` olarak kaydedildi;
  bu gerçek Conversation bileşenini kullanan sentetik bir önizlemedir.

Kurulum doğrulaması: Fusion 0.7.11 `/Applications/Fusion.app` olarak kuruldu,
kararlı imza doğrulandı ve gerçek uygulama 0.7.11 runtime süreçleriyle açıldı.
Eski 0.7.10 uygulaması yedek klasöründe korundu. Düzeltilmiş geri yüklemede
71 mesaj ve 34 araç sonucu var; VFS-BOT kaynakları aynı kaldı. Aktif tur
başlatılmadı.
