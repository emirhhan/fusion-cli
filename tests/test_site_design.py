"""Sitenin tasarım sistemini ölçme (`site_design`).

Ölçüldü (2 Ekim 2026): "görsellerinden yazı tiplerine, bileşenlerine kadar aynı"
istenen sitede Fusion sayfayı yalnız metin olarak okuyabiliyordu; yazı tipini,
renkleri ve kart yapısını tahmin ediyordu.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from fusion_cli.tools import site_design as design

_CORE = Path(__file__).resolve().parents[1] / "chrome-extension" / "core.js"

_KART = (
    '<div class="kart"><a href="/urun/{n}"><img src="/u{n}.png" width="250" height="250"></a>'
    '<h3>Ayakkabı {n}</h3><span class="fiyat">{fiyat} TL</span></div>'
)
_SAYFA_SABLON = """<!doctype html><html><head><meta charset="utf-8"><title>Mağaza</title>
<style>
:root { --marka: #1626ff; }
@font-face { font-family: "Marka"; src: url("/fonts/marka.woff2") format("woff2"); }
body { font-family: Marka, sans-serif; color: #171620; margin: 0; }
header { position: sticky; top: 0; height: 60px; background: #fff; }
.kap { max-width: 1200px; margin: 0 auto; }
.kart { width: 250px; border-radius: 8px; background: #f0f0f0; }
.kart h3 { font-size: 16px; }
.fiyat { font-size: 12px; }
button.ana { background: #000; color: #fff; padding: 12px 24px; border-radius: 0; }
</style></head><body>
<header><a href="/"><img src="/logo.png" width="120" height="40" alt="Logo"></a>
<nav><a href="/erkek">ERKEK</a> <a href="/kadin">KADIN</a></nav>
<a href="/sepet" aria-label="Sepet"><svg width="20" height="20"></svg></a></header>
<main class="kap"><h1>Yeni Sezon</h1><button class="ana">Alışverişe Başla</button>
<div class="liste">{kartlar}</div></main>
<footer><a href="/iletisim">İletişim</a></footer></body></html>"""
_SAYFA = _SAYFA_SABLON.replace(
    "{kartlar}",
    "".join(
        _KART.format(n=n, fiyat=fiyat)
        for n, fiyat in ((1, "3.899,00"), (2, "2.499,00"), (3, "1.999,00"))
    ),
)

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAQUlEQVR4nO3PMQ0AAAjDMO5fNCLGCzI6s+7l"
    "AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAHy2NZQAB0pSPmgAAAABJRU5ErkJggg=="
)


def test_eklenti_ve_python_ayni_olcum_kodunu_tasir():
    """Tek kaynak: core.js'teki blok `assets/design_probe.js` ile birebir aynı olmalı."""
    core = _CORE.read_text(encoding="utf-8")
    blok = core.split("  // <fusion-design>\n", 1)[1].split("  // </fusion-design>\n", 1)[0]
    assert blok == design.PROBE_SOURCE.read_text(encoding="utf-8")
    assert 'if (operation === "design") return designProbe(args || {});' in core


def test_sayfa_kesfi_menu_urun_ve_sepeti_bulur():
    home = {
        "url": "https://m.test/",
        "navigation": {
            "menu": [{"text": "ERKEK", "href": "https://m.test/erkek"}],
            "header": [{"text": "Sepet", "href": "https://m.test/sepet"}],
            "footer": [{"text": "Dış", "href": "https://baska.test/x"}],
        },
        "components": [{"link": "https://m.test/urun/1"}],
    }

    sayfalar = design.discover_pages(home, ("https://m.test/ozel",))

    assert sayfalar == [
        "https://m.test/ozel",
        "https://m.test/erkek",
        "https://m.test/urun/1",
        "https://m.test/sepet",
    ]


playwright = pytest.importorskip("playwright.async_api")


async def test_gercek_tarayicida_tasarim_olculur_ve_varliklar_kaydedilir(tmp_path, monkeypatch):
    from playwright.async_api import async_playwright

    async def _sayfa_rotasi(route):
        url = route.request.url
        if url.endswith(".png"):
            await route.fulfill(body=_PNG, content_type="image/png")
        elif url.endswith(".woff2"):
            await route.fulfill(body=b"wOF2fake", content_type="font/woff2")
        else:
            await route.fulfill(body=_SAYFA, content_type="text/html; charset=utf-8")

    async with async_playwright() as driver:
        try:
            browser = await driver.chromium.launch()
        except Exception as exc:  # pragma: no cover - tarayıcı ikilisi yoksa
            pytest.skip(f"Chromium yok: {exc}")
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.route("**/*", _sayfa_rotasi)
        rapor = design.DesignReport(source="test")
        veri = await design._playwright_page(page, "https://m.test/", design.probe_script(), rapor)
        await browser.close()

    assert veri["fonts"]["used"][0]["value"] == "Marka"
    assert veri["fonts"]["faces"][0]["sources"] == ["https://m.test/fonts/marka.woff2"]
    assert veri["cssVars"]["--marka"] == "#1626ff"
    assert veri["layout"]["header"]["sticky"] is True
    assert veri["scale"]["h1"]["size"]
    kart = veri["components"][0]
    assert kart["count"] == 3 and kart["style"]["radius"] == "8px"
    assert veri["prices"][0]["text"] == "3.899,00 TL"
    assert veri["buttons"][0]["text"] == "Alışverişe Başla"
    assert any(link["text"] == "Sepet" for link in veri["navigation"]["header"])
    # Sayfa bölümleri yukarıdan aşağı sıralıdır; ürün ızgarası fiyatlı öğelerinden tanınır.
    turler = [bolum["kind"] for bolum in veri["sections"]]
    assert turler[0] == "ust-bilgi" and "urun-listesi" in turler
    assert [urun["name"] for urun in veri["products"]] == ["Ayakkabı 1", "Ayakkabı 2", "Ayakkabı 3"]
    assert veri["products"][0]["price"] == "3.899,00 TL"
    assert veri["products"][0]["link"] == "https://m.test/urun/1"

    # Varlıklar: ağ yerine sahte indirme.
    monkeypatch.setattr(
        design,
        "_fetch",
        lambda url, folder, limit: (folder / Path(url).name).write_bytes(b"x") and Path(url).name,
    )
    await design.download_assets(rapor, tmp_path / "kaynak")
    hedef = design.save_report(rapor, tmp_path / "kaynak", "kaynak")

    assert hedef.is_file() and (tmp_path / "kaynak" / "ekran-1.jpg").is_file()
    assert "marka.woff2" in "".join(rapor.fonts.values())
    urunler = json.loads((tmp_path / "kaynak" / "urunler.json").read_text(encoding="utf-8"))
    assert urunler[0] == {
        "ad": "Ayakkabı 1",
        "fiyat": "3.899,00 TL",
        "fiyat_sayi": 3899.0,
        "para_birimi": "TRY",
        "gorsel": "kaynak/images/u1.png",
        "kategori": "",
        "kaynak": "https://m.test/urun/1",
    }
    ozet = design.summarize(rapor, "kaynak")
    assert "Marka" in ozet and "BİREBİR" in ozet and "kendi görsellerinle değiştir" in ozet
    assert "BÖLÜMLER (ana sayfa" in ozet and "3 ürün → kaynak/urunler.json" in ozet
    assert "para birimini TRY yap" in ozet
    # Ölçüldü (8. kabul koşusu): özet logoyu söylemeyince model yazıyla logo uydurdu.
    assert "LOGO: kaynak/images/logo.png" in ozet


def test_satir_ici_svg_logo_dosyaya_yazilir_ve_ozette_gosterilir(tmp_path):
    rapor = design.DesignReport(
        source="test", pages=[{"url": "https://m.test/", "logo": '<svg width="120"></svg>'}]
    )

    design.save_report(rapor, tmp_path, "kaynak")

    assert (tmp_path / "logo.svg").read_text(encoding="utf-8") == '<svg width="120"></svg>'
    assert "LOGO: kaynak/logo.svg" in design.summarize(rapor, "kaynak")


def test_urunler_sayfalar_arasinda_dengeli_secilir_ve_kategori_alir(monkeypatch):
    """Sınır dolduğunda yalnız ana sayfanın ürünleri kalmamalı; kategori sayfası önceliklidir."""
    monkeypatch.setattr(design, "MAX_PRODUCTS", 4)

    def _urun(n: int) -> dict[str, str]:
        return {"name": f"Ürün {n}", "price": "1 TL", "image": "", "link": f"https://m.test/u/{n}"}

    rapor = design.DesignReport(
        pages=[
            {"url": "https://m.test/", "products": [_urun(n) for n in (1, 2, 3, 4)]},
            {"url": "https://m.test/erkek?sayfa=2", "products": [_urun(n) for n in (1, 5, 6)]},
        ]
    )

    urunler = design.collect_products(rapor, "kaynak")

    assert [(u["ad"], u["kategori"]) for u in urunler] == [
        ("Ürün 1", "erkek"),
        ("Ürün 5", "erkek"),
        ("Ürün 2", ""),
        ("Ürün 6", "erkek"),
    ]


def test_urun_ayrinti_sayfasi_galeri_ve_secenekleri_urune_ekler():
    rapor = design.DesignReport(
        pages=[
            {
                "url": "https://m.test/u/1",
                "products": [],
                "product": {
                    "name": "Hoodie",
                    "price": "3.899,00 TL",
                    "images": ["https://m.test/g1.jpg", "https://m.test/yok.jpg"],
                    "options": ["S", "M", "S", "M"],
                    "description": "Açıklama",
                },
            }
        ],
        images={"https://m.test/g1.jpg": "g1.jpg"},
    )

    (urun,) = design.collect_products(rapor, "kaynak")

    assert urun["galeri"] == ["kaynak/images/g1.jpg"] and urun["gorsel"] == "kaynak/images/g1.jpg"
    assert urun["secenekler"] == ["S", "M"] and urun["fiyat"] == "3.899,00 TL"


async def test_eklenti_bagliyken_olcum_kullanicinin_chromeunda_yapilir(monkeypatch):
    """Kullanıcı beklentisi: Fusion siteyi KENDİ eklentisiyle incelesin."""
    monkeypatch.setattr(design, "SCROLL_SETTLE_MS", 0)
    cagrilar: list[tuple[str, dict]] = []
    sayfalar = {
        "https://m.test/": {
            "url": "https://m.test/",
            "navigation": {"menu": [{"text": "ERKEK", "href": "https://m.test/erkek"}]},
            "components": [],
        },
        "https://m.test/erkek": {"url": "https://m.test/erkek", "navigation": {}},
    }

    class _Chrome:
        adres = ""

        async def invoke(self, islem: str, veri: dict) -> dict:
            cagrilar.append((islem, veri))
            if islem == "navigate":
                self.adres = veri["url"]
                return {"ok": True, "veri": {"url": self.adres}}
            if islem == "design":
                return {"ok": True, "veri": dict(sayfalar[self.adres])}
            if islem == "screenshot":
                return {"ok": True, "veri": {"image": "data:image/jpeg;base64,QUJD"}}
            return {"ok": False, "hata": "bilinmeyen işlem"}

    rapor = await design.measure("https://m.test/", chrome=_Chrome())

    assert rapor.source.startswith("Fusion Browser")
    assert [page["url"] for page in rapor.pages] == ["https://m.test/", "https://m.test/erkek"]
    assert rapor.pages[0]["_screenshot_bytes"] == b"ABC"
    assert [islem for islem, _ in cagrilar].count("design") == 2


async def test_eklenti_yanit_vermezse_olcum_bassiz_tarayiciyla_surer(monkeypatch):
    class _Kopuk:
        async def invoke(self, islem: str, veri: dict) -> dict:
            raise ConnectionError("Chrome eklentisi bağlı değil.")

    async def _bassiz(url, extra):
        return design.DesignReport(source="başsız Chromium", pages=[{"url": url}])

    monkeypatch.setattr(design, "_measure_playwright", _bassiz)

    rapor = await design.measure("https://m.test/", chrome=_Kopuk())

    assert rapor.source == "başsız Chromium"


@pytest.mark.parametrize(
    ("metin", "beklenen"),
    [
        ("3.899,00 TL", (3899.0, "TRY")),
        ("7.999,00 ₺", (7999.0, "TRY")),
        ("$1,299.50", (1299.5, "USD")),
        ("1299 TL", (1299.0, "TRY")),
        ("12,5 €", (12.5, "EUR")),
        ("fiyat yok", (None, "")),
    ],
)
def test_fiyat_metni_sayi_ve_para_birimine_cozulur(metin, beklenen):
    """Ölçüldü (10. kabul koşusu): model "7.499,00 TL"yi 749900 dolar yaptı."""
    assert design.parse_price(metin) == beklenen
