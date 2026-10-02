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
