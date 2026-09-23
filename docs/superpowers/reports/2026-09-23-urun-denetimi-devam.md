# Fusion ürün denetimi — 23 Eylül 2026

## Bu oturumda doğrulananlar

- Terminal panelinin yüksekliği sınırlandı. Kurulu uygulamada PTY açıldı, komut
  çalıştı ve önceki sürekli yeniden boyutlandırma döngüsü görülmedi.
- Konuşma yeni yanıtta alta kayıyor; kullanıcı geçmişi okurken zorla kaydırılmıyor.
- Ayarlar sekmeleri arasında başlık ve Kapat düğmesi sabit kaldı.
- İzin kartları doğrudan seçilebilir düğmelere dönüştü; her kart ilgili çalışma
  modu komutunu kullanıyor.
- Dar denetçide web önizleme araç çubuğu iki satıra yerleşti; adres alanı ve
  diğer kontroller panel dışına taşmadı.
- Doğrulama isteyen sağlayıcının devresi aynı oturumda yeniden denenmeden
  açık kalıyor. Devresi açık birincil model, katı zincirde yedeği kilitlemiyor.
- NIM Ultra profili kullanıcı uygulamasında seçildi; yeni bir görevde basit
  soruya doğru yanıt döndü. Yanıt süresi birkaç dakika olduğundan hız sorunu
  açık bulgudur.
- Gerçek görev yürütmesinde korumalı dosya düzenleme kabul testini geçti.
- Godot değerlendirmesinde gerçek PNG ve kaynak/lisans kaydı üretildi. Asset
  doğrulayıcıya `assets` listesi ve kök listedeki `file` yolu desteği eklendi;
  kabul ölçütü PNG bütünlüğünü ve lisans kaydını ürünün kendi denetimiyle
  kontrol ediyor.
- MCP duman testi `ping` aracını listeleyip çalıştırdı; ilk kabul ölçütü istekte
  bulunmayan `call()` fonksiyonunu aradığı için üç geçerli çıktıyı reddetti.
  Ölçüt artık betiği çalıştırıp çıkış kodunu ve `ping`/`pong` çıktısını inceliyor.
- Web oturumu tarafından sarılan doğrulama hatası ve açık Chrome profili,
  yeniden denenecek görev hatası yerine sağlayıcı kullanılamazlığı olarak
  sınıflandırılıyor.

## Kalite kanıtı

- `ruff check .` ve `mypy`: temiz.
- `python -m pytest -q`: başarılı.
- Frontend: 683 test başarılı; TypeScript ve Vite build başarılı.
- Rust: format, Clippy ve testler başarılı (74 test, 3 kasıtlı atlanan).
- macOS app/dmg paketi üretildi; imza ve paket içi çalışma testi doğrulandı.
- Güncel paket `/Applications/Fusion.app` konumuna kuruldu ve yeniden açıldı.
  Kurulu uygulamada terminal, ayarlar, izinler ve web önizlemesi görsel olarak
  denetlendi.

## Açık ürün işleri

1. NIM Ultra ile basit görevin birkaç dakika sürmesinin nedenini model çağrısı,
   araç turu ve ilk çalışma alanı hazırlığı olarak ayrı ayrı ölçmek.
2. Görsel oluştur ve video oluştur gezintileri hâlen işlevsiz boş ekran açıyor.
3. Fusion motoru tek aday seçildiğinde çok modelli değerlendirme yapamıyor;
   arayüz bu durumu açıkça bildirmeli ve çok adaylı profile dönüş sağlamalı.
4. Fusion'ın kendi deposunda değişiklik yapması, GATE HOLDING benzeri tarayıcı
   işi, reklam kontrolü ve otomasyon için ayrı uçtan uca kabul koşuları henüz
   tamamlanmadı.
5. Tek sayfalık web üretimi yapısal ölçütü geçti, fakat 429,91 saniye sürdü;
   90 saniyelik üretim süre eşiğini kaçırdı. Ekran görüntüsünde düzen mobilde
   taşmıyor, ancak metin jenerik ve örnek iletişim bilgileri içeriyor. Bu çıktı
   yayınlanabilir profesyonel site olarak kabul edilmedi.

## Üretim değerlendirmesi

İlk tam koşu 15 örneğin 11'ini geçirdi; katı görev güvenilirliği %60,
`false_success_count=2` idi. Çıktılar incelendiğinde üç MCP örneği de istenen
betiği doğru çalıştırmış, fakat ölçüt görevde istenmeyen `call()` işlevini
aramıştı. Godot'un kalan bir örneği de gerçek PNG ve geçerli lisansı kök JSON
listesinde kaydetmişti; doğrulayıcı bu biçimi tanımıyordu. Her iki ölçüm kusuru
düzeltildi; aynı saklanan örnekler yeni kontrollerle 15/15 geçti.

Güncel ölçütle ikinci bağımsız tam koşu **15/15 geçti**: katı görev güvenilirliği
%100, yanlış başarı 0, ortalama görev süresi 85,96 saniye. Dört üretim kabul
eşiği de geçti. Makine tarafından okunabilir rapor:
`/tmp/fusion-production-20260923-v3.json`. Bu sonuç yalnız bu beş görev
ailesinin ölçümüdür; açık işlerdeki geniş ürün vaadini kanıtlamaz.

## Web üretimi gözlemi

İzole B2B tanıtım sitesi görevi `index.html` ve `style.css` üretti; başlık,
ürün/hizmet bölümleri, iletişim çağrısı ve mobil medya sorguları mevcut.
Chromium'da 1440 px ve 390 px genişliklerde açıldı; JavaScript hatası ve yatay
taşma görülmedi. Site, 16 model çağrısı ve 429,91 saniye gerektirdi. Örnek
iletişim adresi, jenerik içerik ve dil tutarsızlığı insan düzenlemesi gerektiriyor.
Yapısal testin geçmesi profesyonel yayın kalitesinin kanıtı değildir. Rapor:
`/tmp/fusion-site-acceptance-20260923.json`.

Bu bulgular tamamlanmadan ürünün Claude düzeyinde bütün işleri yaptığı sonucu
çıkarılamaz.
