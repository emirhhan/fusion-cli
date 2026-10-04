"""Çok sayfalı denetim: hangi iç sayfalar açılsın ve sayfalar birbirine göre tutarlı mı?

Tarayıcı kapısı eskiden yalnız ana sayfaya (ya da düz HTML dosyalarına) bakıyordu.
Ölçüldü (4 Ekim 2026, site kopyası kabul koşusu): ana sayfa iyi görünüyordu ama
mağaza, ürün ve sepet sayfaları tarayıcı varsayılanı mavi bağlantılarla ve stilsiz
düğmelerle kaldı; ana sayfadaki ürün şeridinde görseller kutularının dörtte birine
büzülmüştü. Kapı bunları görmediği için model işi "bitti" ilan etti.

Bu modül iki şey yapar, ikisi de siteden bağımsızdır:

- `pick_audit_pages`: ana sayfadaki iç bağlantılardan FARKLI ŞABLONLARI temsil eden
  birkaç sayfa seçer (aynı türden on ürün sayfası yerine bir ürün, bir liste, bir sepet).
- `consistency_findings`: her sayfanın ölçülen stil imzasını ana sayfayla karşılaştırır.
  Ana sayfada olmayan tarayıcı varsayılanları (Times yazı tipi, #0000EE bağlantı,
  gri sistem düğmesi) iç sayfada görünüyorsa o sayfa stilsiz kalmıştır.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

#: Ana sayfanın yanında açılacak en fazla iç sayfa. Her sayfa birkaç genişlikte
#: yüklenir; kapı turu dakikalarca bekletmemeli.
MAX_AUDIT_PAGES = 4
#: Tarayıcının stilsiz bağlantı rengi (CSS 2.1 varsayılanı).
DEFAULT_LINK_COLOR = "rgb(0, 0, 238)"
#: Tarayıcıların varsayılan gövde yazı tipleri (stil hiç uygulanmamış sayfa).
DEFAULT_FONTS = frozenset({"times", "times new roman", "serif", "-webkit-standard"})
#: Bir sayfada en az bu kadar içerik bağlantısı varsa oranı anlamlıdır.
MIN_LINKS_FOR_RATIO = 3
#: İçerik bağlantılarının bu oranı varsayılan maviyse sayfa "stilsiz bağlantılı" sayılır.
DEFAULT_LINK_RATIO = 0.5
#: Yolun bu parçaları şablon türünü belirlemez (dil öneki, sayfalama).
_NEUTRAL_SEGMENTS = frozenset({"page", "sayfa", "en", "tr", "de", "fr"})


@dataclass(frozen=True, slots=True)
class StyleSignature:
    """Bir sayfanın ölçülen stil imzası (tarayıcıdan gelen ham veriden)."""

    font: str = ""
    content_links: int = 0
    default_blue_links: int = 0
    buttons: int = 0
    default_buttons: int = 0

    @property
    def primary_font(self) -> str:
        return self.font.split(",")[0].strip().strip("\"'").lower()

    @property
    def default_font(self) -> bool:
        return self.primary_font in DEFAULT_FONTS

    @property
    def default_links(self) -> bool:
        return (
            self.content_links >= MIN_LINKS_FOR_RATIO
            and self.default_blue_links / self.content_links >= DEFAULT_LINK_RATIO
        )


def signature_from(raw: object) -> StyleSignature:
    """Tarayıcıdan gelen sözlüğü imzaya çevir; bozuk veri boş imza olur."""
    if not isinstance(raw, Mapping):
        return StyleSignature()

    def sayi(anahtar: str) -> int:
        deger = raw.get(anahtar)
        return int(deger) if isinstance(deger, int | float) and not isinstance(deger, bool) else 0

    return StyleSignature(
        font=str(raw.get("font") or ""),
        content_links=sayi("contentLinks"),
        default_blue_links=sayi("defaultBlueLinks"),
        buttons=sayi("buttons"),
        default_buttons=sayi("defaultButtons"),
    )


def _template_key(url: str) -> str:
    """Yolun şablonu belirleyen kısmı: ilk anlamlı parça + derinlik."""
    parcalar = [p for p in urlparse(url).path.split("/") if p]
    anlamli = [p for p in parcalar if p.lower() not in _NEUTRAL_SEGMENTS and not p.isdigit()]
    if not anlamli:
        return "/"
    return f"{anlamli[0].lower()}/{len(anlamli)}"


def pick_audit_pages(home: str, links: Sequence[str], limit: int = MAX_AUDIT_PAGES) -> list[str]:
    """Ana sayfa bağlantılarından her şablon türünden bir sayfa seç (sıra korunur)."""
    ana = home.split("#")[0].rstrip("/")
    secilen: list[str] = []
    gorulen: set[str] = set()
    for link in links:
        adres = link.split("#")[0]
        if adres.rstrip("/") == ana or not adres.startswith(("http://", "https://")):
            continue
        anahtar = _template_key(adres)
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        secilen.append(adres)
        if len(secilen) >= limit:
            break
    return secilen


def consistency_findings(
    pages: Sequence[tuple[str, StyleSignature]],
) -> tuple[list[str], list[str]]:
    """İlk sayfa (ana sayfa) referanstır. (engelleyici, uyarı) bulguları döndürür.

    Yargı yok, yalnız tarayıcı varsayılanı: ana sayfa varsayılanı kullanmıyorken iç sayfa
    kullanıyorsa, o sayfaya sitenin stili uygulanmamıştır.
    """
    if len(pages) < 2:
        return [], []
    _, ana = pages[0]
    engel: list[str] = []
    uyari: list[str] = []
    for ad, imza in pages[1:]:
        if imza.default_font and not ana.default_font:
            engel.append(
                f"{ad} tarayıcı varsayılan yazı tipiyle açılıyor ({imza.primary_font}); ana "
                f"sayfa '{ana.primary_font}' kullanıyor. Bu sayfaya sitenin stili uygulanmamış."
            )
        if imza.default_links and not ana.default_links:
            engel.append(
                f"{ad} içindeki {imza.default_blue_links}/{imza.content_links} bağlantı "
                "tarayıcı varsayılanı mavi (#0000EE); ana sayfada böyle değil. Sayfa stilsiz "
                "kalmış: bağlantı, başlık ve fiyat renklerini ana sayfayla eşle."
            )
        if imza.default_buttons and not ana.default_buttons:
            uyari.append(
                f"{ad} içinde {imza.default_buttons} düğme tarayıcının gri sistem düğmesi "
                "görünümünde; ana sayfanın düğme stiline uymuyor."
            )
    return engel, uyari


#: Kabına göre büzülmüş görsel sayısı en az bu kadarsa bir DÜZEN hatasıdır (ızgara,
#: şerit); tek tük görsel tasarım tercihi olabilir, uyarı olarak kalır.
MIN_SHRUNK_FOR_BLOCKING = 3

#: Sayfada çalışan ölçüm: kabına göre büzülmüş içerik görselleri ve stil imzası.
#: Yorum değil ölçüm döndürür; karar Python tarafındadır.
AUDIT_PROBE = """() => {
    const ad = (e) => e.tagName.toLowerCase() +
        (e.className && typeof e.className === 'string'
            ? '.' + e.className.trim().split(/\\s+/)[0] : '');
    const gorunur = (e) => {
        const r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    // 1) Büyük kaynak görsel, kabını dolduran bir zincirle küçük çizilmiş; zincirin
    //    üstündeki ilk geniş kap görselden çok daha geniş. Bu, yüzde genişliklerin
    //    betikle verilen bir kap ölçüsüne dayandığı ve o ölçünün kaybolduğu durumdur
    //    (kaydırıcı, betikli ızgara). Avatar gibi bilinçli küçük görseller yuvarlaktır
    //    ya da kabını doldurmaz; onlar sayılmaz.
    const shrunkMedia = [];
    for (const img of document.querySelectorAll('img')) {
        if (!gorunur(img) || img.naturalWidth < 240) continue;
        const r = img.getBoundingClientRect();
        if (r.width >= 100) continue;
        if (parseFloat(getComputedStyle(img).borderRadius) >= r.width * 0.4) continue;
        let kap = img.parentElement;
        for (let i = 0; kap && i < 12; i++, kap = kap.parentElement) {
            const w = kap.getBoundingClientRect().width;
            if (w < r.width * 1.1) continue;
            if (w >= r.width * 2.5 && kap.querySelectorAll('img').length <= 2) {
                shrunkMedia.push([ad(kap), Math.round(r.width), Math.round(w)]);
            }
            break;
        }
    }

    // 2) Stil imzası: gövde yazı tipi, içerik bağlantılarının rengi, sistem düğmeleri.
    const icerik = [...document.querySelectorAll('a[href]')].filter((a) =>
        gorunur(a) && a.innerText.trim().length > 2 && !a.closest('header, nav, footer'));
    const dugmeler = [...document.querySelectorAll(
        'button, input[type=submit], input[type=button]')].filter(gorunur);
    const sistem = dugmeler.filter((b) => {
        const s = getComputedStyle(b);
        return s.appearance !== 'none' && ['rgb(239, 239, 239)', 'rgb(240, 240, 240)',
            'rgb(233, 233, 237)'].includes(s.backgroundColor);
    });
    const style = {
        font: getComputedStyle(document.body).fontFamily,
        contentLinks: icerik.length,
        defaultBlueLinks: icerik.filter((a) =>
            getComputedStyle(a).color === 'rgb(0, 0, 238)').length,
        buttons: dugmeler.length,
        defaultButtons: sistem.length,
    };
    return {shrunkMedia, style};
}"""


def shrunk_findings(name: str, rows: Sequence[tuple[str, int, int]]) -> tuple[list[str], list[str]]:
    """Büzülmüş görseller: düzen örüntüsüyse engelleyici, tek tükse uyarı."""
    if not rows:
        return [], []
    ornek = ", ".join(f"{kap} içinde {gorsel}px/{kutu}px" for kap, gorsel, kutu in rows[:3])
    metin = (
        f"{name} içinde {len(rows)} görsel kabına göre büzülmüş ({ornek}): görsel kutusunu "
        "doldurmuyor. Kabın genişliği betiğe ya da eksik bir kurala bağlı olabilir; kartın "
        "ve görselin genişliğini CSS ile ver (ör. grid-template-columns, width: 100%)."
    )
    return ([metin], []) if len(rows) >= MIN_SHRUNK_FOR_BLOCKING else ([], [metin])
