"""Kaynak medya koşullarının viewport varyantına güvenilir bağlanması."""

from __future__ import annotations

from fusion_cli.tools.site_responsive import width_conditions


def test_yalniz_kaynaktaki_px_genislik_kosullari_esikleriyle_korunur():
    conditions = width_conditions(
        (
            "(max-width: 768px)",
            "screen and (min-width: 900px)",
            "(prefers-reduced-motion: reduce)",
            "(max-width: 48em)",
        )
    )
    assert [(item.query, item.boundary) for item in conditions] == [
        ("(max-width: 768px)", 768),
        ("screen and (min-width: 900px)", 900),
    ]


def test_bilesik_ve_aralik_kosullari_tahminle_basitlesmez():
    assert (
        width_conditions(
            (
                "(max-width: 768px) and (orientation: portrait)",
                "(min-width: 400px) and (max-width: 800px)",
                "(width <= 700px)",
            )
        )
        == ()
    )


async def test_esik_iki_yaninda_kaynak_dom_gecisi_dogrulanmadan_sorgu_verilmez():
    from fusion_cli.tools.site_responsive import CapturedVariant, verify_variants

    def variant(width: int, signature: str) -> CapturedVariant:
        return CapturedVariant(width, 900, "", "", "", 0, "", signature, ("(max-width: 768px)",))

    async def capture(width: int, height: int) -> CapturedVariant:
        return variant(width, "ara")

    result = await verify_variants((variant(1440, "masaustu"), variant(390, "mobil")), capture)
    assert result.variants[-1].media_query is None
    assert any("tahmin edilmedi" in problem for problem in result.problems)


async def test_kaynak_cssdisi_js_esigi_css_esigine_yanlis_baglanmaz():
    from fusion_cli.tools.site_responsive import CapturedVariant, verify_variants

    def variant(width: int) -> CapturedVariant:
        return CapturedVariant(
            width,
            900,
            "",
            "",
            "",
            0,
            "",
            "mobil" if width < 600 else "masaustu",
            ("(max-width: 768px)",),
        )

    async def capture(width: int, height: int) -> CapturedVariant:
        return variant(width)

    result = await verify_variants((variant(1440), variant(390)), capture)
    assert result.variants[-1].media_query is None
    assert any("tahmin edilmedi" in problem for problem in result.problems)


async def test_her_viewport_dom_css_ve_mobil_gorseli_yakalanir(tmp_path, monkeypatch):
    import pytest

    from fusion_cli.tools import site_capture

    playwright = pytest.importorskip("playwright.async_api")
    source = tmp_path / "index.html"
    source.write_text(
        """<!doctype html><style>
    @media(max-width:768px){header{height:80px}}
    @media(min-width:769px){header{height:40px}}
    </style><header></header><main><img></main><footer>Alt</footer>
    <script>const mobile=matchMedia('(max-width:768px)').matches;
    document.querySelector('header').innerHTML=mobile
      ?'<nav id="mobile">Telefon</nav>':'<nav id="desktop">Masaüstü</nav>';
    document.querySelector('img').src=mobile?'mobile.svg':'desktop.svg';
    </script>""",
        encoding="utf-8",
    )
    for name in ("mobile.svg", "desktop.svg"):
        (tmp_path / name).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"></svg>',
            encoding="utf-8",
        )

    async def scroll(page):
        return None

    monkeypatch.setattr(site_capture, "_scroll", scroll)
    monkeypatch.setattr(site_capture, "SETTLE_MS", 0)
    async with playwright.async_playwright() as session:
        browser = await session.chromium.launch()
        try:
            page, css, blocked = await site_capture._capture_one(
                browser, source.as_uri(), site_capture.CAPTURE_SCRIPT.read_text(encoding="utf-8")
            )
        finally:
            await browser.close()
    assert tuple(variant.width for variant in page.variants) == (1440, 390)
    desktop, mobile = page.variants
    assert 'id="desktop"' in desktop.header
    assert 'id="mobile"' in mobile.header
    assert mobile.media_query == "(max-width: 768px)"
    assert "mobile.svg" in mobile.main and "desktop.svg" in desktop.main
    assert {390, 768, 769, 1440} <= page.screenshots.keys()
    from io import BytesIO

    from PIL import Image

    assert Image.open(BytesIO(page.screenshots[390])).size == (mobile.width, mobile.height)
    assert Image.open(BytesIO(page.screenshots[1440])).size == (desktop.width, desktop.height)
    assert "@media" in mobile.css and css == desktop.css and not blocked
    assert "<script" not in mobile.main
    assert any("henüz uygulanmadı" in problem for problem in page.responsive_problems)


def test_mobil_varliklar_indirmeye_css_yazi_tiplerinden_once_girer():
    from fusion_cli.tools.site_capture import CapturedPage, capture_asset_urls, localize
    from fusion_cli.tools.site_responsive import CapturedVariant

    mobile = CapturedVariant(
        390,
        844,
        "",
        '<picture><source srcset="https://example.com/mobile.webp"></picture>',
        "",
        40,
        "body{background:url(https://example.com/mobile-bg.webp)}",
        "mobil",
    )
    page = CapturedPage(
        "https://example.com",
        "",
        "tr",
        "",
        "",
        '<img src="https://example.com/desktop.webp">',
        "",
        variants=(mobile,),
    )
    addresses = capture_asset_urls((page,), "a{src:url(https://example.com/font.woff)}", page.url)
    assert addresses == [
        "https://example.com/desktop.webp",
        "https://example.com/mobile.webp",
        "https://example.com/mobile-bg.webp",
        "https://example.com/font.woff",
    ]
    mapping = {address: f"assets/{index}.webp" for index, address in enumerate(addresses)}
    assert "https://" not in localize(mobile.main, mapping, "T/")
    assert "https://" not in localize(mobile.css, mapping, "T/")


async def test_exact_max_boundary_js_offbyone_eslesmesini_reddeder():
    from fusion_cli.tools.site_responsive import CapturedVariant, verify_variants

    def variant(width):
        return CapturedVariant(
            width,
            900,
            "",
            "",
            "",
            0,
            "",
            "mobil" if width < 768 else "masaustu",
            ("(max-width: 768px)",),
        )

    async def capture(width, height):
        return variant(width)

    result = await verify_variants((variant(1440), variant(390)), capture)
    assert result.variants[-1].media_query is None


async def test_exact_min_boundary_js_offbyone_eslesmesini_reddeder():
    from fusion_cli.tools.site_responsive import CapturedVariant, verify_variants

    def variant(width):
        return CapturedVariant(
            width,
            900,
            "",
            "",
            "",
            0,
            "",
            "mobil" if width <= 768 else "masaustu",
            ("(min-width: 768px)",),
        )

    async def capture(width, height):
        return variant(width)

    result = await verify_variants((variant(1440), variant(390)), capture)
    assert result.variants[-1].media_query is None


def test_nested_media_kosulu_orientationi_kaybetmez(tmp_path):
    import pytest

    from fusion_cli.tools.site_capture import CAPTURE_SCRIPT

    playwright = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "index.html"
    source.write_text(
        "<style>@media(orientation:portrait){@media(max-width:768px){body{color:red}}}</style><main>İçerik</main>",
        encoding="utf-8",
    )
    with playwright.sync_playwright() as session:
        browser = session.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(source.as_uri())
            values = page.evaluate(CAPTURE_SCRIPT.read_text(encoding="utf-8"))
        finally:
            browser.close()
    assert "(max-width: 768px)" not in values["mediaConditions"]
    assert "(orientation: portrait) and (max-width: 768px)" in values["mediaConditions"]
    assert width_conditions(tuple(values["mediaConditions"])) == ()


def test_picture_srcset_yakalama_secili_current_srcyi_korur(tmp_path):
    import pytest

    from fusion_cli.tools.site_capture import CAPTURE_SCRIPT, collapse_srcset

    playwright = pytest.importorskip("playwright.sync_api")
    for name in ("mobile.svg", "mobile-large.svg", "desktop.svg"):
        (tmp_path / name).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"></svg>',
            encoding="utf-8",
        )
    source = tmp_path / "index.html"
    source.write_text(
        """<main><picture><source media="(max-width:768px)"
    srcset="mobile.svg 390w, mobile-large.svg 1440w" sizes="100vw">
    <img src="desktop.svg" srcset="desktop.svg 1440w" sizes="100vw"></picture></main>""",
        encoding="utf-8",
    )
    with playwright.sync_playwright() as session:
        browser = session.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
            page.goto(source.as_uri())
            selected = page.locator("img").evaluate("img => img.currentSrc")
            assert selected.endswith("mobile.svg")
            values = page.evaluate(CAPTURE_SCRIPT.read_text(encoding="utf-8"))
            copied = collapse_srcset(values["main"])
            page.set_content(copied)
            page.wait_for_function("document.querySelector('img').complete")
            assert page.locator("img").evaluate("img => img.currentSrc") == selected
            assert "<source" not in copied and "srcset=" not in copied and "sizes=" not in copied
        finally:
            browser.close()


async def test_yukseklik_js_gecisi_ilgisiz_width_kosuluna_baglanmaz():
    from fusion_cli.tools.site_responsive import CapturedVariant, verify_variants

    def variant(width, height):
        return CapturedVariant(
            width,
            height,
            "",
            "",
            "",
            0,
            "",
            "mobil" if height < 880 else "masaustu",
            ("(max-width: 768px)",),
        )

    async def capture(width, height):
        return variant(width, height)

    result = await verify_variants((variant(1440, 900), variant(390, 844)), capture)
    assert result.variants[-1].media_query is None
    assert any("yükseklik" in problem for problem in result.problems)


def test_ters_nested_media_dis_width_saf_aday_olmaz(tmp_path):
    import pytest

    from fusion_cli.tools.site_capture import CAPTURE_SCRIPT

    playwright = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "index.html"
    source.write_text(
        "<style>@media(max-width:768px){@media(orientation:portrait){body{color:red}}}</style><main>İçerik</main>",
        encoding="utf-8",
    )
    with playwright.sync_playwright() as session:
        browser = session.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(source.as_uri())
            values = page.evaluate(CAPTURE_SCRIPT.read_text(encoding="utf-8"))
        finally:
            browser.close()
    assert "(max-width: 768px)" not in values["mediaConditions"]
    assert "(max-width: 768px) and (orientation: portrait)" in values["mediaConditions"]
    assert width_conditions(tuple(values["mediaConditions"])) == ()
