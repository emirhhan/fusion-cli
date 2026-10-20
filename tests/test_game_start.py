"""Başlangıç kapısı gerçek CSS tıklanabilirliğini ve durum geçişini ölçer."""

from __future__ import annotations

import pytest

from fusion_cli.tools.game_start import start_game

_STATE = "() => JSON.stringify(window.__GAME_STATE__())"


@pytest.mark.parametrize(
    ("style", "handler", "expected_problem"),
    [
        ("#ui{pointer-events:none}button{pointer-events:auto}", "s.state='playing'", False),
        ("#ui{pointer-events:none}", "s.state='playing'", True),
        ("#cover{position:fixed;inset:0;z-index:2}", "s.state='playing'", True),
        ("", "button.hidden=true", True),
        ("", "s.state='playing'", False),
        ("", "s.tick++", True),
    ],
    ids=[
        "child-auto",
        "inherited-none",
        "overlay",
        "hidden-without-start",
        "state",
        "menu-animation",
    ],
)
async def test_gercek_tiklama_ve_state_gecisi(style, handler, expected_problem):
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    cover = "<div id='cover'></div>" if "#cover" in style else ""
    source = f"""<style>{style}</style><div id='ui'><button>Başla</button></div>{cover}
    <script>const s={{state:'menu',tick:0}};const button=document.querySelector('button');
    button.onclick=()=>{{{handler}}};window.__GAME_STATE__=()=>s;</script>"""
    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(source)
            report = await start_game(page, settle_ms=20, timeout_ms=250, state_script=_STATE)
            assert report.has_button
            assert bool(report.problems) is expected_problem
            if not expected_problem:
                assert await page.evaluate("s.state") == "playing"
        finally:
            await browser.close()


_MENU_GAME = """<style>body{{margin:0}}canvas{{display:block;width:100vw;height:100vh}}
#start-screen{{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}}
{rule}</style><canvas></canvas><div id='start-screen'><button>Başla</button></div>
<script>const s={{state:'menu'}};document.querySelector('button').onclick=()=>{{
s.state='playing';document.getElementById('start-screen').classList.add('hidden')}};
window.__GAME_STATE__=()=>s;</script>"""


@pytest.mark.parametrize(
    ("rule", "expected_problem"),
    [("", True), ("#start-screen.hidden{display:none}", False)],
    ids=["menu-kaldi", "menu-gizlendi"],
)
async def test_durum_degisse_de_menu_ekrani_ortuyorsa_kalir(rule, expected_problem):
    """dalga44: state 'playing' oldu ama `.hidden` kuralı yok, menü oyunu örttü."""
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 800, "height": 600})
            await page.set_content(_MENU_GAME.format(rule=rule))
            report = await start_game(page, settle_ms=20, timeout_ms=250, state_script=_STATE)
            assert bool(report.problems) is expected_problem
            if expected_problem:
                assert "menü ekranda kaldı" in report.problems[0]
        finally:
            await browser.close()


@pytest.mark.parametrize("attribute", ["hidden", "disabled"])
async def test_gizli_ve_devredisi_basla_basari_sayilmaz(attribute):
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as driver:
        browser = await driver.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(
                f"<button {attribute} onclick=\"s.state='playing'\">Başla</button>"
                "<script>const s={state:'menu'};window.__GAME_STATE__=()=>s;</script>"
            )
            report = await start_game(page, settle_ms=20, timeout_ms=250, state_script=_STATE)
            assert await page.evaluate("s.state") == "menu"
            if attribute == "hidden":
                assert not report.has_button
            else:
                assert report.has_button and report.problems
        finally:
            await browser.close()


def test_oyun_becerisi_kacis_bolunme_ve_restart_dersini_tam_enjekte_eder():
    from fusion_cli.engines.agent.expertise import expertise_hint

    hint = expertise_hint("HTML canvas oyun yap")
    assert hint is not None
    for lesson in ("alive → resolved", "idempotent", "Bölünmede", "restart", "Masaüstüne"):
        assert lesson in hint
