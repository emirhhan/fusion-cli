"""Önizleme: projeyi çalıştır, sayfayı ölç, kullanıcıya göster.

Ölçüldü (2 Ekim 2026, "sneaksup" sohbeti): kullanıcı önizleme istedi; Fusion
kurulum rehberi yazdı, sonra açmadığı bir `preview.html` bıraktı.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.core.events import PreviewReady
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import preview_tools
from fusion_cli.engines.agent.preview_tools import run_preview
from fusion_cli.engines.agent.turn_hints import (
    DESIGN_NOTE,
    PREVIEW_NOTE,
    SCOPE_NOTE,
    design_hint,
    preview_hint,
    scope_hint,
)
from fusion_cli.tools import preview_server
from fusion_cli.tools.preview_probe import PageProbe, probe
from fusion_cli.tools.preview_server import PreviewKind, detect_kind, static_entry
from fusion_cli.tools.wordpress_setup import WordPressSetup

PHP = shutil.which("php") or next(
    (p for p in ("/opt/homebrew/bin/php", "/usr/local/bin/php") if Path(p).is_file()), None
)
php_gerekli = pytest.mark.skipif(PHP is None, reason="php kurulu değil")


@pytest.fixture(autouse=True)
def _sunuculari_kapat():
    yield
    preview_server.stop_all()


def _sayfa(root: Path, ad: str = "index.html", govde: str = "") -> Path:
    path = root / ad
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<!doctype html><html><head><title>Deneme Mağaza</title></head><body><main>"
        f"<h1>Hoş geldiniz</h1><p>Yeni sezon ayakkabılar burada, hemen keşfet.</p>{govde}"
        f"</main></body></html>",
        encoding="utf-8",
    )
    return path


# --- Tür tespiti ----------------------------------------------------------------- #


def test_proje_turu_dosyalardan_anlasilir(tmp_path):
    (tmp_path / "wp" / "wp-content" / "themes").mkdir(parents=True)
    (tmp_path / "php").mkdir()
    (tmp_path / "php" / "index.php").write_text("<?php echo 1;", encoding="utf-8")
    (tmp_path / "node").mkdir()
    (tmp_path / "node" / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite"}}), encoding="utf-8"
    )
    _sayfa(tmp_path / "statik")
    (tmp_path / "bos").mkdir()

    assert detect_kind(tmp_path / "wp") is PreviewKind.WORDPRESS
    assert detect_kind(tmp_path / "php") is PreviewKind.PHP
    assert detect_kind(tmp_path / "node") is PreviewKind.NODE
    assert detect_kind(tmp_path / "statik") is PreviewKind.STATIC
    assert detect_kind(tmp_path / "bos") is None


def test_statik_giris_sayfasi_bulunur(tmp_path):
    _sayfa(tmp_path, "site/index.html")
    assert static_entry(tmp_path) == "site/index.html"


# --- Sunucu + ölçüm --------------------------------------------------------------- #


async def test_statik_site_sunulur_ve_olculur(tmp_path):
    _sayfa(tmp_path, govde='<a href="/hakkimizda.html">Hakkımızda</a>')
    _sayfa(tmp_path, "hakkimizda.html")

    preview = await preview_server.start(
        tmp_path, PreviewKind.STATIC, preview_server.free_port(), php=None, entry="index.html"
    )
    sonuc = await probe(preview.url, browser=False)

    assert sonuc.status == 200 and sonuc.title == "Deneme Mağaza"
    assert sonuc.problems == ()
    assert [link.status for link in sonuc.links] == [200]
    # İkinci çağrı çalışan sunucuyu yeniden kullanır, yenisini açmaz.
    again = await preview_server.start(tmp_path, PreviewKind.STATIC, 1, php=None)
    assert again is preview


async def test_kirik_baglanti_ve_bos_sayfa_sorun_sayilir(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><body><a href="/yok.html">Kayıp</a></body></html>', encoding="utf-8"
    )
    preview = await preview_server.start(
        tmp_path, PreviewKind.STATIC, preview_server.free_port(), php=None, entry="index.html"
    )

    problems = (await probe(preview.url, browser=False)).problems

    assert any("neredeyse boş" in p for p in problems)
    assert any("bağlantı açılmıyor" in p and "404" in p for p in problems)


def test_php_hata_metni_sorun_sayilir():
    sayfa = PageProbe(
        url="http://127.0.0.1:1/",
        status=200,
        title="",
        visible_chars=500,
        page_errors=("Fatal error",),
    )
    assert sayfa.problems == ("sayfada hata: Fatal error",)


@php_gerekli
async def test_php_projesi_php_sunucusuyla_calisir(tmp_path):
    (tmp_path / "index.php").write_text(
        "<?php $ad = 'Fusion'; ?><html><head><title>PHP Deneme</title></head><body>"
        "<p>Merhaba <?= $ad ?>, bu sayfa PHP ile üretildi ve çalışıyor.</p></body></html>",
        encoding="utf-8",
    )
    preview = await preview_server.start(
        tmp_path, PreviewKind.PHP, preview_server.free_port(), php=PHP
    )

    sonuc = await probe(preview.url, browser=False)

    assert sonuc.status == 200 and sonuc.title == "PHP Deneme" and sonuc.problems == ()
    preview_server.stop(preview)
    assert preview_server.running(tmp_path) is None


# --- Araç ------------------------------------------------------------------------- #


class _Yayinci:
    def __init__(self) -> None:
        self.olaylar: list[object] = []

    def publish(self, event: object) -> None:
        self.olaylar.append(event)


async def test_arac_siteyi_calistirir_ve_uygulamaya_adres_yayinlar(tmp_path):
    _sayfa(tmp_path)
    yayinci = _Yayinci()
    deps = SimpleNamespace(publisher=yayinci)

    sonuc = await run_preview(deps, {}, ToolContext(root=tmp_path))  # type: ignore[arg-type]

    assert sonuc.ok and "Önizleme çalışıyor: http://127.0.0.1:" in sonuc.output
    assert "hatasız açıldı" in sonuc.output
    hazir = [olay for olay in yayinci.olaylar if isinstance(olay, PreviewReady)]
    assert len(hazir) == 1 and hazir[0].kind == "static" and hazir[0].title == "Deneme Mağaza"


async def test_yuklenemeyen_kaynak_adiyla_sorun_olarak_soylenir(tmp_path):
    """Ölçüldü (2 Ekim 2026, 8. kabul koşusu): tema 12 görsele bağlanıyordu ama dosyalar
    kopyalanmamıştı; kahraman alanı boştu, araç "sayfa hatasız açıldı" dedi."""
    pytest.importorskip("playwright.async_api")
    _sayfa(tmp_path, govde='<img src="/assets/images/afis.jpg" width="600" height="300">')

    sonuc = await run_preview(
        SimpleNamespace(publisher=_Yayinci()),  # type: ignore[arg-type]
        {},
        ToolContext(root=tmp_path),
    )

    if "ekran görüntüsü" not in sonuc.output.lower():
        pytest.skip("Chromium başlatılamadı")
    assert "1 kaynak yüklenemedi" in sonuc.output
    assert "HTTP 404 /assets/images/afis.jpg" in sonuc.output
    assert "hatasız açıldı" not in sonuc.output


async def test_kaynak_olculmusse_onizleme_farklari_metin_olarak_soyler(tmp_path):
    """Görsel okuyamayan model ekran görüntüsünü göremez: farklar ölçülüp yazıyla verilir."""
    pytest.importorskip("playwright.async_api")
    _sayfa(
        tmp_path, govde="<header><nav><ul><li><a href='/a.html'>ERKEK</a></li></ul></nav></header>"
    )
    _sayfa(tmp_path, "a.html")
    kaynak = {
        "kaynak": "test",
        "sayfalar": [
            {
                "url": "https://m.test/",
                "logo": "https://m.test/logo.svg",
                "fonts": {"used": [{"value": "Oswald"}]},
                "navigation": {"layout": "yatay", "menu": [{"text": "KADIN", "href": "x"}]},
                "sections": [],
                "products": [],
            }
        ],
    }
    klasor = tmp_path / "tasarim-kaynak"
    klasor.mkdir()
    (klasor / "tasarim.json").write_text(json.dumps(kaynak), encoding="utf-8")

    sonuc = await run_preview(
        SimpleNamespace(publisher=_Yayinci()),  # type: ignore[arg-type]
        {},
        ToolContext(root=tmp_path),
    )

    if "ekran görüntüsü" not in sonuc.output.lower():
        pytest.skip("Chromium başlatılamadı")
    assert "KAYNAKLA FARKLAR (https://m.test/" in sonuc.output
    assert "LOGO: kaynakta üst bilgide logo görseli var, sayfanda yok" in sonuc.output
    assert "madde imi" in sonuc.output
    assert "şu öğeler üst bilgide yok: KADIN" in sonuc.output
    assert "YAZI TİPİ" in sonuc.output and "Oswald" in sonuc.output
    assert (tmp_path / ".fusion" / "onizleme.jpg").is_file()


async def test_calistirilacak_bir_sey_yoksa_ne_yapilacagini_soyler(tmp_path):
    sonuc = await run_preview(SimpleNamespace(publisher=_Yayinci()), {}, ToolContext(root=tmp_path))  # type: ignore[arg-type]

    assert not sonuc.ok and "kind='wordpress'" in sonuc.output and "KENDİSİ kurar" in sonuc.output


@php_gerekli
async def test_bos_klasorde_wordpress_istenirse_arac_kurulumu_kendisi_baslatir(
    tmp_path, monkeypatch
):
    """Ölçüldü (2 Ekim, 5. kabul koşusu): boş klasörde araç "önce temayı yaz" deyip
    reddetti; model `wp config create` + MySQL ile 10 dakika boğuştu."""
    istenen: dict[str, object] = {}

    async def _kur(root, url, *, wp_cli, plugins=()):
        istenen.update(root=root, plugins=plugins)
        (root / "index.php").write_text("<?php echo '<h1>Mağaza</h1>';", encoding="utf-8")
        return WordPressSetup(steps=("WordPress kuruldu",), theme=None, credentials=None)

    monkeypatch.setattr(preview_tools, "setup_wordpress", _kur)
    deps = SimpleNamespace(publisher=_Yayinci())

    sonuc = await run_preview(
        deps,  # type: ignore[arg-type]
        {"kind": "wordpress", "plugins": ["woocommerce"]},
        ToolContext(root=tmp_path),
    )

    assert sonuc.ok and "(wordpress)" in sonuc.output
    assert istenen == {"root": tmp_path, "plugins": ("woocommerce",)}
    assert (tmp_path / "wp-content" / "themes").is_dir()


async def test_gecersiz_eklenti_adi_kabuga_gitmeden_reddedilir(tmp_path):
    (tmp_path / "wp-content").mkdir()

    sonuc = await run_preview(
        SimpleNamespace(publisher=_Yayinci()),  # type: ignore[arg-type]
        {"plugins": ["woocommerce; rm -rf ~"]},
        ToolContext(root=tmp_path),
    )

    assert not sonuc.ok and "geçersiz: woocommerce; rm -rf ~" in sonuc.output


# --- İstek notları ----------------------------------------------------------------- #


@pytest.mark.parametrize(
    "istek",
    [
        "nasıl önizleyebilirim?",
        "ekstra bir şeyler kurmadan benim önizlememi sağla yeter",
        "siteyi göster",
        "show me the page",
    ],
)
def test_onizleme_istegi_aracı_kullandirir(istek):
    assert preview_hint(istek, available=True) == PREVIEW_NOTE
    assert preview_hint(istek, available=False) is None


def test_siradan_istek_onizleme_notu_almaz():
    assert preview_hint("bu fonksiyonu düzelt", available=True) is None


def test_olaydaki_buyuk_istek_asama_planiyla_calistirilir():
    olay = (
        "wordpress tabanlı bir website yapmanı istiyorum bu website birebir olarak "
        "https://www.sneaksup.com sitesine benzeyecek ... bu siteyi her sayfalarıyla "
        "birlite her eklentisi ile birlikte gerçek çalışan bir e ticaret sitesi yapmanı "
        "istiyorum ben ilerleyen zamanda bu siteyi bir hostinge ve domaine bağlayacağım."
    )
    assert scope_hint(olay) == SCOPE_NOTE
    assert scope_hint("basit bir e-ticaret sitesi yap") is None


def test_bir_siteye_benzetme_isteginde_once_tasarim_olcumu_istenir():
    """Ölçüldü (5. kabul koşusu): `site_design` defterdeydi ama model hiç çağırmadı;
    siteyi `browser_open` ile 15 kez gezip tasarımı tahmin etti."""
    olay = (
        "wordpress tabanlı bir website yapmanı istiyorum bu website birebir olarak "
        "https://www.sneaksup.com sitesine benzeyecek görsellerine kadar"
    )
    assert design_hint(olay, available=True) == DESIGN_NOTE
    assert design_hint("apple.com gibi olsun ana sayfa", available=True) == DESIGN_NOTE
    assert design_hint(olay, available=False) is None


@pytest.mark.parametrize(
    "istek",
    [
        "bana bir blog sitesi yap",
        "https://example.com adresindeki hatayı incele",
        "README.md dosyasını config.py ile aynı olacak şekilde düzelt",
    ],
)
def test_benzetme_olmayan_istek_tasarim_notu_almaz(istek):
    assert design_hint(istek, available=True) is None


async def test_liste_sepet_ve_odeme_sayfalari_da_olculur_ve_stilsizlik_soylenir(monkeypatch):
    """Ölçüldü (16. kabul koşusu): mağaza tek sütun dev görsel, sepet/ödeme çıplak form;
    yalnız ana sayfa ölçüldüğü için hiçbiri raporlanmadı."""
    from fusion_cli.engines.agent import preview_tools
    from fusion_cli.tools.preview_probe import LinkCheck

    olculen: list[str] = []

    async def _probe(url, **kwargs):
        olculen.append(url)
        health = {"viewport": 1440, "products": 4, "widestCard": 1368, "singleColumn": True,
                  "controls": 6, "unstyledControls": 5, "overflowX": False}  # fmt: skip
        return PageProbe(
            url=url, status=200, title="s", visible_chars=300, page_errors=(),
            measured={"url": url, "health": health, "products": [], "texts": [{"text": "Mağaza"}]},
        )  # fmt: skip

    monkeypatch.setattr(preview_tools, "probe", _probe)
    ana = PageProbe(
        url="http://127.0.0.1:8770/", status=200, title="Ö", visible_chars=500, page_errors=(),
        measured={"url": "http://127.0.0.1:8770/"},
        links=(
            LinkCheck("http://127.0.0.1:8770/shop/", 200),
            LinkCheck("http://127.0.0.1:8770/cart/", 200),
            LinkCheck("http://127.0.0.1:8770/checkout/", 200),
            LinkCheck("http://127.0.0.1:8770/hakkimizda/", 200),
        ),
    )  # fmt: skip

    farklar = await preview_tools._other_page_differences([{"url": "https://m.test/"}], ana)

    assert olculen == [
        "http://127.0.0.1:8770/shop/",
        "http://127.0.0.1:8770/cart/",
        "http://127.0.0.1:8770/checkout/",
    ]
    metin = "\n".join(farklar)
    assert (
        "LİSTE SAYFASI (http://127.0.0.1:8770/shop/): ÜRÜN IZGARASI: ürün kartları tek sütunda"
        in metin
    )
    # Üç sayfa aynı ölçümü verdi: bulgu bir kez, ilk görüldüğü sayfayla söylenir.
    assert metin.count("FORM ÖĞELERİ: 5/6") == 1
    assert "LİSTE SAYFASI (http://127.0.0.1:8770/shop/): FORM ÖĞELERİ: 5/6" in metin


async def test_woocommerce_stilleri_kapatilmissa_onizleme_uyarir(tmp_path):
    from fusion_cli.engines.agent.php_verify import woocommerce_styles_disabled

    tema = tmp_path / "wp-content" / "themes" / "klon"
    tema.mkdir(parents=True)
    (tema / "functions.php").write_text(
        "<?php add_filter('woocommerce_enqueue_styles', '__return_empty_array');",
        encoding="utf-8",
    )
    assert woocommerce_styles_disabled(tmp_path) == "wp-content/themes/klon/functions.php"
    (tema / "functions.php").write_text("<?php add_theme_support('woocommerce');", encoding="utf-8")
    assert woocommerce_styles_disabled(tmp_path) is None


async def test_kaynakta_urun_sayfasi_varsa_sitenin_urun_sayfasi_da_olculur(monkeypatch):
    """Ölçüldü (3 Ekim 2026, 11. kabul koşusu): bozulan ürün şablonu her ürün sayfasını
    "Shop" listesi yaptı; ana sayfa hatasızdı ve kapanış doğrulaması bunu görmedi."""
    from fusion_cli.engines.agent import preview_tools
    from fusion_cli.tools.preview_probe import LinkCheck

    kaynak = [
        {"url": "https://m.test/"},
        {"url": "https://m.test/u/1", "product": {"name": "Hoodie", "images": [], "options": []}},
    ]
    olculen: list[str] = []

    async def _probe(url, **kwargs):
        olculen.append(url)
        return PageProbe(
            url=url, status=200, title="Ürün", visible_chars=100, page_errors=(),
            measured={"url": url, "texts": [{"tag": "a", "text": "ERKEK"}]},
        )  # fmt: skip

    monkeypatch.setattr(preview_tools, "probe", _probe)
    ana = PageProbe(
        url="http://127.0.0.1:8770/", status=200, title="Önizleme", visible_chars=500,
        page_errors=(), measured={"url": "http://127.0.0.1:8770/"},
        links=(LinkCheck("http://127.0.0.1:8770/shop/", 200),
               LinkCheck("http://127.0.0.1:8770/product/ayakkabi/", 200)),
    )  # fmt: skip

    farklar = await preview_tools._other_page_differences(kaynak, ana)

    assert olculen[0] == "http://127.0.0.1:8770/product/ayakkabi/"
    urun = [f for f in farklar if f.startswith("ÜRÜN SAYFASI")]
    assert len(urun) == 1 and "ürün ölçülemedi (ilk başlık 'ERKEK')" in urun[0]
    # Kaynakta ürün sayfası yoksa "ürün ölçülemedi" denmez; sayfa yalnız sağlık için ölçülür.
    farklar = await preview_tools._other_page_differences([{"url": "https://m.test/"}], ana)
    assert not any("ürün ölçülemedi" in f for f in farklar)


async def test_ana_sayfayla_ayni_icerigi_gosteren_baglanti_sorun_sayilir(tmp_path):
    """Ölçüldü (14. kabul koşusu): sepet ve ödeme sayfaları 200 dönüp ana sayfayı gösterdi."""
    govde = '<a href="/sepet.html">Sepet</a><a href="/hakkimizda.html">Hakkımızda</a>'
    _sayfa(tmp_path, govde=govde)
    _sayfa(tmp_path, "sepet.html", govde=govde)  # ana sayfanın birebir kopyası
    (tmp_path / "hakkimizda.html").write_text(
        "<html><body><main><h1>Hakkımızda</h1><p>Bambaşka bir sayfa, kendi metniyle.</p>"
        "</main></body></html>",
        encoding="utf-8",
    )

    onizleme = await preview_server.start(
        tmp_path, PreviewKind.STATIC, preview_server.free_port(), php=None, entry="index.html"
    )
    sonuc = await probe(onizleme.url, browser=False)

    sorunlar = "\n".join(sonuc.problems)
    assert "ana sayfayla aynı içeriği gösteriyor" in sorunlar and "sepet.html" in sorunlar
    assert "hakkimizda.html" not in sorunlar


async def test_kaynak_siteye_istek_atan_sayfa_uyarilir(monkeypatch):
    """Ölçüldü (16. kabul koşusu): model sepet işlemlerini kaynak sitenin canlı API'sine bağladı."""
    from fusion_cli.engines.agent import preview_tools

    kaynak = [{"url": "https://www.m.test/", "sections": [], "products": []}]
    sonuc = PageProbe(
        url="http://127.0.0.1:8770/", status=200, title="x", visible_chars=200, page_errors=(),
        measured={"url": "http://127.0.0.1:8770/", "sections": [], "products": []},
        external_hosts=("fonts.gstatic.com", "api.m.test"),
    )  # fmt: skip

    farklar = preview_tools._differences(kaynak, sonuc)

    assert farklar is not None and "KAYNAK SİTEYE İSTEK: sayfan m.test" in farklar[1]


def test_tema_woocommerce_stillerini_kapatinca_dosyasi_bulunur(tmp_path):
    """Ölçüldü (3 Ekim 2026, 16. kabul koşusu): tema WooCommerce stillerini kapattı ve
    mağaza/sepet/ödeme için stil yazmadı; sayfalar çıplak HTML kaldı."""
    from fusion_cli.engines.agent.php_verify import woocommerce_styles_disabled

    tema = tmp_path / "wp-content" / "themes" / "kopya"
    tema.mkdir(parents=True)
    (tema / "functions.php").write_text("<?php add_theme_support('woocommerce');", "utf-8")
    assert woocommerce_styles_disabled(tmp_path) is None

    (tema / "functions.php").write_text(
        "<?php add_filter( 'woocommerce_enqueue_styles', '__return_empty_array' );", "utf-8"
    )
    assert woocommerce_styles_disabled(tmp_path) == "wp-content/themes/kopya/functions.php"
    assert woocommerce_styles_disabled(tmp_path / "yok") is None


def test_php_hatasinin_mesaji_dosyasi_ve_satiri_bildirilir():
    """Ölçüldü (3 Ekim 2026, 17. kabul koşusu): önizleme yalnız "sayfada hata: Fatal error"
    dedi; modelin düzeltmesi gereken "Class ... not found in header.php:42" hiç gitmedi."""
    from fusion_cli.tools.preview_probe import page_error_lines

    govde = (
        "<html><body><style>.x{color:red}</style>\n<b>Fatal error</b>:  Uncaught Error: Class "
        "&quot;Sneaksup_Nav_Walker&quot; not found in /site/wp-content/themes/t/header.php:42\n"
        "Stack trace:\n#0 {main}\n  thrown in <b>/site/wp-content/themes/t/header.php</b> on "
        "line <b>42</b><br />\n</body></html>"
    )
    satirlar = page_error_lines(govde)
    assert len(satirlar) == 1
    assert satirlar[0].startswith('Fatal error: Uncaught Error: Class "Sneaksup_Nav_Walker"')
    assert "header.php:42" in satirlar[0]
    assert page_error_lines("<p>her şey yolunda</p>") == ()


async def test_ana_sayfada_soylenen_bulgu_alt_sayfada_tekrarlanmaz(monkeypatch):
    """Ölçüldü (17. kabul koşusu): ortak üst bilgideki kırık menü bağlantıları mağaza ve
    sepet sayfasında yeniden yazıldı; asıl sayfa sorunları gürültüde kayboldu."""
    from fusion_cli.engines.agent import preview_tools
    from fusion_cli.tools.preview_probe import LinkCheck

    kirik = LinkCheck("http://127.0.0.1:8770/erkek/", 404)

    async def _probe(url, **kwargs):
        return PageProbe(
            url=url, status=200, title="s", visible_chars=300, page_errors=(),
            measured={"url": url, "health": {"controls": 4, "unstyledControls": 4}},
            links=(kirik,),
        )  # fmt: skip

    monkeypatch.setattr(preview_tools, "probe", _probe)
    ana = PageProbe(
        url="http://127.0.0.1:8770/", status=200, title="Ö", visible_chars=500, page_errors=(),
        measured={"url": "http://127.0.0.1:8770/"},
        links=(kirik, LinkCheck("http://127.0.0.1:8770/sepet/", 200),
               LinkCheck("http://127.0.0.1:8770/odeme/", 200)),
    )  # fmt: skip

    farklar = await preview_tools._other_page_differences([], ana, ana.problems)

    assert not any("erkek" in fark for fark in farklar)
    form = [fark for fark in farklar if "FORM ÖĞELERİ" in fark]
    assert len(form) == 1 and form[0].startswith("SEPET SAYFASI")


async def test_urun_ve_sepet_baglantisi_varsa_sepete_ekleme_denenir(monkeypatch):
    """Ölçüldü (17. kabul koşusu): "SEPETE EKLE" form dışındaydı, sepet hep boş kaldı."""
    from fusion_cli.engines.agent import preview_tools
    from fusion_cli.tools.preview_probe import LinkCheck

    denenen: list[tuple[str, str]] = []

    async def _dene(urun, sepet):
        denenen.append((urun, sepet))
        return "SEPETE EKLEME ÇALIŞMIYOR: …"

    monkeypatch.setattr(preview_tools.shop_flow, "cart_flow_problem", _dene)
    ana = PageProbe(
        url="http://127.0.0.1:8770/", status=200, title="Ö", visible_chars=500, page_errors=(),
        links=(LinkCheck("http://127.0.0.1:8770/product/a/", 200),
               LinkCheck("http://127.0.0.1:8770/sepet/", 200)),
    )  # fmt: skip

    assert await preview_tools._cart_flow(ana) == ("SEPETE EKLEME ÇALIŞMIYOR: …",)
    assert denenen == [("http://127.0.0.1:8770/product/a/", "http://127.0.0.1:8770/sepet/")]
    sepetsiz = PageProbe(
        url="http://127.0.0.1:8770/", status=200, title="Ö", visible_chars=500, page_errors=(),
        links=(LinkCheck("http://127.0.0.1:8770/product/a/", 200),),
    )  # fmt: skip
    assert await preview_tools._cart_flow(sepetsiz) == ()


def test_onizleme_ilk_satiri_durumu_once_soyler():
    """Ölçüldü (17. kabul koşusu): başarısız önizleme 'çalışıyor' diye başlıyordu;
    takılma sorusu ilk satırdan üretildiği için öğretmen 'hata yok' dedi."""
    from fusion_cli.engines.agent.preview_tools import _status_line

    hata = _status_line("http://x/", "wordpress", 500, ["PHP Fatal error: a.php:3"], ())
    sorunlu = _status_line("http://x/", "wordpress", 200, [], ("ürün sayısı 4/24",))
    temiz = _status_line("http://x/", "wordpress", 200, [], ())

    assert hata.startswith("BAŞARISIZ: HTTP 500") and "a.php:3" in hata
    assert sorunlu.startswith("SORUNLU:") and "1 kaynak farkı" in sorunlu
    assert temiz.startswith("Önizleme çalışıyor")


def test_php_hatasi_karisan_bozuk_baglanti_olcumu_dusurmez():
    """Ölçüldü (4 Ekim): kontrol karakterli adres InvalidURL ile aracı çökertiyordu."""
    from fusion_cli.tools.preview_probe import _fetch

    assert _fetch("http://127.0.0.1:9/<br />\n<b>Fatal error</b>") == (0, "")


def test_acik_bulgu_sayisi_artinca_gerileme_uyarisi_ikinci_satirda():
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent.preview_tools import _with_regression_note

    sonuc = ToolResult("SORUNLU: sayfa açılıyor\nÖlçüm: x")

    kotu = _with_regression_note(sonuc, 2, 13)

    assert kotu.output.splitlines()[1].startswith("GERİLEME: açık sorun+fark sayısı 2 → 13")
    assert _with_regression_note(sonuc, 13, 2) is sonuc
    assert _with_regression_note(sonuc, None, 5) is sonuc
