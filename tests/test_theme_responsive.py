"""Yakalanmış responsive varyantların tek etkin tema ağacına aktarılması."""

from __future__ import annotations

import re

import pytest

from fusion_cli.tools.site_capture import CapturedPage, SiteCapture
from fusion_cli.tools.site_responsive import CapturedVariant
from fusion_cli.tools.woo_theme import THEME_URI, ThemeFiles, write_theme


def _capture() -> SiteCapture:
    def variant(width: int, label: str, query: str | None) -> CapturedVariant:
        return CapturedVariant(
            width,
            844,
            f'<header><nav><a id="nav-link" href="#end">{label}</a></nav></header>',
            f'<main id="hero"><img src="https://source.test/{label}.svg">'
            '<section style="overflow:hidden;max-width:100%"><div><div><div>'
            '<div style="width:5000px;display:flex">'
            f'<div class="swiper-slide" style="flex:0 0 {150 if query else 250}px">'
            "Kart</div></div></div></div></div></section></main>",
            '<footer id="end">Alt</footer>',
            40 if query else 60,
            f"body{{margin:0}} header{{height:{40 if query else 60}px}} "
            "img{width:100%;max-width:100%} main{height:1200px}",
            label,
            media_query=query,
        )

    wide = variant(1440, "desktop", None)
    mobile = variant(390, "mobile", "(max-width: 768px)")
    page = CapturedPage(
        "https://source.test",
        "",
        "tr",
        "",
        wide.header,
        wide.main,
        wide.footer,
        header_offset=60,
        variants=(wide, mobile),
    )
    return SiteCapture(
        (page,),
        wide.css,
        {
            "https://source.test/desktop.svg": "assets/desktop.svg",
            "https://source.test/mobile.svg": "assets/mobile.svg",
        },
    )


def _fixture(theme: ThemeFiles, main: str | None = None):
    (theme.folder / "assets").mkdir()
    for name in ("desktop", "mobile"):
        (theme.folder / "assets" / f"{name}.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"></svg>'
        )
    document = (theme.folder / "header.php").read_text()
    document += main if main is not None else (theme.folder / "front-page.php").read_text()
    document += (theme.folder / "footer.php").read_text()
    document = document.replace(THEME_URI, theme.folder.as_uri() + "/")
    document = re.sub(r"<\?php.*?\?>", "", document, flags=re.S)
    document = document.replace('<meta charset="">', '<meta charset="utf-8">')
    document = document.replace(
        "</head>", '<link id="kopya-css" rel="stylesheet" href="kopya.css"></head>'
    )
    document = document.replace("</body>", '<script src="responsive.js"></script></body>')
    path = theme.folder / "fixture.html"
    path.write_text(document)
    return path


def test_verified_variant_tema_runtime_ile_aktarilir(tmp_path):
    theme = write_theme(_capture(), tmp_path, "https://source.test")
    assert "responsive.js" in theme.files
    assert theme.responsive_paths == ("https://source.test",)
    header = (theme.folder / "header.php").read_text()
    assert "<template" in header and "data-fusion-query" in header
    assert "mobile.svg" in (theme.folder / "front-page.php").read_text()
    assert "wp_enqueue_script" in (theme.folder / "functions.php").read_text()


def test_tek_etkin_dom_css_checkout_odak_ve_scroll_korunur(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    theme = write_theme(_capture(), tmp_path, "https://source.test")
    checkout = (
        '<main id="checkout"><input id="billing" name="billing" value="">'
        '<div style="height:1600px"></div></main>'
    )
    path = _fixture(theme, checkout)
    with playwright.sync_playwright() as session:
        browser = session.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(path.as_uri())
            page.locator("#billing").fill("Kalıcı değer")
            page.locator("#billing").focus()
            page.evaluate(
                "window.savedCheckout=document.querySelector('#checkout');scrollTo(0,300)"
            )
            for width in (390, 767, 769, 1440):
                page.set_viewport_size({"width": width, "height": 900})
                expected = "mobile" if width <= 768 else "desktop"
                page.wait_for_function(
                    "label => document.querySelector('#nav-link').textContent === label",
                    arg=expected,
                )
                assert page.locator("#nav-link").count() == 1
                assert page.locator("#end").count() == 1
                assert page.locator("#billing").input_value() == "Kalıcı değer"
                assert page.evaluate("document.activeElement.id") == "billing"
                assert page.evaluate("savedCheckout===document.querySelector('#checkout')")
                assert page.evaluate("scrollY") == 300
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert page.locator("style[data-fusion-active-css]").count() == 1
                assert page.locator("#kopya-css").evaluate("node => node.disabled")
        finally:
            browser.close()


def test_ana_sayfa_mobil_varlik_ve_odak_tek_agacta_korunur(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    theme = write_theme(_capture(), tmp_path, "https://source.test")
    path = _fixture(theme)
    with playwright.sync_playwright() as session:
        browser = session.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(path.as_uri())
            page.locator("#nav-link").focus()
            for width in (390, 767, 769, 1440):
                page.set_viewport_size({"width": width, "height": 900})
                expected = "mobile" if width <= 768 else "desktop"
                page.wait_for_function(
                    'value => document.querySelector("#hero img").src.endsWith(value)',
                    arg=f"{expected}.svg",
                )
                assert page.get_by_role("link", name=expected).count() == 1
                assert page.locator("#hero").count() == 1
                assert page.evaluate("document.activeElement.id") == "nav-link"
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert page.locator("header").evaluate(
                    "node => node.getBoundingClientRect().height"
                ) == (40 if expected == "mobile" else 60)
                assert page.locator(".swiper-slide").evaluate(
                    "node => node.getBoundingClientRect().width"
                ) == (150 if expected == "mobile" else 250)
                assert (
                    page.locator("body").evaluate("node => getComputedStyle(node).overflowX")
                    == "visible"
                )
                assert page.locator("#hero img").evaluate(
                    "img => img.complete && img.naturalWidth > 0"
                )
            assert errors == []
        finally:
            browser.close()


def test_dogrulanmayan_varyant_tema_aktarildi_sayilmaz(tmp_path):
    from dataclasses import replace

    capture = _capture()
    page = capture.pages[0]
    variants = tuple(replace(item, media_query=None) for item in page.variants)
    capture = replace(capture, pages=(replace(page, variants=variants),))
    theme = write_theme(capture, tmp_path, "https://source.test")
    assert theme.responsive_paths == ()
    assert "responsive.js" not in theme.files


def test_odak_karsiligi_yoksa_sessiz_basarili_sayilmaz(tmp_path):
    from dataclasses import replace

    playwright = pytest.importorskip("playwright.sync_api")
    capture = _capture()
    original = capture.pages[0]
    wide, mobile = original.variants
    mobile = replace(mobile, header='<header><a id="other-link" href="#end">mobile</a></header>')
    capture = replace(capture, pages=(replace(original, variants=(wide, mobile)),))
    theme = write_theme(capture, tmp_path, "https://source.test")
    path = _fixture(theme)
    with playwright.sync_playwright() as session:
        browser = session.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            warnings = []
            page.on(
                "console",
                lambda message: (
                    warnings.append(message.text) if message.type == "warning" else None
                ),
            )
            page.goto(path.as_uri())
            page.locator("#nav-link").focus()
            page.set_viewport_size({"width": 390, "height": 900})
            page.wait_for_function("document.documentElement.dataset.fusionFocusLost === 'true'")
            assert any("odak karşılığı bulunamadı" in message for message in warnings)
            assert page.locator("#other-link").count() == 1
        finally:
            browser.close()


def test_summary_yalniz_aktarilan_yolun_pending_bildirimini_dusurur(tmp_path):
    from dataclasses import replace

    from fusion_cli.engines.agent.clone_tools import _summary

    pending = "Viewport varyantları yakalandı; responsive tema aktarımı henüz uygulanmadı."
    capture = _capture()
    primary = replace(capture.pages[0], responsive_problems=(pending,))
    secondary = replace(primary, url="https://source.test/category")
    capture = replace(capture, pages=(primary, secondary), problems=(pending, pending))
    theme = write_theme(capture, tmp_path, "https://source.test")
    summary = _summary(capture, theme, [], list(capture.problems), tmp_path)
    assert summary.count(pending) == 1
    assert "diğer kaynak etkileşimleri aktarılmadı" in summary


def test_summary_dogrulanmayan_yolda_pending_ve_bulgu_korunur(tmp_path):
    from dataclasses import replace

    from fusion_cli.engines.agent.clone_tools import _summary

    pending = "Viewport varyantları yakalandı; responsive tema aktarımı henüz uygulanmadı."
    capture = _capture()
    original = capture.pages[0]
    variants = tuple(replace(item, media_query=None) for item in original.variants)
    primary = replace(original, variants=variants, responsive_problems=(pending,))
    capture = replace(
        capture, pages=(primary,), problems=(pending, "Kaynak menü olayı doğrulanamadı.")
    )
    theme = write_theme(capture, tmp_path, "https://source.test")
    summary = _summary(capture, theme, [], list(capture.problems), tmp_path)
    assert pending in summary and "Kaynak menü olayı doğrulanamadı." in summary


def _multi_capture() -> SiteCapture:
    from dataclasses import replace

    from fusion_cli.tools.site_responsive import CapturedTransition

    capture = _capture()
    wide, mobile = capture.pages[0].variants
    mobile = replace(mobile, media_query=None)
    tablet = replace(
        mobile,
        width=601,
        signature="tablet",
        header=mobile.header.replace("mobile", "tablet"),
        main=mobile.main.replace("mobile.svg", "tablet.svg"),
    )
    first = CapturedTransition(
        "(max-width: 600px)", replace(mobile, width=600), tablet, ("(max-width: 600px)",)
    )
    second = CapturedTransition(
        "(max-width: 1000px)",
        replace(tablet, width=1000),
        replace(wide, width=1001),
        ("(max-width: 1000px)",),
    )
    primary = replace(
        capture.pages[0],
        variants=(wide, mobile),
        transitions=(first, second),
        responsive_problems=(
            "Çoklu kaynak genişlik geçişleri yakalandı; çoklu bölge tema aktarımı desteklenmiyor.",
        ),
    )
    return replace(
        capture,
        pages=(primary,),
        assets={**capture.assets, "https://source.test/tablet.svg": "assets/tablet.svg"},
    )


def test_multisource_verified_chain_is_transferred_with_source_predicates(tmp_path):
    theme = write_theme(_multi_capture(), tmp_path, "https://source.test")
    assert "responsive.js" in theme.files
    assert theme.responsive_paths == ("https://source.test",)
    header = (theme.folder / "header.php").read_text()
    assert "data-fusion-conditions" in header
    assert "(max-width: 600px)" in header and "(max-width: 1000px)" in header
    assert "tablet.svg" in (theme.folder / "front-page.php").read_text()


def test_disconnected_source_transition_chain_is_not_silently_transferred(tmp_path):
    from dataclasses import replace

    capture = _multi_capture()
    page = capture.pages[0]
    first, second = page.transitions
    second = replace(second, left=replace(second.left, signature="unobserved-js-regime"))
    capture = replace(capture, pages=(replace(page, transitions=(first, second)),))
    theme = write_theme(capture, tmp_path, "https://source.test")
    assert "responsive.js" not in theme.files
    assert theme.responsive_paths == ()
    assert any("bağlı viewport" in problem for problem in theme.problems)


@pytest.mark.parametrize("has_checkout", [False, True])
def test_multi_runtime_exact_boundaries_local_assets_unique_ids_and_checkout_state(
    tmp_path, has_checkout
):
    playwright = pytest.importorskip("playwright.sync_api")
    theme = write_theme(_multi_capture(), tmp_path, "https://source.test")
    main = (
        '<main id="checkout"><input id="billing"><div style="height:1600px"></div></main>'
        if has_checkout
        else None
    )
    path = _fixture(theme, main)
    (theme.folder / "assets/tablet.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"></svg>'
    )
    with playwright.sync_playwright() as session:
        browser = session.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(path.as_uri())
            if has_checkout:
                page.locator("#billing").fill("Kalıcı")
                page.locator("#billing").focus()
                page.evaluate(
                    'window.savedCheckout=document.querySelector("#checkout");scrollTo(0,300)'
                )
            else:
                page.locator("#nav-link").focus()
            for width in (390, 599, 600, 601, 999, 1000, 1001, 1440):
                expected = "mobile" if width <= 600 else "tablet" if width <= 1000 else "desktop"
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_function(
                    'label => document.querySelector("#nav-link").textContent === label',
                    arg=expected,
                )
                assert page.locator("#nav-link").count() == page.locator("#end").count() == 1
                assert page.locator("style[data-fusion-active-css]").count() == 1
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert (
                    page.locator("body").evaluate("node => getComputedStyle(node).overflowX")
                    == "visible"
                )
                if has_checkout:
                    assert page.locator("#billing").input_value() == "Kalıcı"
                    assert page.evaluate('savedCheckout===document.querySelector("#checkout")')
                    assert page.evaluate("document.activeElement.id") == "billing"
                    assert page.evaluate("scrollY") == 300
                else:
                    assert page.evaluate("document.activeElement.id") == "nav-link"
                    assert page.locator("#hero img").evaluate(
                        "image => image.complete && image.naturalWidth > 0"
                    )
                    assert (
                        page.locator("#hero img").get_attribute("src").endswith(expected + ".svg")
                    )
                    assert page.locator("#hero").count() == 1
            assert errors == []
        finally:
            browser.close()


def test_summary_resolves_only_transferred_primary_multiregion_pending(tmp_path):
    from dataclasses import replace

    from fusion_cli.engines.agent.clone_tools import _summary

    capture = _multi_capture()
    primary = capture.pages[0]
    secondary = replace(primary, url="https://source.test/category")
    pending = primary.responsive_problems[0]
    capture = replace(
        capture,
        pages=(primary, secondary),
        problems=(pending, pending, "Kaynak JavaScript koşulu desteklenmiyor."),
    )
    theme = write_theme(capture, tmp_path, "https://source.test")
    summary = _summary(capture, theme, [], list(capture.problems), tmp_path)
    assert summary.count(pending) == 1
    assert "Kaynak JavaScript koşulu desteklenmiyor." in summary
    assert "piksel geometrisi kanıtı değildir" in summary
