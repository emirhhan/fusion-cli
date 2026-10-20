"""Kopyala-sonra-bağla hattı: yakalama yardımcıları, tema üretimi, aktarım, yönlendirme."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.clone_tools import _pick_pages, price_format, site_locale
from fusion_cli.engines.agent.turn_hints import CLONE_NOTE, DESIGN_NOTE, design_hint
from fusion_cli.tools.site_capture import (
    CapturedPage,
    SiteCapture,
    _with_suffix,
    absolutize_css,
    collapse_srcset,
    css_urls,
    drop_remote_srcset,
    html_urls,
    localize,
    same_site_paths,
)
from fusion_cli.tools.woo_import import parse_import_output
from fusion_cli.tools.woo_theme import THEME_URI, theme_slug, write_theme


def test_css_url_leri_dosyanin_kendi_adresine_gore_mutlaklasir():
    css = "a{background:url('../img/a.png')} b{src:url(data:x)} c{x:url(/f.woff2)}"

    sonuc = absolutize_css(css, "https://cdn.site.com/css/main.css")

    assert "url(https://cdn.site.com/img/a.png)" in sonuc
    assert "url(data:x)" in sonuc
    assert css_urls(sonuc, "https://site.com") == [
        "https://cdn.site.com/img/a.png",
        "https://cdn.site.com/f.woff2",
    ]


def test_srcset_en_buyuk_adaya_iner_ve_yalniz_o_indirilir():
    html = (
        '<img src="https://s.com/a.jpg" '
        'srcset="https://s.com/a-1x.jpg 1x, https://s.com/a-2x.jpg 2x">'
    )

    tek = collapse_srcset(html)

    assert 'srcset="https://s.com/a-2x.jpg"' in tek
    assert html_urls(tek) == ["https://s.com/a.jpg", "https://s.com/a-2x.jpg"]


def test_yerellesmeyen_srcset_silinir_hotlink_kalmaz():
    html = '<img src="/yerel.jpg" srcset="https://s.com/b.jpg">'
    assert drop_remote_srcset(html) == '<img src="/yerel.jpg" >'
    assert drop_remote_srcset('<img srcset="assets/b.jpg">') == '<img srcset="assets/b.jpg">'


def test_localize_kacisli_adresi_de_degistirir_ve_uzun_adres_once_gelir():
    html = (
        '<img src="https://s.com/_next/image?url=x&amp;w=1920"><a href="https://s.com/a.css.map">'
    )
    varliklar = {
        "https://s.com/_next/image?url=x&amp;w=1920": "assets/image-1.webp",
        "https://s.com/a.css": "assets/a.css",
    }

    sonuc = localize(html, varliklar, "T/")

    assert 'src="T/assets/image-1.webp"' in sonuc
    assert "https://s.com/a.css.map" in sonuc


def test_ayni_site_baglantilari_koke_goreli_olur():
    html = '<a href="https://www.s.com/erkek">E</a><a href="https://www.s.com">A</a>'
    assert same_site_paths(html, "https://www.s.com") == '<a href="/erkek">E</a><a href="/">A</a>'


def test_uzantisiz_varliga_icerik_turunden_uzanti_eklenir():
    assert _with_suffix("assets/image-ab12", "image/webp; q=1").endswith(".webp")
    assert _with_suffix("assets/a-ab12.png", "image/webp") == "assets/a-ab12.png"


def _yakalama(header_offset: int = 64) -> SiteCapture:
    sayfa = CapturedPage(
        url="https://www.ornek.com",
        title="Örnek",
        lang="tr",
        body_class="ana",
        header='<header><img src="https://www.ornek.com/logo.svg"><a href="https://www.ornek.com/kadin">K</a></header>',
        main="<section><p>Kod örneği: <?php echo 1; ?></p></section>",
        footer="<footer>alt</footer>",
        header_offset=header_offset,
        screenshots={1440: b"jpg"},
    )
    return SiteCapture(
        pages=(sayfa,),
        css="body{background:url(https://www.ornek.com/bg.png)}",
        assets={
            "https://www.ornek.com/logo.svg": "assets/logo-1.svg",
            "https://www.ornek.com/bg.png": "assets/bg-1.png",
        },
    )


def test_tema_woocommerce_sablonuyla_ve_yerel_varliklarla_yazilir(tmp_path):
    tema = write_theme(_yakalama(), tmp_path, "https://www.ornek.com", ("kadin",))

    klasor = tmp_path / "ornek-kopya"
    assert tema.folder == klasor
    assert {"style.css", "functions.php", "woocommerce.php", "index.php"} <= set(tema.files)
    header = (klasor / "header.php").read_text(encoding="utf-8")
    assert f'src="{THEME_URI}assets/logo-1.svg"' in header
    assert "/?product_cat=kadin" in header and "wp_head()" in header
    on_sayfa = (klasor / "front-page.php").read_text(encoding="utf-8")
    assert "&lt;?php echo 1;" in on_sayfa and "<?php echo 1;" not in on_sayfa
    assert "url(assets/bg-1.png)" in (klasor / "kopya.css").read_text(encoding="utf-8")
    assert "woocommerce_content()" in (klasor / "woocommerce.php").read_text(encoding="utf-8")
    fonksiyonlar = (klasor / "functions.php").read_text(encoding="utf-8")
    assert (
        "wp_dequeue_style" not in fonksiyonlar
        and "add_theme_support( 'woocommerce' )" in fonksiyonlar
    )
    assert "padding-top: 64px" in (klasor / "style.css").read_text(encoding="utf-8")
    assert (klasor / "referans" / "sayfa0-1440.jpg").read_bytes() == b"jpg"


def test_akista_baslik_varsa_ic_sayfa_boslugu_eklenmez(tmp_path):
    write_theme(_yakalama(header_offset=0), tmp_path, "https://www.ornek.com")
    assert "padding-top" not in (tmp_path / "ornek-kopya" / "style.css").read_text(encoding="utf-8")


def test_tema_adi_alan_adindan_gelir():
    assert theme_slug("https://www.sneaksup.com/erkek") == "sneaksup-kopya"


def test_aktarim_ciktisinin_son_json_satiri_okunur():
    sonuc = parse_import_output('Uyarı: x\n{"eklenen": 3, "atlanan": 1, "gorselsiz": 0}')
    assert (sonuc.added, sonuc.skipped, sonuc.error) == (3, 1, "")
    assert parse_import_output("Fatal error").error.startswith("Fatal error")
    assert parse_import_output('{"hata": "WooCommerce etkin değil"}').error


def test_fiyat_bicimi_ve_dil_kaynaktan_cikarilir():
    tr = price_format("7.199,00 TL")
    assert tr is not None and (tr.thousand, tr.decimal, tr.position) == (".", ",", "right_space")
    en = price_format("$1,299.00")
    assert en is not None and (en.thousand, en.position) == (",", "left")
    assert price_format("Fiyat sorunuz") is None
    assert (site_locale("tr"), site_locale("en-GB"), site_locale("")) == ("tr_TR", "en_GB", "")


def test_yakalanacak_sayfalar_ana_sayfa_once_ve_sinirli():
    from types import SimpleNamespace

    rapor = SimpleNamespace(
        pages=[{"url": f"https://s.com/{yol}"} for yol in ("", "erkek", "kadin", "cocuk")]
    )

    sayfalar = _pick_pages(rapor, "https://s.com")  # type: ignore[arg-type]

    assert sayfalar[0] == "https://s.com" and len(sayfalar) == 3


def test_wordpress_kopyasi_istenince_clone_site_digerinde_olcum_yolu():
    gorev_wp = "https://www.sneaksup.com sitesinin birebir wordpress kopyasını yap"
    gorev_statik = "https://www.ornek.com sitesine benzeyen bir html sayfa yap"

    assert design_hint(gorev_wp, available=True, clone_available=True) == CLONE_NOTE
    assert design_hint(gorev_wp, available=True, clone_available=False) == DESIGN_NOTE
    assert design_hint(gorev_statik, available=True, clone_available=True) == DESIGN_NOTE
    assert design_hint("bir blog yap", available=True, clone_available=True) is None


def test_kaynak_baglantilari_woocommerce_adreslerine_baglanir():
    from fusion_cli.tools.woo_theme import wire_store_links

    html = (
        '<a href="/">A</a><a href="/erkek/">E</a><a href="/sepet">S</a>'
        '<a href="/air-jordan-1?x=1&amp;y=2">J</a>'
    )

    sonuc = wire_store_links(html, ("erkek",))

    assert '<a href="/">A</a>' in sonuc
    assert "/?product_cat=erkek" in sonuc
    assert "wc_get_cart_url()" in sonuc and "kopya-sepet-sayaci" in sonuc
    assert "/?s=air+jordan+1&post_type=product" in sonuc


def test_betikli_simge_dugmeleri_baglantiya_doner():
    from fusion_cli.tools.woo_theme import buttons_to_links

    html = (
        '<button class="i" type="button" aria-label="Hesabım"><svg></svg></button>'
        '<button aria-label="Kapat">x</button>'
    )

    sonuc = buttons_to_links(html)

    assert sonuc.startswith("<a href=\"<?php echo esc_url( wc_get_page_permalink( 'myaccount' ) )")
    assert 'class="i"' in sonuc and 'type="button"' not in sonuc
    assert '<button aria-label="Kapat">x</button>' in sonuc


def test_tema_ilk_hali_yalniz_metin_dosyalariyla_yedeklenir(tmp_path):
    from fusion_cli.engines.agent.clone_tools import _backup_theme

    tema = tmp_path / "tema"
    (tema / "assets").mkdir(parents=True)
    (tema / "header.php").write_text("<?php ?>", encoding="utf-8")
    (tema / "kopya.css").write_text("a{}", encoding="utf-8")
    (tema / "assets" / "x.png").write_bytes(b"png")

    _backup_theme(tema, tmp_path / "yedek")

    assert sorted(p.name for p in (tmp_path / "yedek").iterdir()) == ["header.php", "kopya.css"]


_KAYDIRICI = """<!doctype html><html><head><style>
.swiper{overflow:hidden;width:600px}.swiper-wrapper{display:flex}
.kart{max-width:25%;flex-basis:25%}.kart img{width:100%;display:block}
</style></head><body><header>ust</header><div class="swiper"><div class="swiper-wrapper">
<div class="swiper-slide"><div class="kart"><img height="10"></div></div>
<div class="swiper-slide"><div class="kart"><img height="10"></div></div>
</div></div>
<script>document.querySelectorAll('.swiper-slide').forEach(s=>{s.style.width='250px';
s.querySelector('.kart').style.cssText='max-width:100%;flex-basis:100%';});
</script><footer>alt</footer></body></html>"""


def test_kaydirici_slaytlari_ve_gorsel_zinciri_olculen_genislikle_dondurulur(tmp_path):
    """Betik kopyada çalışmaz: slayt ve içindeki kart kaynaktaki genişliği korumalı."""
    playwright = pytest.importorskip("playwright.sync_api")
    from fusion_cli.tools.site_capture import CAPTURE_SCRIPT

    sayfa = tmp_path / "index.html"
    sayfa.write_text(_KAYDIRICI, encoding="utf-8")
    try:
        with playwright.sync_playwright() as p:
            tarayici = p.chromium.launch()
            page = tarayici.new_page(viewport={"width": 1000, "height": 600})
            page.goto(sayfa.as_uri())
            veri = page.evaluate(CAPTURE_SCRIPT.read_text(encoding="utf-8"))
            tarayici.close()
    except playwright.Error as hata:
        pytest.skip(f"tarayıcı yok: {hata}")

    ana = veri["main"]
    assert 'class="swiper-slide" style="width: 250px; max-width: none; flex: 0 0 250px;"' in ana
    assert "width: 250px; max-width: none; flex-basis: auto;" in ana
    assert '<div class="swiper" style="overflow: hidden;">' in ana
    assert "<script" not in ana


_KAYAN_PANEL = """<!doctype html><html><head><style>.izgara{display:flex;width:1600px}
</style></head><body><div class="panel"><div class="izgara">takvim</div></div>
<script>const s=document.createElement('style');s.textContent='.panel{overflow-x:auto}';
document.head.append(s);</script></body></html>"""


def test_icerigi_tasan_kaydirma_paneli_tasmasini_korur(tmp_path):
    """dalga45: CSS-in-JS ile verilen overflow-x kopyada düştü, takvim sayfayı 365 px taşırdı."""
    playwright = pytest.importorskip("playwright.sync_api")
    from fusion_cli.tools.site_capture import CAPTURE_SCRIPT

    sayfa = tmp_path / "index.html"
    sayfa.write_text(_KAYAN_PANEL, encoding="utf-8")
    try:
        with playwright.sync_playwright() as p:
            tarayici = p.chromium.launch()
            page = tarayici.new_page(viewport={"width": 1000, "height": 600})
            page.goto(sayfa.as_uri())
            veri = page.evaluate(CAPTURE_SCRIPT.read_text(encoding="utf-8"))
            tarayici.close()
    except playwright.Error as hata:
        pytest.skip(f"tarayıcı yok: {hata}")

    assert '<div class="panel" style="overflow-x: auto;">' in veri["main"]


def test_kategori_adi_kaynak_menuden_gelir_turkce_harfler_korunur():
    from fusion_cli.engines.agent.clone_tools import category_labels, display_label

    menu = [
        {"text": "ERKEK", "href": "https://www.ornek.com/erkek"},
        {"text": "KADIN", "href": "https://www.ornek.com/kadin/"},
        {"text": "İNDİRİM", "href": "https://www.ornek.com/indirim"},
        {"text": "Blog", "href": "https://www.ornek.com/blog"},
        "bozuk",
    ]

    etiketler = category_labels(menu, ("erkek", "kadin", "indirim"), "tr")

    assert etiketler == {"erkek": "Erkek", "kadin": "Kadın", "indirim": "İndirim"}
    assert display_label("NEW  ARRIVALS", "en") == "New Arrivals"
    assert category_labels(None, ("erkek",), "tr") == {}


def test_sayfa_cevirisi_dile_ozel_metin_tasimaz():
    from fusion_cli.engines.agent.clone_tools import TRANSLATE_PAGES_PHP

    assert "'Page title', 'woocommerce'" in TRANSLATE_PAGES_PHP
    assert "Sepet" not in TRANSLATE_PAGES_PHP and "wc_get_page_id" in TRANSLATE_PAGES_PHP


def test_magaza_isteginde_once_alisveris_akisi_kurulur():
    from fusion_cli.engines.agent.turn_hints import STORE_NOTE, store_hint

    assert store_hint("woocommerce ile e-ticaret sitesi yap") == STORE_NOTE
    assert store_hint("https://x.com sitesinin birebir mağaza kopyası") == STORE_NOTE
    assert store_hint("kişisel blog sitesi yap") is None
