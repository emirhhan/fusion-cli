"""Üzerine gelince açılan menü panelleri betiksiz kopyada saf CSS ile açılır."""

from __future__ import annotations

import asyncio
import re

import pytest

from fusion_cli.tools.site_hover import HoverPanel, hover_css


def _panel(key: str, **fields: str) -> HoverPanel:
    varsayilan = {"text": key, "display": "flex", "opacity": "1", "transform": "none"}
    return HoverPanel(key=key, **{**varsayilan, **fields})


def test_panel_tetikleyici_ya_da_kendi_uzerindeyken_gorunur():
    css = hover_css((_panel("0"),))

    assert 'body:has([data-kopya-ac="0"]:hover) [data-kopya-panel="0"]' in css
    assert 'body [data-kopya-panel="0"]:hover' in css
    assert "visibility:hidden!important" in css
    assert "transition:visibility 0s linear 0.25s" in css


def test_alt_panel_uzerindeyken_ust_panel_acik_kalir():
    css = hover_css((_panel("0"), _panel("0-1", parent="0")))

    assert 'body:has([data-kopya-ust="0"]:hover) [data-kopya-panel="0"]' in css


def test_konumlu_panelin_yerlesimi_hep_uygulanir_yalniz_gorunurlugu_degisir():
    """display:none gecikmesiz dönerse fare alt panele varmadan kutu yok olur."""
    css = hover_css((_panel("0-0", position="absolute", left="394px", top="0px", width="390px"),))

    yerlesim = re.search(r'\n\[data-kopya-panel="0-0"\]\{([^}]*)\}', css)
    assert yerlesim is not None
    assert "position:absolute!important" in yerlesim.group(1)
    assert "left:394px!important" in yerlesim.group(1)
    assert "visibility" not in yerlesim.group(1)


def test_panel_yoksa_css_de_yok():
    assert hover_css(()) == ""


_MENU = """<!doctype html><html><head><style>
body{margin:0;font:16px sans-serif} header{position:relative;height:40px}
header a{display:inline-block;padding:10px 20px}
.mega{position:absolute;top:40px;left:0;width:300px;display:flex;background:#eee}
.alt{width:200px;background:#ccc}
</style></head><body><header><nav>
<a href="/erkek" id="erkek">ERKEK</a><a href="/kadin" id="kadin">KADIN</a></nav>
<div class="mega" id="m0" style="visibility:hidden"><ul class="liste">
<li><a href="#">AYAKKABI<svg width="8" height="8"></svg></a></li>
<li><a href="#">GİYİM<svg width="8" height="8"></svg></a></li></ul>
<div class="alt" id="alt" style="display:none"></div></div>
<div class="mega" id="m1" style="visibility:hidden"><p>kadın</p><p>yeni</p><p>indirim</p></div>
</header><main style="height:600px">içerik</main>
<script>
const show=(id)=>{for(const m of document.querySelectorAll('.mega'))m.style.visibility=
  m.id===id?'visible':'hidden';};
document.getElementById('erkek').onmouseenter=()=>show('m0');
document.getElementById('kadin').onmouseenter=()=>show('m1');
document.querySelector('header').onmouseleave=()=>show('');
const alt=document.getElementById('alt');
for(const li of document.querySelectorAll('#m0 li')){li.onmouseenter=()=>{
  alt.style.display='block';alt.innerHTML='<p>'+li.textContent+'-1</p><p>x</p><p>y</p>';};}
</script></body></html>"""


async def _capture_and_copy(page_url: str, tarayici: object) -> str:
    from fusion_cli.tools.site_capture import CAPTURE_SCRIPT
    from fusion_cli.tools.site_hover import capture_hover_panels

    page = await tarayici.new_page(viewport={"width": 800, "height": 600})  # type: ignore[attr-defined]
    await page.goto(page_url)
    panels = await capture_hover_panels(page)
    veri = await page.evaluate(CAPTURE_SCRIPT.read_text(encoding="utf-8"))
    await page.close()
    return (
        f"<!doctype html><html><head><style>{veri['css']}\n{hover_css(panels)}</style>"
        f"</head><body>{veri['header']}{veri['main']}</body></html>"
    )


async def _hover_states(tmp_path: object) -> dict[str, str]:
    from playwright.async_api import async_playwright

    kaynak = tmp_path / "kaynak.html"  # type: ignore[operator]
    kaynak.write_text(_MENU, encoding="utf-8")
    async with async_playwright() as p:
        tarayici = await p.chromium.launch()
        kopya = tmp_path / "kopya.html"  # type: ignore[operator]
        kopya.write_text(await _capture_and_copy(kaynak.as_uri(), tarayici), encoding="utf-8")
        page = await tarayici.new_page(viewport={"width": 800, "height": 600})
        await page.goto(kopya.as_uri())
        gorunur = (
            '(k)=>{const e=document.querySelector(`[data-kopya-panel="${k}"]`);'
            "return e?getComputedStyle(e).visibility+':'+e.textContent.trim():'yok'}"
        )
        durum = {"betik": str(await page.evaluate("document.scripts.length"))}
        durum["bos"] = await page.evaluate(gorunur, "0")
        merkez = (
            '(k)=>{const r=document.querySelector(`[data-kopya-ac="${k}"]`)'
            ".getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]}"
        )
        ex, ey = await page.evaluate(merkez, "0")
        await page.mouse.move(ex, ey)
        durum["erkek"] = await page.evaluate(gorunur, "0")
        gx, gy = await page.evaluate(merkez, "0-1")
        await page.mouse.move(ex, gy, steps=4)
        await page.mouse.move(gx, gy, steps=4)
        durum["giyim"] = await page.evaluate(gorunur, "0-1")
        await page.mouse.move(400, 60, steps=6)
        await page.wait_for_timeout(100)
        durum["alt_icinde"] = await page.evaluate(gorunur, "0-1")
        durum["ust_alt_icinde"] = await page.evaluate(gorunur, "0")
        await tarayici.close()
    return durum


def test_menu_ve_alt_menu_betiksiz_kopyada_acilir(tmp_path):
    """sneaksup: ERKEK > GİYİM paneli betikle açılıyordu; kopyada hiç açılmıyordu."""
    playwright = pytest.importorskip("playwright.async_api")
    try:
        durum = asyncio.run(_hover_states(tmp_path))
    except playwright.Error as hata:
        pytest.skip(f"tarayıcı yok: {hata}")

    assert durum["betik"] == "0"
    assert durum["bos"].startswith("hidden")
    assert durum["erkek"].startswith("visible")
    assert durum["giyim"] == "visible:GİYİM-1xy"
    assert durum["alt_icinde"].startswith("visible")
    assert durum["ust_alt_icinde"].startswith("visible")
