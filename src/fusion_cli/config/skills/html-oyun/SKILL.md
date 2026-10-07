---
name: html-oyun
description: Tarayıcıda oynanan 2D HTML5 canvas oyunu (arcade, platform, nişancı, toplama). Oyun döngüsü, girdi, durum makinesi, HUD, yeniden başlatma ve oynanabilirliği kendi kendine doğrulama.
---

# HTML5 oyun — oynanabilir iskelet

## Zorunlu parçalar

1. Tek `<canvas>`; boyutu pencereye uyar. DPR ile: `canvas.width = innerWidth*dpr`,
   `ctx.setTransform(dpr,0,0,dpr,0,0)` (scale BİRİKTİRME), sonra her şeyi CSS piksel
   ölçüsüyle (innerWidth×innerHeight) çiz.
2. `requestAnimationFrame` döngüsü, sabit zaman adımı (dt sınırlı): `update(dt)` + `draw()`.
   `draw()` HER karede önce tüm canvas'ı zemin rengiyle boyar; yoksa nesneler iz bırakır.
   Tek dosyalı klasik `<script src>` kullan: `type="module"`/`fetch` çift tıklanan
   index.html'de (file://) engellenir.
3. Girdi: `keydown`/`keyup` ile bir `keys` kümesi tut (ok tuşları + WASD + Boşluk);
   `preventDefault` ile sayfa kaymasını engelle. Dokunmatik için basit düğmeler.
4. Durum makinesi: `menu → oynuyor → bitti`. Görünür **Başla düğmesi**, Boşluk/Enter
   aynı `start()` işlevini çağırır; düğme klavye kullanmadan tek başına oyunu başlatır.
   **R tuşu ve görünür
   "Yeniden başla" düğmesi** her durumda sıfırlar (skor, can, düşmanlar, konum).
   Geçiş/duraklama/bitiş durumunda savaş güncellemesi ÇALIŞMAZ: geçiş sayacını
   güncelledikten sonra `return`; dalga, doğma, hasar yalnız `oynuyor` durumunda.
   Sıfır dalga sayacıyla geçişten savaş mantığına düşmek bölümleri anında atlatır.
5. HUD: skor/can yüksek kontrastla ayrı bir şeritte gösterilir. Oyun sınırını HUD'ın
   gerçek alt kenarından başlat; oyuncu merkezini değil sprite'ın dış boyutunu ve
   efektini bu sınıra göre kısıtla. DPR ve yeniden boyutlandırmada sınırı güncelle;
   en üst köşelerde oyuncu, HUD yazısını örtmemeli.
6. Zorluk artar (düşman hızı/sayısı zamanla), çarpışma kutuları net.
7. Varlıklar: sprite'ları `assets/` altına SVG olarak KENDİN üret (oyuncu, her düşman,
   boss, güçlendirme, mermi, patlama, zemin dokusu); tek renk paleti, degrade, dış hat ve
   parlama ile tutarlı stil. `new Image()` ile hepsini yükle, `Promise.all` bitmeden
   oyunu başlatma. Varlık anahtarını TEK kayıttan çöz; aktör `chaser`, kayıt
   `enemy_chaser` ise açık eşleme kullan. Yanlış anahtarı şekle sessiz düşürerek gizleme.
   Dosya yüklenememesi ile kayıt/eşleme hatasını ayır ve düzelt.
8. Doğrulama kancası: `window.__GAME_STATE__ = () => ({ durum, skor, can, oyuncu: {x, y} })`.

## Kendi işini doğrula (bitti demeden önce)

- HTML'nin çağırdığı bütün CSS/JS dosyaları mevcut ve yüklenir olmalı; eksik kod
  varken yalnız menü ve görselleri tamamlandı sayma.
- Başla düğmesini Enter/Space kullanmadan gerçek tıklamayla ayrıca dene: menüden
  oynuyor durumuna geçiş ve oyuncu kontrolü görülmeli. Klavye başlangıcı bozuk
  düğmeyi örtemez.
- Sondadaki VARLIK KANITI, yükleme ve gerçek `drawImage` kaynaklarını ayırır.
  Çizimi gözlemlenmeyen düşman/boss/güçlendirme sahnesini tetikle; aktör türü-kayıt
  eşleşmesini kontrol et. İndirilmiş dosya kullanılma kanıtı, çizim çağrısı da
  görünürlük kanıtı değildir. Her türün gerçekten sprite ile çizildiğini karede gör.
  Başlangıçta henüz doğmayan boss tek başına hata değildir.
- FPS düşükse boş sayfa ve oyun hızını aynı tarayıcıda karşılaştır; ölçmeden
  "headless throttling" diye geçiştirme. Ağır SVG filtrelerini her karede yeniden
  çizmek yerine yüklemede uygun boyutlu bitmap/offscreen canvas'a önbellekle;
  düşman/parçacık sayılarını sınırlayıp bitenleri temizle. Başla sonrası tüm dalga
  geçişleri, duraklama ve bitiş boyunca oynanabilirlik korunmalı.

- `play_probe(target='index.html')` çağır: oyunu ayrı başsız tarayıcıda açar, tuşlara
  basar; konsol hatası 0, rAF ~60/sn, tuşlardan sonra oyuncu konumu belirgin değişmeli,
  R'den sonra skor/can sıfırlanmalı. Çıktıda "DEĞİŞTİRMEDİ" görürsen girdi kodunu düzelt.
  "GÖRSEL SORUN" satırları ekran görüntüsünden ölçülür (yarım ekran, iz, hareketsiz
  sahne, okunmayan HUD): hepsi düzelmeden bitti deme; kapanışta oyun yeniden oynatılır.
- Masaüstüne `osascript` ile tuş gönderme, ekran görüntüsü alıp tahmin yürütme.
