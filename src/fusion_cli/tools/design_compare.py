"""Yapılan sayfayı KAYNAK ölçümle karşılaştır ve farkları METİN olarak söyle.

Ölçüldü (2 Ekim 2026, 8. kabul koşusu, NIM Nemotron 3 Ultra): model ekran görüntüsünü
okuyamıyor. Yazdığı ana sayfada kahraman alanı bomboştu (beyaz zeminde beyaz başlık),
menü madde imli dikey liste olarak çıkıyordu ve logo yazıyla çizilmişti; `start_preview`
"sayfa hatasız açıldı" dediği için model hiçbirini fark etmedi.

Kaynak site `site_design` ile ölçülmüşse aynı ölçüm kodu (`assets/design_probe.js`) yerel
sayfada da çalıştırılır ve iki ölçüm burada karşılaştırılır. Çıktı, modelin doğrudan
düzeltebileceği somut farklardır; görsel okuyabilen ya da okuyamayan her modelde çalışır.
Saf işlevdir: ağ ve dosya bilmez.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

#: Modele verilecek en fazla fark (en önemliler önce); fazlası gürültüdür.
MAX_DIFFERENCES = 14
#: Karşılaştırılacak en fazla bölüm (sayfanın üst kısmı ilk izlenimi belirler).
MAX_SECTIONS = 10
#: Yükseklik/ölçü farkı bu oranı aşarsa bildirilir.
SIZE_TOLERANCE = 0.3
#: Adıyla bildirilecek en fazla eksik bölüm.
MAX_MISSING_SECTIONS = 5
#: Ayrı karşılaştırılan çerçeve bölümleri (bkz. `_header`).
_CHROME = frozenset({"ust-bilgi", "alt-bilgi"})
#: Ana sayfa sayılan yollar (statik sitede önizleme adresi açılış dosyasını taşır).
_HOME_PATHS = frozenset({"", "index.html", "index.php"})
#: Liste sayfası sayılmak için gereken en az ürün.
MIN_LISTING_PRODUCTS = 6

_KIND_NAMES = {
    "ust-bilgi": "üst bilgi", "kahraman": "kahraman (tam genişlik açılış)",
    "urun-listesi": "ürün şeridi/ızgarası", "gorsel-izgara": "görsel ızgarası",
    "afis": "afiş", "alt-bilgi": "alt bilgi", "metin": "metin",
}  # fmt: skip


def pick_reference(pages: list[dict[str, Any]], built: dict[str, Any]) -> dict[str, Any] | None:
    """Yapılan sayfanın türüne karşılık gelen kaynak sayfa (ana, ürün, liste)."""
    if not pages:
        return None
    if urlparse(str(built.get("url", ""))).path.strip("/") in _HOME_PATHS:
        return pages[0]
    if built.get("product"):
        return next((page for page in pages if page.get("product")), None)
    if len(built.get("products", [])) >= MIN_LISTING_PRODUCTS:
        listings = [page for page in pages[1:] if not page.get("product")]
        return max(listings, key=lambda page: len(page.get("products", [])), default=None)
    return None


def health_findings(built: dict[str, Any]) -> list[str]:
    """Kaynak gerekmeyen yerleşim sorunları: tek sütun ürün ızgarası, stilsiz form öğeleri.

    Ölçüldü (3 Ekim 2026, 16. kabul koşusu): model WooCommerce'in stillerini kapatıp mağaza,
    sepet ve ödeme için stil yazmadı; sayfalar çıplak HTML'di ve hiçbir ölçüm bunu söylemedi.
    """
    health = built.get("health") or {}
    found: list[str] = []
    if health.get("singleColumn"):
        found.append(
            f"ÜRÜN IZGARASI: ürün kartları tek sütun ve {health.get('widestCard')}px genişlikte "
            f"({health.get('viewport')}px ekranda). Kartları çok sütunlu ızgaraya al "
            "(ör. grid, 4 sütun, kart ~250-360px); listeleme için stil eksik."
        )
    unstyled, controls = health.get("unstyledControls", 0), health.get("controls", 0)
    if controls and unstyled >= max(2, controls // 2):
        found.append(
            f"FORM ÖĞELERİ: {unstyled}/{controls} giriş/düğme tarayıcı varsayılanıyla (stilsiz) "
            "görünüyor. Bu sayfanın form ve düğmelerine kaynak sitedeki ölçülerle stil ver "
            "(ya da eklentinin kendi stillerini kapatma)."
        )
    if health.get("overflowX"):
        found.append("YATAY TAŞMA: sayfa ekrandan geniş; bir öğe viewport'u aşıyor.")
    return found


def compare(reference: dict[str, Any], built: dict[str, Any]) -> list[str]:
    """Kaynak ölçümle yapılan sayfa arasındaki farklar, önem sırasıyla."""
    differences = [
        *health_findings(built),
        *_invisible_text(built),
        *_header(reference, built),
        *_fonts(reference, built),
        *_sections(reference, built),
        *_products(reference, built),
        *_product_page(reference, built),
    ]
    return differences[:MAX_DIFFERENCES]


def _invisible_text(built: dict[str, Any]) -> list[str]:
    hidden = built.get("invisible", [])
    if not hidden:
        return []
    examples = ", ".join(f"'{item['text']}' ({item['color']})" for item in hidden[:3])
    return [
        f"GÖRÜNMEYEN YAZI: {len(hidden)} yazı zeminle aynı renkte, okunmuyor: {examples}. "
        "Arkasına görseli/videoyu koy ya da rengi değiştir."
    ]


def _header(reference: dict[str, Any], built: dict[str, Any]) -> list[str]:
    found: list[str] = []
    ref_logo, logo = str(reference.get("logo", "")), str(built.get("logo", ""))
    if ref_logo and not logo:
        found.append("LOGO: kaynakta üst bilgide logo görseli var, sayfanda yok.")
    elif ref_logo and "<text" in logo:
        found.append(
            "LOGO: logo yazıyla çizilmiş bir SVG; kaynak sitenin indirilen logo dosyasını kullan."
        )
    ref_nav, nav = reference.get("navigation", {}), built.get("navigation", {})
    if nav.get("bullets"):
        found.append(
            "MENÜ: bağlantıların yanında madde imi görünüyor; listeye `list-style: none; "
            "margin: 0; padding: 0` ver."
        )
    if ref_nav.get("layout") == "yatay" and nav.get("layout") == "dikey":
        found.append(
            "MENÜ: kaynakta yatay tek satır, sayfanda alt alta diziliyor (flex ile yatay)."
        )
    wanted = [str(link.get("text", "")) for link in ref_nav.get("menu", [])[:8]]
    present = {
        str(link.get("text", "")).casefold()
        for link in (*nav.get("header", []), *nav.get("menu", []))
    }
    missing = [text for text in wanted if text and text.casefold() not in present]
    if missing:
        found.append(f"MENÜ: kaynaktaki şu öğeler üst bilgide yok: {', '.join(missing)}.")
    ref_header = (reference.get("layout") or {}).get("header") or {}
    header = (built.get("layout") or {}).get("header") or {}
    if ref_header and header and _differs(ref_header.get("height"), header.get("height")):
        found.append(
            f"ÜST BİLGİ: yükseklik kaynakta {ref_header.get('height')}px, "
            f"sayfanda {header.get('height')}px."
        )
    return found


def _fonts(reference: dict[str, Any], built: dict[str, Any]) -> list[str]:
    wanted = [str(font["value"]) for font in reference.get("fonts", {}).get("used", [])[:2]]
    used = [str(font["value"]) for font in built.get("fonts", {}).get("used", [])]
    missing = [font for font in wanted if font not in used]
    if not missing:
        return []
    return [
        f"YAZI TİPİ: kaynakta {', '.join(wanted)} kullanılıyor; sayfanda {', '.join(missing)} "
        f"yok (kullanılan: {', '.join(used[:3]) or '-'}). @font-face ile indirilen dosyaları bağla."
    ]


def _sections(reference: dict[str, Any], built: dict[str, Any]) -> list[str]:
    """Bölümleri TÜRLERİNE göre hizala: sıra numarası kaymaları yanlış fark üretmesin.

    Üst ve alt bilgi ayrı karşılaştırılır (`_header`); kaynakta üst bilgi kahramanın
    ÜSTÜNE biniyorsa ayrı bölüm sayılmaz, yapılan sayfada sayılır — ölçüldü: sıra
    numarasıyla eşleştirme bu yüzden on bölümün onunu da "farklı" gösterdi.
    """
    wanted = [s for s in reference.get("sections", []) if s["kind"] not in _CHROME][:MAX_SECTIONS]
    actual = [s for s in built.get("sections", []) if s["kind"] not in _CHROME]
    if not wanted:
        return []
    matcher = SequenceMatcher(
        a=[section["kind"] for section in wanted],
        b=[section["kind"] for section in actual],
        autojunk=False,
    )
    found: list[str] = []
    matched: set[int] = set()
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            matched.add(block.a + offset)
            found.extend(
                _section_pair(
                    block.a + offset + 1, wanted[block.a + offset], actual[block.b + offset]
                )
            )
    missing = [(index, section) for index, section in enumerate(wanted) if index not in matched]
    if not missing:
        return found
    order = [
        "BÖLÜM SIRASI: kaynak: "
        + " → ".join(_KIND_NAMES.get(s["kind"], s["kind"]) for s in wanted)
        + "; sayfan: "
        + (
            " → ".join(_KIND_NAMES.get(s["kind"], s["kind"]) for s in actual[:MAX_SECTIONS])
            or "boş"
        )
        + "."
    ]
    gaps = [
        f"EKSİK BÖLÜM: kaynakta {index + 1}. sırada {_describe(section)} var, sayfanda yok."
        for index, section in missing[:MAX_MISSING_SECTIONS]
    ]
    return [*order, *gaps, *found]


def _section_pair(position: int, wanted: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    name = _KIND_NAMES.get(wanted["kind"], wanted["kind"])
    found: list[str] = []
    if _has_media(wanted) and not _has_media(actual):
        medya = "video" if wanted.get("video") else "görsel"
        found.append(
            f"BÖLÜM {position} ({name}): kaynakta {medya} var, sayfanda bu bölümde yüklenen "
            "görsel/video yok (boş görünüyor). İndirilen dosyayı kullan ve yolunu doğrula."
        )
    if _differs(wanted.get("height"), actual.get("height")):
        found.append(
            f"BÖLÜM {position} ({name}): yükseklik kaynakta {wanted['height']}px, "
            f"sayfanda {actual['height']}px."
        )
    return found


def _products(reference: dict[str, Any], built: dict[str, Any]) -> list[str]:
    wanted, actual = len(reference.get("products", [])), len(built.get("products", []))
    found: list[str] = []
    if wanted >= MIN_LISTING_PRODUCTS and actual < wanted // 2:
        found.append(
            f"ÜRÜNLER: kaynak sayfada {wanted}+ ürün kartı (görsel + ad + fiyat) var, sayfanda "
            f"{actual}. Ürünleri mağazaya ekle ve bu sayfada listele."
        )
    # Ölçüldü (13. kabul koşusu): kartta ürün adı ve "Sepete Ekle" iki kez çıktı; şablon
    # kancası iki kez bağlanmıştı ve model ekranı göremediği için fark etmedi.
    yinelenen = [
        item["name"]
        for item in built.get("products", [])[:12]
        if item.get("name") and str(item.get("text", "")).count(str(item["name"])) >= 2
    ]
    if yinelenen:
        found.append(
            f"ÜRÜN KARTI: ad kartta iki kez yazılıyor ('{yinelenen[0]}'); şablon kancası ya "
            "da başlık iki kez bağlanmış, birini kaldır."
        )
    return found


def _product_page(reference: dict[str, Any], built: dict[str, Any]) -> list[str]:
    wanted, actual = reference.get("product"), built.get("product")
    if not wanted or not actual:
        return []
    found: list[str] = []
    if len(actual.get("images", [])) < min(2, len(wanted.get("images", []))):
        found.append(
            f"ÜRÜN SAYFASI: kaynakta {len(wanted.get('images', []))} büyük galeri görseli var, "
            f"sayfanda {len(actual.get('images', []))}."
        )
    ref_button, button = wanted.get("buyButton", {}), actual.get("buyButton", {})
    for key, label in (("background", "zemin"), ("color", "yazı rengi"), ("radius", "köşe")):
        if ref_button.get(key) and button.get(key) and ref_button[key] != button[key]:
            found.append(
                f"ÜRÜN SAYFASI: sepete ekle düğmesi {label} kaynakta {ref_button[key]}, "
                f"sayfanda {button[key]}."
            )
    if wanted.get("options") and not actual.get("options"):
        secenekler = ", ".join(dict.fromkeys(wanted["options"]))
        found.append(f"ÜRÜN SAYFASI: kaynakta seçenekler ({secenekler}) var, sayfanda yok.")
    return found


def _describe(section: dict[str, Any]) -> str:
    parts = [f"{_KIND_NAMES.get(section['kind'], section['kind'])} ({section['height']}px"]
    if section.get("video"):
        parts.append(", video")
    elif _has_media(section):
        parts.append(", görsel")
    headings = section.get("headings") or []
    if headings:
        parts.append(f", başlık '{headings[0]['text']}'")
    return "".join(parts) + ")"


def _has_media(section: dict[str, Any]) -> bool:
    return bool(section.get("video") or section.get("images") or section.get("backgroundImage"))


def _differs(wanted: object, actual: object) -> bool:
    if not isinstance(wanted, int | float) or not isinstance(actual, int | float) or not wanted:
        return False
    return abs(actual - wanted) / wanted > SIZE_TOLERANCE
