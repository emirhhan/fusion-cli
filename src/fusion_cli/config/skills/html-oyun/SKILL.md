---
name: html-oyun
description: Tarayıcıda oynanan 2D HTML5 canvas oyunu (arcade, platform, nişancı, toplama). Oyun döngüsü, girdi, durum makinesi, HUD, yeniden başlatma ve oynanabilirliği kendi kendine doğrulama.
---

# HTML5 oyun — oynanabilir iskelet

"Çalışıyor" ile "oynanabilir" farklıdır: sayfa açılır ama tuşlara tepki vermiyorsa ya
da oyun bittiğinde yeniden başlamıyorsa oyun bitmemiştir.

## Zorunlu parçalar

1. Tek `<canvas>`; boyutu pencereye uyar. DPR ile: `canvas.width = innerWidth*dpr`,
   `ctx.setTransform(dpr,0,0,dpr,0,0)` (scale BİRİKTİRME), sonra her şeyi CSS piksel
   ölçüsüyle (innerWidth×innerHeight) çiz — yoksa oyun ekranın bir köşesinde kalır.
2. `requestAnimationFrame` döngüsü, sabit zaman adımı (dt sınırlı): `update(dt)` + `draw()`.
   `draw()` HER karede önce tüm canvas'ı zemin rengiyle boyar; yoksa nesneler iz bırakır.
   Tek dosyalı klasik `<script src>` kullan: `type="module"`/`fetch` çift tıklanan
   index.html'de (file://) engellenir ve oyun hiç açılmaz.
3. Girdi: `keydown`/`keyup` ile bir `keys` kümesi tut (ok tuşları + WASD + Boşluk);
   `preventDefault` ile sayfa kaymasını engelle. Dokunmatik için basit düğmeler.
4. Durum makinesi: `menu → oynuyor → bitti`. Görünür **Başla düğmesi**, Boşluk/Enter
   aynı `start()` işlevini çağırır; düğme klavye kullanmadan tek başına oyunu başlatır.
   **R tuşu ve görünür
   "Yeniden başla" düğmesi** her durumda sıfırlar (skor, can, düşmanlar, konum).
5. HUD: skor ve can her karede çizilir (`fillText`) ya da DOM'da gösterilir.
6. Zorluk artar (düşman hızı/sayısı zamanla), çarpışma kutuları net.
7. Varlıklar: sprite'ları `assets/` altına SVG olarak KENDİN üret (oyuncu, her düşman,
   boss, güçlendirme, mermi, patlama, zemin dokusu); tek renk paleti, degrade, dış hat ve
   parlama ile tutarlı stil. `new Image()` ile hepsini yükle, `Promise.all` bitmeden
   oyunu başlatma; yüklenemezse şekle düş (konsol hatası bırakma).
   HUD yazısı zeminle yüksek kontrastlı olsun (açık zeminde koyu, koyu zeminde açık).
8. Doğrulama kancası: `window.__GAME_STATE__ = () => ({ durum, skor, can, oyuncu: {x, y} })`.

## Çekirdek

```js
const keys = new Set();
addEventListener('keydown', (e) => { if (['ArrowUp','ArrowDown','ArrowLeft','ArrowRight',' '].includes(e.key)) e.preventDefault();
  keys.add(e.key.toLowerCase()); if (e.key.toLowerCase() === 'r') reset(); if (state.mode !== 'oynuyor' && (e.key === ' ' || e.key === 'Enter')) start(); });
addEventListener('keyup', (e) => keys.delete(e.key.toLowerCase()));
let last = performance.now();
function frame(t) { const dt = Math.min(0.033, (t - last) / 1000); last = t;
  if (state.mode === 'oynuyor') update(dt); draw(); requestAnimationFrame(frame); }
requestAnimationFrame(frame);
window.__GAME_STATE__ = () => ({ durum: state.mode, skor: state.score, can: state.lives, oyuncu: { x: state.p.x, y: state.p.y } });
```

## Kendi işini doğrula (bitti demeden önce)

- HTML'nin çağırdığı bütün CSS/JS dosyaları mevcut ve yüklenir olmalı. Yalnız menü
  ve görselleri yazıp tamamlandı deme; oyunun kodu eksikse teslim tamamlanmamıştır.
- Başla düğmesini Enter/Space kullanmadan gerçek tıklamayla ayrıca dene: menüden
  oynuyor durumuna geçiş ve oyuncu kontrolü görülmeli. Klavye başlangıcı bozuk
  düğmeyi örtemez; `play_probe` bunu ayrı bir BAŞLATMA SORUNU olarak bildirir.

- `play_probe(target='index.html')` çağır: oyunu ayrı başsız tarayıcıda açar, tuşlara
  basar; konsol hatası 0, rAF ~60/sn, tuşlardan sonra oyuncu konumu belirgin değişmeli,
  R'den sonra skor/can sıfırlanmalı. Çıktıda "DEĞİŞTİRMEDİ" görürsen girdi kodunu düzelt.
  "GÖRSEL SORUN" satırları ekran görüntüsünden ölçülür (yarım ekran, iz, hareketsiz
  sahne, okunmayan HUD): hepsi düzelmeden bitti deme; kapanışta oyun yeniden oynatılır.
- Masaüstüne `osascript` ile tuş gönderme, ekran görüntüsü alıp tahmin yürütme.
