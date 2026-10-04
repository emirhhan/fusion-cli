"""`clone_site`: bir siteyi WordPress/WooCommerce kopyasına çeviren tek adımlık hat.

Ölçüldü: 17 kabul koşusunun hepsinde model "ölç → temayı sıfırdan yaz" yolunu
seçti; aynalama aracını 1.696 araç çağrısında bir kez çağırdı. Aynı model Hermes
ve Codex'te de aynı yola girdi. Model opsiyonel yöntemi seçmiyor, ama araç
sonucunda söylenen sıradaki adıma uyuyor. Bu yüzden görünüm, katalog ve kurulum
bu araçta DETERMİNİSTİK yapılır; modele kalan iş sonuç metninde listelenir.

Sıra: tasarım ölçümü (sayfa keşfi + katalog + görseller) → sayfa yakalama
(CSSOM + betiksiz DOM, yerel varlıklar) → tema iskeleti → WordPress + WooCommerce
kurulumu → katalog aktarımı.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...tools import preview_server
from ...tools import site_design as design
from ...tools.site_capture import CaptureError, SiteCapture, capture_site
from ...tools.web import url_block_reason
from ...tools.woo_import import import_products
from ...tools.woo_theme import ThemeFiles, theme_slug, write_theme
from ...tools.wordpress_setup import (
    WordPressSetupError,
    find_wp_cli,
    run_wp,
    setup_wordpress,
)

#: Yakalanacak en fazla sayfa: ana sayfa + bir liste + bir ürün sayfası çoğu
#: mağazanın görünüm dilini taşır; her sayfa iki genişlikte ~20-40 sn sürer.
MAX_CAPTURED_PAGES = 3

COD_SETTINGS = '{"enabled":"yes","title":"Kapıda ödeme","description":"Teslimatta ödeme."}'

NEXT_STEPS = """SIRADAKİ ADIMLAR (görünümü SIFIRDAN YAZMA; kopya hazır):
1. start_preview(kind='wordpress', plugins=['woocommerce']) ile siteyi aç ve farklara bak.
2. Kategori, sepet ve hesap bağlantıları WooCommerce'e bağlandı, sepette sayaç var.
   Bağlanmamış menü bağlantısı kaldıysa header.php'yi tek tek düzenleme; gerekirse
   küçük bir python betiğiyle toplu değiştir.
3. Mağaza ve ürün sayfası woocommerce.php içinden GERÇEK WooCommerce şablonuyla açılır.
   Görünümünü referansa yaklaştırmak için yalnız {tema}/style.css'e `.woocommerce …`
   seçicileriyle stil ekle. WooCommerce formlarını/kancalarını SÖKME, stillerini kapatma.
   Referans: {tema}/referans/sayfa*.html ve sayfa*-1440.jpg.
4. Ödeme sayfasında sipariş verilebildiğini dene (kapıda ödeme açık); gerçek ödeme
   geçidi (iyzico, PayTR) yerelde kurulmaz, kullanıcının anahtarıyla sonra eklenir.
5. Mobil görünüm: kopya masaüstü DOM'undan yapıldı. Kaynak mobilde farklı menü
   gösteriyorsa ({tema}/referans/sayfa0-390.jpg) header.php'ye @media ile mobil menü ekle.
6. Her değişiklikten sonra start_preview'ı tekrar çağır; FARKLAR ve SORUNLAR boşalana kadar."""


@dataclass(frozen=True, slots=True)
class PriceFormat:
    thousand: str
    decimal: str
    position: str


_PRICE_SAMPLE = re.compile(r"\d{1,3}(?P<binlik>[.,\s])\d{3}(?P<ondalik>[.,])\d{2}")


def price_format(sample: str) -> PriceFormat | None:
    """Kaynaktaki fiyat yazımından WooCommerce biçimi ('7.199,00 TL' → '.', ',', sağda)."""
    eslesme = _PRICE_SAMPLE.search(sample)
    if eslesme is None:
        return None
    sembol_solda = bool(re.match(r"^\s*[^\d\s]", sample))
    return PriceFormat(
        thousand=eslesme.group("binlik").replace("\xa0", " "),
        decimal=eslesme.group("ondalik"),
        position="left" if sembol_solda else "right_space",
    )


#: WooCommerce sayfalarını (mağaza, sepet, ödeme, hesap) site dilindeki ad ve adrese çevirir.
#: Çeviriler WooCommerce'in kendi dil paketinden gelir; burada dile özel metin yoktur.
TRANSLATE_PAGES_PHP = (
    "foreach ( array( 'shop' => array( 'Shop', 'shop' ), 'cart' => array( 'Cart', 'cart' ), "
    "'checkout' => array( 'Checkout', 'checkout' ), "
    "'myaccount' => array( 'My account', 'my-account' ) ) as $anahtar => $cift ) { "
    "$kimlik = wc_get_page_id( $anahtar ); if ( $kimlik < 1 ) { continue; } "
    "wp_update_post( array( 'ID' => $kimlik, "
    "'post_title' => _x( $cift[0], 'Page title', 'woocommerce' ), "
    "'post_name' => sanitize_title( _x( $cift[1], 'Page slug', 'woocommerce' ) ) ) ); } "
    "flush_rewrite_rules();"
)


def display_label(text: str, lang: str) -> str:
    """Menü metnini ('KADIN') okunur ada ('Kadın') çevir; Türkçede I/İ ayrımı korunur."""
    temiz = " ".join(text.split())
    if lang.lower().startswith("tr"):
        kucuk = temiz.replace("I", "ı").replace("İ", "i").lower()
        return " ".join(
            ("İ" if kelime[0] == "i" else kelime[0].upper()) + kelime[1:]
            for kelime in kucuk.split(" ")
            if kelime
        )
    return temiz.title()


def category_labels(menu: object, slugs: tuple[str, ...], lang: str) -> dict[str, str]:
    """Kategori kısa adı → kaynaktaki menü metni (adresin son parçası eşleşiyorsa)."""
    if not isinstance(menu, list):
        return {}
    etiketler: dict[str, str] = {}
    for oge in menu:
        if not isinstance(oge, dict):
            continue
        son = str(oge.get("href", "")).rstrip("/").rsplit("/", 1)[-1].lower()
        metin = str(oge.get("text", "")).strip()
        if son in slugs and metin and son not in etiketler:
            etiketler[son] = display_label(metin, lang)
    return etiketler


def site_locale(lang: str) -> str:
    """Sayfa dili ('tr', 'tr-TR') → WordPress yerel ayarı ('tr_TR'); bilinmiyorsa boş."""
    parcalar = re.split(r"[-_]", lang.strip())
    if not parcalar or len(parcalar[0]) != 2:
        return ""
    bolge = parcalar[1] if len(parcalar) > 1 and len(parcalar[1]) == 2 else parcalar[0]
    return f"{parcalar[0].lower()}_{bolge.upper()}"


async def _localize_store(
    root: Path, wp_cli: str, catalog_sample: str, lang: str, steps: list[str]
) -> None:
    """WooCommerce'i kaynağın diline ve fiyat yazımına getir (best effort)."""
    yerel = site_locale(lang)
    if yerel and yerel != "en_US":
        # Site dili de değişmeli: yalnız eklenti paketi kurulunca arayüz İngilizce kalıyor,
        # sayfalar "Cart" / "Checkout" adıyla ve ABD varsayılanıyla açılıyordu (ölçüldü).
        await run_wp(wp_cli, root, "language", "core", "install", yerel, "--activate")
        kod, _ = await run_wp(wp_cli, root, "language", "plugin", "install", "woocommerce", yerel)
        if kod == 0:
            steps.append(f"Site ve WooCommerce dili: {yerel}")
        await run_wp(
            wp_cli, root, "option", "update", "woocommerce_default_country", yerel.split("_")[1]
        )
        kod, _ = await run_wp(wp_cli, root, "eval", TRANSLATE_PAGES_PHP)
        if kod == 0:
            steps.append("Mağaza sayfalarının adı ve adresi site diline çevrildi.")
    bicim = price_format(catalog_sample)
    if bicim is None:
        return
    for anahtar, deger in (
        ("woocommerce_price_thousand_sep", bicim.thousand),
        ("woocommerce_price_decimal_sep", bicim.decimal),
        ("woocommerce_currency_pos", bicim.position),
    ):
        await run_wp(wp_cli, root, "option", "update", anahtar, deger)
    steps.append(f"Fiyat biçimi kaynaktan: binlik '{bicim.thousand}', ondalık '{bicim.decimal}'.")


#: Temanın ilk halinin yedeği (önizleme gerilemesinde geri dönülecek yer).
THEME_BACKUP_DIR = ".fusion/tema-ilk"


def _backup_theme(folder: Path, target: Path) -> None:
    """Tema metin dosyalarını (PHP/CSS) yedekle; varlıklar değişmediği için kopyalanmaz."""
    target.mkdir(parents=True, exist_ok=True)
    for dosya in folder.iterdir():
        if dosya.is_file() and dosya.suffix in (".php", ".css"):
            (target / dosya.name).write_bytes(dosya.read_bytes())


def _pick_pages(report: design.DesignReport, url: str) -> list[str]:
    """Ölçülen sayfalardan yakalanacakları seç: ana sayfa önce, sonra farklı türler."""
    adresler = [str(page.get("url", "")) for page in report.pages if page.get("url")]
    secilen = [url, *(a for a in adresler if a.rstrip("/") != url.rstrip("/"))]
    return list(dict.fromkeys(secilen))[:MAX_CAPTURED_PAGES]


def _summary(
    capture: SiteCapture, theme: ThemeFiles, steps: list[str], problems: list[str], root: Path
) -> str:
    tema = theme.folder.relative_to(root).as_posix()
    satirlar = [
        f"Kopya tema yazıldı: {tema} ({', '.join(theme.files)}).",
        f"Yakalanan sayfalar: {', '.join(page.url for page in capture.pages)}.",
        f"İndirilen varlık: {len(capture.assets)} (kaynağa hotlink yok); "
        f"CSS: {len(capture.css)} karakter.",
        *steps,
    ]
    if problems:
        satirlar.append("SORUNLAR:")
        satirlar.extend(f"- {sorun}" for sorun in problems)
    satirlar.append(NEXT_STEPS.format(tema=tema))
    return "\n".join(satirlar)


def _catalog_categories(catalog: Path) -> tuple[str, ...]:
    """Katalogdaki kategori kısa adları (menü bağlantılarını bağlamak için)."""
    try:
        urunler = json.loads(catalog.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(
        dict.fromkeys(
            str(u.get("kategori", "")).strip().lower()
            for u in urunler
            if isinstance(u, dict) and str(u.get("kategori", "")).strip()
        )
    )


def _catalog_sample(catalog: Path) -> str:
    try:
        urunler = json.loads(catalog.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return next((str(u.get("fiyat", "")) for u in urunler if isinstance(u, dict)), "")


async def _install(
    root: Path,
    catalog: Path,
    lang: str,
    steps: list[str],
    problems: list[str],
    labels: dict[str, str] | None = None,
) -> None:
    """WordPress + WooCommerce kur, temayı etkinleştir, kataloğu aktar."""
    wp_cli = find_wp_cli()
    try:
        kurulum = await setup_wordpress(
            root,
            f"http://127.0.0.1:{preview_server.free_port()}",
            wp_cli=wp_cli,
            plugins=("woocommerce",),
        )
    except WordPressSetupError as error:
        problems.append(f"WordPress kurulamadı: {error}")
        return
    steps.extend(kurulum.steps)
    problems.extend(kurulum.problems)
    if wp_cli is None or not await asyncio.to_thread(catalog.is_file):
        problems.append("katalog bulunamadı; ürünler aktarılmadı")
        return
    # Kapıda ödeme: ödeme sayfasının uçtan uca çalışması için gerçek ödeme geçidi
    # gerekmeyen tek yöntem (kabul testinde "sipariş verilebilir" ölçülür).
    kod, cikti = await run_wp(
        wp_cli, root, "option", "update", "woocommerce_cod_settings", COD_SETTINGS, "--format=json"
    )
    if kod == 0:
        steps.append("Kapıda ödeme etkinleştirildi.")
    else:
        problems.append(f"kapıda ödeme açılamadı: {cikti[-200:]}")
    ornek = await asyncio.to_thread(_catalog_sample, catalog)
    await _localize_store(root, wp_cli, ornek, lang, steps)
    aktarim = await import_products(root, catalog, wp_cli)
    if aktarim.error:
        problems.append(f"ürün aktarımı: {aktarim.error}")
    steps.append(
        f"Ürün aktarıldı: {aktarim.added} eklendi, {aktarim.skipped} atlandı, "
        f"{aktarim.without_image} görselsiz."
    )
    for slug, etiket in (labels or {}).items():
        await run_wp(
            wp_cli, root, "term", "update", "product_cat", slug, "--by=slug", f"--name={etiket}"
        )
    if labels:
        steps.append(f"Kategori adları kaynaktaki menüden alındı: {', '.join(labels.values())}.")


async def run_clone_site(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Siteyi ölç, yakala, temaya çevir, WooCommerce'e kur ve kataloğu aktar."""
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        return ToolResult.failure("'url' gerekli (ör. https://site.com).")
    url = url.strip() if url.startswith(("http://", "https://")) else f"https://{url.strip()}"
    reason = url_block_reason(url)
    if reason is not None:
        return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
    root = context.root
    kaynak = root / design.DEFAULT_FOLDER
    try:
        rapor = await design.measure(url, chrome=context.chrome, extra_pages=())
    except design.DesignError as error:
        return ToolResult.failure(f"Site ölçülemedi: {error}")
    await design.download_assets(rapor, kaynak)
    await asyncio.to_thread(design.save_report, rapor, kaynak, design.DEFAULT_FOLDER)
    tema_klasoru = root / "wp-content" / "themes" / theme_slug(url)
    try:
        yakalama = await capture_site(_pick_pages(rapor, url), tema_klasoru)
    except CaptureError as error:
        return ToolResult.failure(f"Sayfa yakalanamadı: {error}")
    kategoriler = await asyncio.to_thread(_catalog_categories, kaynak / "urunler.json")
    # Mağaza sayfalarının stili kaynak ana sayfanın ölçülerinden üretilir.
    olcum = rapor.pages[0] if rapor.pages else None
    tema = await asyncio.to_thread(
        write_theme, yakalama, tema_klasoru.parent, url, kategoriler, olcum
    )
    await asyncio.to_thread(_backup_theme, tema.folder, root / THEME_BACKUP_DIR)
    adimlar: list[str] = [
        f"Temanın ilk hali yedeklendi: {THEME_BACKUP_DIR}/ (gerilemede geri dön)."
    ]
    sorunlar = list(yakalama.problems)
    dil = yakalama.pages[0].lang if yakalama.pages else ""
    menu = (olcum or {}).get("navigation", {}).get("menu") if isinstance(olcum, dict) else None
    etiketler = category_labels(menu, kategoriler, dil)
    await _install(root, kaynak / "urunler.json", dil, adimlar, sorunlar, etiketler)
    return ToolResult(_summary(yakalama, tema, adimlar, sorunlar, root))


def clone_tools() -> tuple[Tool, ...]:
    return (
        Tool(
            name="clone_site",
            description="Bir siteyi WordPress + WooCommerce kopyasına çevir: görünümü (CSS, "
            "görseller, başlık/altlık) birebir yakalar, temayı yazar, WooCommerce'i kurar ve "
            "ürünleri aktarır. Bir siteye BENZEYEN/KOPYASI site istendiğinde İLK adım budur.",
            parameters={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            run=run_clone_site,
            mutating=True,
        ),
    )
