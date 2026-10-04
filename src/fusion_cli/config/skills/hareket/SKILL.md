---
name: hareket
description: Animasyonlu web sayfası, landing page, hero girişi, kaydırmayla ortaya çıkan bölümler, mikro etkileşimler. Akıcı, ölçülebilir ve erişilebilir hareket kalıpları ve çalışan kod örnekleri.
---

# Hareket (animasyonlu web) — çalışan kalıplar

Amaç: "animasyonlu" sayfanın gerçekten HAREKET ETMESİ, akıcı olması ve hareketi
azaltmak isteyen kullanıcıya saygı göstermesi. Hareket süs değil, hiyerarşiyi anlatır.

## Kurallar (hepsi zorunlu)

1. Yalnız `transform` ve `opacity` (gerekirse `clip-path`, `filter`) canlandır.
   `width/height/top/left/margin/padding` canlandırma: sayfayı yeniden dizer, takılır.
2. Easing token'ları tanımla ve EN AZ İKİ farklı eğri kullan:
   `--ease-out: cubic-bezier(.16,1,.3,1)` (giriş), `--ease-in-out: cubic-bezier(.65,0,.35,1)` (döngü).
3. Süreler 150–800 ms; sıralı girişlerde 60–120 ms gecikme (stagger).
4. `@media (prefers-reduced-motion: reduce)` bloğu ŞART: animasyonları kapat, öğeleri görünür bırak.
5. Kaydırma tetiklemesi `IntersectionObserver` ile; `scroll` olayında ağır iş yapma.
6. Sayfada en az BEŞ farklı kalıp: hero girişi, kaydırmayla ortaya çıkma, stagger kart
   girişi, hover/focus durumu, sürekli hafif hareket (marquee/float/parallax/sayaç).
7. Konsolda hata olmamalı; JS yoksa da içerik görünür kalmalı (`.js` sınıfıyla gizle).

## Çekirdek kod

```css
:root { --ease-out: cubic-bezier(.16,1,.3,1); --ease-in-out: cubic-bezier(.65,0,.35,1); }
.js .reveal { opacity: 0; transform: translateY(24px);
  transition: opacity .7s var(--ease-out), transform .7s var(--ease-out);
  transition-delay: calc(var(--i, 0) * 90ms); }
.js .reveal.is-visible { opacity: 1; transform: none; }
.hero-title { animation: hero-in .9s var(--ease-out) both; }
@keyframes hero-in { from { opacity: 0; transform: translateY(40px) scale(.98); } }
.card { transition: transform .25s var(--ease-out), box-shadow .25s var(--ease-out); }
.card:hover, .card:focus-visible { transform: translateY(-6px); }
.marquee__track { display: flex; animation: marquee 22s linear infinite; }
@keyframes marquee { to { transform: translateX(-50%); } }
.float { animation: float 6s var(--ease-in-out) infinite alternate; }
@keyframes float { to { transform: translateY(-12px); } }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
  .js .reveal { opacity: 1; transform: none; }
}
```

```js
document.documentElement.classList.add('js');
const io = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { e.target.classList.add('is-visible'); io.unobserve(e.target); }
}, { threshold: 0.15 });
document.querySelectorAll('.reveal').forEach((el, i) => { el.style.setProperty('--i', i % 6); io.observe(el); });
// Sayaç: görünür olunca hedef sayıya akar (requestAnimationFrame).
function countUp(el) { const end = +el.dataset.to, t0 = performance.now();
  (function step(t) { const p = Math.min(1, (t - t0) / 1200); el.textContent = Math.round(end * (1 - (1 - p) ** 3));
    if (p < 1) requestAnimationFrame(step); })(t0); }
```

## Kendi işini doğrula (bitti demeden önce)

- `start_preview` ile aç; konsol hatası 0 olmalı.
- Kaydırarak her bölümün göründüğünü ve sayfanın boş kalmadığını kontrol et.
- CSS'te layout özelliği canlandırılmadığını ve `prefers-reduced-motion` bloğunu kontrol et.
