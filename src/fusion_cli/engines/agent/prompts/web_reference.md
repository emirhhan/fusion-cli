# Web arayüzü referansı — somut değerler

Bu referans WEBSITE görevlerinde otomatik yüklenir. Amacı estetik öğüt vermek değil,
KOPYALANABİLİR değer vermek. "İyi tipografi kullan" bir modele hiçbir şey söylemez;
aşağıdaki ölçekler söyler.

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
