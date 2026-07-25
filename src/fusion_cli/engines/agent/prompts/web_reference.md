# Web arayüzü referansı — somut değerler

## ÖNCE BUNU YAP: scaffold_web

Web arayüzü yapmaya başlarken İLK iş `scaffold_web` aracını çağırmaktır. Aşağıdaki
ölçeklerin, biçimlendiricilerin ve doğru sıralı sayfa iskeletinin ÇALIŞAN halini diske
yazar (`tokens.css`, `format.js`, `index.html`). Var olan dosyayı ezmez.

Sonrasında kural okumana gerek kalmaz: dosyaları DOLDURURSUN. `tokens.css` ve
`format.js` yeniden yazılmaz, oldukları gibi kullanılır.

Aşağıdaki bölümler o dosyalarda ne olduğunu ve neden öyle olduğunu anlatır.

## Ölçekler — bu sayıları kullan, yenisini uydurma

```css
:root {
  /* Boşluk: 4'ün katları. Ara değer uydurma. */
  --space-1: 4px;   --space-2: 8px;   --space-3: 12px;  --space-4: 16px;
  --space-5: 24px;  --space-6: 32px;  --space-7: 48px;  --space-8: 64px;
  --space-9: 96px;  --space-10: 128px;

  /* Tipografi: akışkan ölçek. Gövde 16px'in altına inmez. */
  --text-xs:   0.75rem;                                    /* 12px, yalnız etiket */
  --text-sm:   0.875rem;                                   /* 14px, ikincil */
  --text-base: 1rem;                                       /* 16px, gövde */
  --text-lg:   1.125rem;
  --text-xl:   clamp(1.25rem, 1.1rem + 0.5vw, 1.5rem);     /* kart başlığı */
  --text-2xl:  clamp(1.5rem, 1.2rem + 1.2vw, 2rem);        /* bölüm başlığı */
  --text-hero: clamp(2rem, 1.2rem + 3.5vw, 3.5rem);        /* hero */

  --leading-tight: 1.15;   /* başlıklar */
  --leading-normal: 1.6;   /* gövde metni */

  /* Yarıçap: üç kademe yeter. */
  --radius-sm: 6px;  --radius-md: 12px;  --radius-lg: 20px;  --radius-full: 999px;

  /* Gölge: üç kademe. Hepsi düşük opaklık; ağır gölge ucuz durur. */
  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.04), 0 1px 3px rgb(0 0 0 / 0.06);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.06), 0 2px 4px -2px rgb(0 0 0 / 0.06);
  --shadow-lg: 0 12px 24px -8px rgb(0 0 0 / 0.12);

  --ease: cubic-bezier(0.2, 0, 0, 1);
  --dur: 180ms;
}
```

## Renk disiplini

- Marka renklerini `:root`'a koy ve **her yerde `var()` ile kullan**. Bileşenin içinde
  ikinci bir hex yazma; JavaScript'le üretilen markup da `var()` kullanmalıdır.
- Nötrler ayrı bir ölçek: `#ffffff`, `#f6f7f9`, `#e5e7eb`, `#9ca3af`, `#4b5563`, `#111827`.
  Gri tonlarını marka renginden türetme.
- Gövde metni ile arka plan arasında **en az 4.5:1** kontrast, büyük başlıkta 3:1.
- Bir yüzeyde en fazla iki marka rengi. Aksan rengi yalnızca eylem çağrısında.
- Gradyan kullanacaksan **komşu tonlar** arasında kal. Zıt renkler (lacivert→turuncu)
  ortada çamur üretir; iki durak yerine tek renk + doku daha temizdir.

## Düzen

```css
.container { width: min(100% - 2 * var(--space-5), 1200px); margin-inline: auto; }

/* Kart ızgarası: sabit sütun sayısı YAZMA, otomatik sığdır.
   Sabit sütun 6 öğede 5+1 gibi yetim satır bırakır. */
.grid { display: grid; gap: var(--space-5);
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
```

- Sticky header yüksekliği 56–72px; `position: sticky; top: 0; z-index: 50`.
  İçeriğin altına kaymaması için `scroll-margin-top` ver.
- Bölüm dikey boşluğu: `padding-block: clamp(48px, 6vw, 96px)`.
- Yatay kaydırma ASLA olmamalı. Uzun içerik sarmalanır (`flex-wrap: wrap`) ya da
  kapsayıcıya `overflow-x: auto` verilir — kırpılmış içerik erişilemez içeriktir.

## Bileşen ölçüleri

| Öğe | Değer |
|---|---|
| Buton yüksekliği | 40px (küçük 32px, büyük 48px) |
| Buton iç boşluğu | `0 var(--space-5)`, yarıçap `--radius-md` |
| Girdi/select yüksekliği | 40px, kenarlık 1px, odakta 2px halka |
| **İkon boyutu** | **16px / 20px / 24px — SVG'ye HER ZAMAN `width` ve `height` ver** |
| Tıklanabilir alan | en az 24×24px, mobilde 44×44px hedefle |
| Kart iç boşluğu | `var(--space-5)`, yarıçap `--radius-md`, gölge `--shadow-sm` |
| Ürün görseli oranı | `aspect-ratio: 1 / 1` veya `4 / 3`, `object-fit: cover` |

## Durumlar — hepsini yaz

Her etkileşimli öğe için dört durum tanımla: `:hover`, `:focus-visible`, `:active`,
`:disabled`. Odak halkası görünür olmalı (`outline: 2px solid; outline-offset: 2px`);
`outline: none` yazıp yerine bir şey koymamak erişilebilirliği kırar.

```css
.btn { transition: background-color var(--dur) var(--ease), transform var(--dur) var(--ease); }
.btn:hover { background: var(--brand-dark); }
.btn:active { transform: translateY(1px); }
.btn:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { * { transition-duration: 1ms !important; } }
```

## Görseller

Ağdaki placeholder servislerine (via.placeholder.com, placehold.it, lorempixel.com)
GÜVENME — kapandılar, sayfa kırık açılır. Yer tutucu gerekiyorsa inline SVG data URI
üret ve **okunur** olsun: düz bir zemin + ortada büyük etiket, 12px'lik gri yazı değil.

```html
<img width="400" height="400" alt="Ürün adı"
     src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'%3E%3Crect width='400' height='400' fill='%23e5e7eb'/%3E%3Ctext x='200' y='210' font-family='sans-serif' font-size='28' fill='%236b7280' text-anchor='middle'%3EÜrün%3C/text%3E%3C/svg%3E">
```

Her `<img>` etiketine `width`, `height` ve anlamlı `alt` ver; boyutsuz görsel hem
düzen kaymasına hem devasa render'a yol açar.

## Metin ve biçimlendirme

Arayüz dili Türkçe ise **tarih, para ve sayı da Türkçe biçimlenir**:
`toLocaleDateString('tr-TR')`, `toLocaleString('tr-TR')`. İngilizce ay adı ("15 May")
sızıntıdır. Sayfada verilen söz (ör. "2.000 TL üzeri ücretsiz kargo") koddaki eşikle
birebir aynı olmalıdır.

## Bunları yapma

- Boş bağlantı (`href="#"`). Hedefi yoksa `<button>` kullan.
- Tek sütunlu ortalanmış hero + üç kart + footer: en jenerik düzendir. Bölümlerden
  en az birinde ritmi kır (asimetrik ızgara, geniş görsel, farklı zemin).
- Her bölüme aynı `padding` ve aynı gölgeyi vermek. Hiyerarşi ölçekten doğar.
- `<div>` yığını. `header`, `nav`, `main`, `section`, `footer` kullan; sayfada tam
  bir `<main>` bulunmalı.

## Çalışan örnek — bunları taklit et

Aşağıdaki parçalar yukarıdaki ölçekleri kullanır. Yapıyı kopyala, içeriği projeye uyarla.

### Sticky header + ikon butonları

İkonun boyutu HER ZAMAN `<svg>` üzerinde yazılır; yoksa devasa render edilir.

```html
<header class="site-header">
  <div class="container header__inner">
    <a class="logo" href="/">Marka</a>
    <nav aria-label="Ana menü"><a href="/kategoriler">Kategoriler</a></nav>
    <div class="header__actions">
      <button class="icon-btn" aria-label="Sepet">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" aria-hidden="true"><path d="M6 6h15l-1.5 9h-12z"/></svg>
        <span class="badge">0</span>
      </button>
    </div>
  </div>
</header>
```

```css
.site-header { position: sticky; top: 0; z-index: 50; background: var(--white);
               border-bottom: 1px solid var(--gray-200); }
.header__inner { display: flex; align-items: center; gap: var(--space-5); height: 64px; }
.header__actions { margin-left: auto; display: flex; gap: var(--space-2); }
.icon-btn { position: relative; width: 40px; height: 40px; display: grid;
            place-items: center; border: 0; background: none; border-radius: var(--radius-md); }
.icon-btn:hover { background: var(--gray-100); }
.badge { position: absolute; top: 2px; right: 2px; min-width: 18px; height: 18px;
         display: grid; place-items: center; font-size: 11px; border-radius: var(--radius-full);
         background: var(--accent); color: var(--white); }
```

### Ürün kartı

Fiyat hiyerarşisi: güncel fiyat büyük ve koyu, eski fiyat küçük ve üstü çizili.

```html
<article class="card">
  <div class="card__media">
    <img src="…" alt="Ürün adı" width="400" height="400" loading="lazy">
    <span class="card__badge">%25</span>
  </div>
  <div class="card__body">
    <p class="card__kicker">Kategori</p>
    <h3 class="card__title">Ürün adı</h3>
    <p class="card__price"><s>19.999 TL</s> <strong>14.999 TL</strong></p>
    <div class="card__actions">
      <button class="btn btn--primary">Sepete Ekle</button>
      <button class="icon-btn" aria-label="Favorilere ekle">
        <svg width="20" height="20" …></svg>
      </button>
    </div>
  </div>
</article>
```

```css
.card { display: flex; flex-direction: column; background: var(--white);
        border: 1px solid var(--gray-200); border-radius: var(--radius-md);
        overflow: hidden; transition: box-shadow var(--dur) var(--ease); }
.card:hover { box-shadow: var(--shadow-md); }
.card__media { position: relative; aspect-ratio: 1; background: var(--gray-100); }
.card__media img { width: 100%; height: 100%; object-fit: cover; display: block; }
.card__badge { position: absolute; top: var(--space-3); left: var(--space-3);
               padding: 2px var(--space-2); border-radius: var(--radius-sm);
               background: var(--accent); color: var(--white); font-size: var(--text-xs); }
.card__body { padding: var(--space-5); display: grid; gap: var(--space-2); }
.card__kicker { font-size: var(--text-xs); color: var(--gray-500);
                text-transform: uppercase; letter-spacing: 0.04em; }
.card__title { font-size: var(--text-lg); line-height: var(--leading-tight); }
.card__price s { font-size: var(--text-sm); color: var(--gray-500); }
.card__price strong { font-size: var(--text-xl); color: var(--brand); }
.card__actions { display: flex; gap: var(--space-2); align-items: center; }
.card__actions .btn { flex: 1; }
```

### Bölüm kabuğu

```html
<section class="section" id="cok-satanlar" aria-labelledby="cok-satanlar-h">
  <div class="container">
    <header class="section__head">
      <h2 id="cok-satanlar-h">Çok Satanlar</h2>
      <a class="link" href="/urunler">Tümünü gör</a>
    </header>
    <div class="grid"><!-- kartlar --></div>
  </div>
</section>
```

```css
.section { padding-block: clamp(48px, 6vw, 96px); }
.section:nth-of-type(even) { background: var(--gray-50); }  /* ritim: zemin değişimi */
.section__head { display: flex; align-items: baseline; justify-content: space-between;
                 gap: var(--space-4); margin-bottom: var(--space-6); }
```

## JavaScript ile içerik üretiyorsan

- Üretilen markup da `var(--…)` kullanır; şablon dizesine hex renk gömme.
- `init()`'i **tanımladığın gibi çağır** ve `DOMContentLoaded`'a bağla; çağrılmayan
  render fonksiyonu = boş bölüm.
- HTML'e `<script src="…">` etiketini eklemeyi UNUTMA. Dosyayı yeniden yazarken en sık
  düşen şey budur ve sayfa sessizce boşalır — konsolda hata bile çıkmaz.
- Bir bölümü JS dolduruyorsa, HTML'de o bölümün kapsayıcısı ve `id`'si bulunmalıdır.

## İkonlar — path verisini UYDURMA, buradan kopyala

Ölçüldü: model SVG `d` verisini ezberden yazmaya çalışıyor ve bozuk şekiller çıkıyor
(sepet ikonu tanınmaz hale geliyor). Aşağıdakiler doğrulanmış Feather/Lucide
verileridir. Hepsi `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`,
`stroke-width="2"`, `stroke-linecap="round"`, `stroke-linejoin="round"` ile kullanılır.

```html
<!-- Kalıp: boyutu HER ZAMAN yaz -->
<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
     stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <!-- ↓ aşağıdaki gövdelerden birini koy -->
</svg>
```

| İkon | Gövde |
|---|---|
| arama | `<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>` |
| sepet | `<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/>` |
| kalp (favori) | `<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>` |
| kullanıcı | `<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>` |
| menü | `<line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="18" y2="18"/>` |
| kapat | `<path d="M18 6 6 18"/><path d="m6 6 12 12"/>` |
| yıldız (dolu) | `fill="currentColor"` ile: `<path d="M11.5 2.9a.5.5 0 0 1 1 0l2.2 4.5 4.9.7a.5.5 0 0 1 .3.9l-3.6 3.5.9 4.9a.5.5 0 0 1-.8.5L12 15.6l-4.4 2.3a.5.5 0 0 1-.8-.5l.9-4.9-3.6-3.5a.5.5 0 0 1 .3-.9l4.9-.7Z"/>` |
| kargo/kamyon | `<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/>` |
| kalkan (güvenlik) | `<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1Z"/>` |
| iade/geri | `<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>` |
| onay | `<path d="M20 6 9 17l-5-5"/>` |
| çöp (sil) | `<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>` |
| artı / eksi | `<path d="M5 12h14"/><path d="M12 5v14"/>` &nbsp;/&nbsp; `<path d="M5 12h14"/>` |
| ok sağ | `<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>` |
| e-posta | `<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>` |
| telefon | `<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92Z"/>` |

Bu listede olmayan bir ikon gerekirse: ya listeden anlamca en yakınını kullan ya da
metinle çöz. **Path verisi uydurma** — bozuk şekil, ikonsuzluktan kötüdür.

Ağdan ikon kütüphanesi (Font Awesome, Bootstrap Icons, Material Icons) `<link>`
etmeden sınıf adı yazma: sınıf yazıp kütüphaneyi yüklememek sayfayı boş kare
kutularla doldurur — ölçülen gerçek bir hata.

## Sayfa kurgusu — bölümlerin sırası rastgele değildir

Bir açılış sayfası bir ikna sırası (funnel) izler: **dikkat → değer → kanıt → eylem**.
Bölümleri bu sıraya oturt; sıra bozulursa sayfa "parça yığını" gibi durur.

**E-ticaret ana sayfası**
1. Duyuru çubuğu (kargo/iade/ödeme güveni) — ince, tek satır
2. Header (logo, menü, arama, hesap/favori/sepet)
3. Hero — tek net vaat + iki buton (birincil dolu, ikincil çerçeveli)
4. Kategoriler — gezinme, kartlardan önce
5. Öne çıkan ürünler — asıl ticari içerik, sayfanın merkezi
6. Kampanya bandı — ritmi kırar, farklı zemin
7. Güven blokları (garanti, güvenli ödeme, hızlı teslimat, kolay iade)
8. Müşteri yorumları — sosyal kanıt, eylemden hemen önce
9. Bülten — tek alan + tek buton
10. Footer — kurumsal, hizmet, yasal, iletişim, ödeme yöntemleri

**SaaS / ürün açılış sayfası**
Header → Hero (vaat + CTA) → sosyal kanıt şeridi (logolar) → problem/çözüm →
özellikler (3-6) → nasıl çalışır (3 adım) → fiyatlandırma → SSS → son CTA → footer

**Uygulama arayüzü (dashboard)**
Kenar çubuğu (birincil gezinme) + üst çubuk (bağlam, arama, hesap) →
özet metrikler (üstte, 3-4 kart) → asıl tablo/grafik → ikincil paneller.
Pazarlama hero'su KOYMA; ilk ekranda iş yapılır.

Kurallar:
- **Sayfada tek birincil eylem vardır.** Her bölüme dolu turuncu buton koyma; ikincil
  eylemler çerçeveli ya da bağlantı olur.
- Yorum ve güven blokları eylemden ÖNCE gelir, sonra değil.
- Ardışık iki bölüm aynı zeminde olmaz; `--white` ve `--gray-50` dönüşümlü kullan.
- Bir bölüm tek cümlelik içerikse ayrı bölüm olmayı hak etmiyordur; birleştir.

## Dikey ritim — boşluk göz kararı değildir

| Yer | Değer |
|---|---|
| Bölümler arası (`padding-block`) | `clamp(48px, 6vw, 96px)` |
| Bölüm başlığı ile içeriği arası | `var(--space-6)` = 32px |
| Kartlar arası (`gap`) | `var(--space-5)` = 24px |
| Kart içinde satırlar arası | `var(--space-2)` = 8px |
| Başlık ile alt metni arası | `var(--space-3)` = 12px |
| Buton grubu (`gap`) | `var(--space-3)` = 12px |
| Form alanları arası | `var(--space-4)` = 16px |
| Sayfa yan boşluğu | `var(--space-5)`, geniş ekranda `container` sınırlar |

- Ölçek DIŞINDA değer yazma (13px, 17px, 42px gibi). Ara değer gerekiyorsa ölçeği
  gözden geçir, uydurma.
- Boşluğu `margin` yerine kapsayıcıda `gap` ile ver; çift boşluk (margin+gap)
  ritmi bozar.
- Aynı hiyerarşideki her bölüm aynı dikey boşluğu alır. Bir bölümü öne çıkarmak
  istiyorsan boşlukla değil zeminle, ölçekle ya da genişlikle çıkar.

### Footer — çok sütunlu bağlantı bloğu

Ölçülen gerçek hata: model tüm bağlantı gruplarını TEK bir `<div>` içine koydu; o sütun
1109px'e uzadı, footer 1237px oldu (ekranın %137'si) ve telif satırı ortada asılı kaldı.
Her grup AYRI bir grid öğesidir; telif satırı grid'in DIŞINDA, tam genişlikte durur.

```html
<footer class="site-footer">
  <div class="container footer__grid">
    <div class="footer__brand">
      <h3>Marka</h3>
      <p>Tek cümlelik tanım.</p>
    </div>
    <!-- HER GRUP AYRI <nav>: tek div içine yığma -->
    <nav class="footer__col" aria-label="Kurumsal">
      <h4>Kurumsal</h4>
      <ul><li><a href="/hakkimizda">Hakkımızda</a></li><li><a href="/kariyer">Kariyer</a></li></ul>
    </nav>
    <nav class="footer__col" aria-label="Müşteri Hizmetleri">
      <h4>Müşteri Hizmetleri</h4>
      <ul><li><a href="/sss">SSS</a></li><li><a href="/iletisim">İletişim</a></li></ul>
    </nav>
    <nav class="footer__col" aria-label="Yasal">
      <h4>Yasal</h4>
      <ul><li><a href="/gizlilik">Gizlilik</a></li><li><a href="/kosullar">Koşullar</a></li></ul>
    </nav>
  </div>
  <!-- Telif: grid'in DIŞINDA, tam genişlik -->
  <div class="container footer__bottom">
    <small>© 2026 Marka. Tüm hakları saklıdır.</small>
    <ul class="footer__pay"><li>Visa</li><li>Mastercard</li></ul>
  </div>
</footer>
```

```css
.site-footer { background: var(--navy); color: #fff; padding-block: var(--space-8) var(--space-5); }
.footer__grid { display: grid; gap: var(--space-6);
                grid-template-columns: 2fr repeat(3, 1fr); align-items: start; }
.footer__col h4 { font-size: var(--text-base); margin-bottom: var(--space-3); }
.footer__col ul { list-style: none; display: grid; gap: var(--space-2); }
.footer__bottom { display: flex; justify-content: space-between; align-items: center;
                  gap: var(--space-4); flex-wrap: wrap;
                  margin-top: var(--space-6); padding-top: var(--space-5);
                  border-top: 1px solid rgb(255 255 255 / 0.12); }
@media (max-width: 768px) { .footer__grid { grid-template-columns: 1fr 1fr; } }
```

Kurallar:
- `align-items: start` ZORUNLU. Varsayılan `stretch` tüm sütunları en uzun sütun
  kadar uzatır ve footer devasa görünür.
- Bağlantı grubu 6'yı geçmesin; geçiyorsa grupları birleştir. Footer bir site
  haritası değildir.
- Footer yüksekliği ekran yüksekliğini AŞMAMALI. Aşıyorsa yapı yanlıştır.

### Para biçimlendirme — bölme yapma

Ölçülen gerçek hata: veri `price: 14999` (yani 14.999 TL) iken model
`(price / 100)` yazdı ve sayfada **₺149,99** göründü — sekiz ürünün fiyatı da 100 kat
yanlış çıktı, sayfa kusursuz görünüyordu.

Fiyatı ANA BİRİMDE (TL) sakla ve olduğu gibi biçimlendir:

```js
const tl = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY',
                                            minimumFractionDigits: 0 });
tl.format(14999);   // "₺14.999"   ✅
tl.format(14999/100); // "₺149,99"  ❌ kuruş varsayımı — YAPMA
```

Veriyi kuruş cinsinden saklıyorsan bunu alan adında belirt (`priceKurus`) ve tek yerde
çevir. Bir kez yazdıktan sonra ekrandaki ilk fiyatın şartnamedeki değerle aynı
olduğunu GÖZLE doğrula.
