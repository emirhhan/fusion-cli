"""Kopyala-sonra-bağla hattı: yakalama yardımcıları, tema üretimi, aktarım, yönlendirme."""

from __future__ import annotations

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
    tema = write_theme(_yakalama(), tmp_path, "https://www.ornek.com")

    klasor = tmp_path / "ornek-kopya"
    assert tema.folder == klasor
    assert {"style.css", "functions.php", "woocommerce.php", "index.php"} <= set(tema.files)
    header = (klasor / "header.php").read_text(encoding="utf-8")
    assert f'src="{THEME_URI}assets/logo-1.svg"' in header
    assert 'href="/kadin"' in header and "wp_head()" in header
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
