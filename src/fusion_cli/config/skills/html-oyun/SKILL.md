---
name: html-oyun
description: HTML5 canvas oyununu üret ve gerçek oynanabilirliğini doğrula.
---

# HTML5 oyun — oynanabilir iskelet

## Zorunlu parçalar

1. Tek responsive canvas; DPR ile boyutlandır, `setTransform(dpr,0,0,dpr,0,0)`
   kullan (scale biriktirme), çizimi CSS pikseliyle yap.
2. `requestAnimationFrame` döngüsü, sabit zaman adımı (dt sınırlı): `update(dt)` + `draw()`.
   `draw()` HER karede önce tüm canvas'ı zemin rengiyle boyar; yoksa nesneler iz bırakır.
   Tek dosyalı klasik `<script src>` kullan: `type="module"`/`fetch` çift tıklanan
   index.html'de (file://) engellenir.
3. `keydown`/`keyup` keys kümesi: oklar/WASD/Boşluk; `preventDefault` ile
   kaymayı engelle, dokunmatik düğmeler ekle.
4. Durum makinesi: `menu → oynuyor → bitti`. Görünür **Başla düğmesi**, Boşluk/Enter
   aynı `start()` işlevini çağırır; düğme klavye kullanmadan tek başına oyunu başlatır.
   **R ve görünür "Yeniden başla"** skor/can/düşman/konumu sıfırlar.
   Geçiş/duraklama/bitiş durumunda savaş güncellemesi ÇALIŞMAZ: geçiş sayacını
   güncelledikten sonra `return`; dalga, doğma, hasar yalnız `oynuyor` durumunda.
   Sıfır dalga sayacıyla geçişten savaş mantığına düşmek bölümleri anında atlatır.
5. HUD: skor/can yüksek kontrastla ayrı bir şeritte gösterilir. Oyun sınırını HUD'ın
   gerçek alt kenarından başlat; oyuncu merkezini değil sprite'ın dış boyutunu ve
   efektini bu sınıra göre kısıtla. DPR ve yeniden boyutlandırmada sınırı güncelle;
   en üst köşelerde oyuncu, HUD yazısını örtmemeli.
6. Dalga yaşam döngüsü: doğan her aktör tek kayıtta `alive → resolved` olur.
   Ölüm/kaçış aynı idempotent çözümden geçer; kaçışı can kaybı/temizleme/geri giriş
   olarak tanımla. Geri giriş süre/konumla sınırlı olsun; kaçan dalgayı kilitlemesin.
   Kalan sayısını canlı kayıttan türet; ayrı sayaç varsa kayıtla her kare doğrula.
   Bölünmede ebeveyni bir kez çöz, çocukları yeni kayıtlarla ekle; restart kayıt ve
   sayaçları birlikte temizler. Öldürme ve kaçış aynı karede iki kez sayılmamalı.
7. Zorluk artar (düşman hızı/sayısı zamanla), çarpışma kutuları net.
8. Varlıklar: sprite'ları `assets/` altında SVG üret: oyuncu/düşman/boss/güçlendirme/
   mermi/patlama/zemin, tutarlı palet ve stil. `new Image()` ile hepsini yükle, `Promise.all` bitmeden
   oyunu başlatma. Varlık anahtarını TEK kayıttan çöz; aktör `chaser`, kayıt
   `enemy_chaser` ise açık eşleme kullan. Yanlış anahtarı şekle sessiz düşürerek gizleme.
   Dosya yüklenememesi ile kayıt/eşleme hatasını ayır ve düzelt.
9. Doğrulama kancası: `window.__GAME_STATE__ = () => ({ durum, skor, can, oyuncu: {x, y} })`.

## Kendi işini doğrula (bitti demeden önce)

- HTML'nin çağırdığı bütün CSS/JS dosyaları mevcut ve yüklenir olmalı; eksik kod
  varken yalnız menü ve görselleri tamamlandı sayma.
- Başla düğmesini Enter/Space kullanmadan gerçek tıklamayla ayrıca dene: menüden
  oynuyor durumuna geçiş ve oyuncu kontrolü görülmeli. Klavye başlangıcı bozuk
  düğmeyi örtemez.
- Sondadaki VARLIK KANITI, yükleme ve gerçek `drawImage` kaynaklarını ayırır.
  İlgili sahneyi tetikleyip sprite eşleşmesini karede gör. Yükleme kullanım,
  çizim çağrısı görünürlük kanıtı değildir; henüz doğmayan boss hata sayılmaz.
- Bir düşmanı ateş etmeden kaçır; tanımlı kaçış politikasının çalıştığını ve
  sonraki dalgaya geçilebildiğini doğrula. Bölünme, çift çözüm ve restart sonrası
  canlı/kalan sayısı tutarlı olmalı; yalnız öldürerek oynama bu açığı gizler.
- FPS düşükse boş sayfa ve oyun hızını aynı tarayıcıda karşılaştır; ölçmeden
  "headless throttling" deme. SVG filtrelerini bitmap/offscreen canvas'a önbellekle;
  düşman/parçacıkları sınırla ve bitenleri temizle; geçiş/pause/bitişi oyna.

- `play_probe(target='index.html')` çağır: oyunu ayrı başsız tarayıcıda açar, tuşlara
  basar: konsol 0, rAF ~60/sn, hareket belirgin, R sıfırlar.
  "DEĞİŞTİRMEDİ" varsa girdiyi düzelt.
  "GÖRSEL SORUN" ölçümünü ve kareleri incele; kapanışta yeniden oynat.
- Masaüstüne `osascript` ile tuş gönderme, ekran görüntüsü alıp tahmin yürütme.
