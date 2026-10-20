"""Yüklenen sprite ile gerçek çizim çağrısı birbirinden ayrılır."""

from __future__ import annotations

import pytest

from fusion_cli.tools.game_assets import ASSET_INIT, read_asset_usage

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
    '<rect width="16" height="16" fill="red"/></svg>'
)


@pytest.mark.parametrize("attribute", [False, True])
async def test_yuklenen_ama_cizilmeyen_sprite_kullanim_kaniti_degildir(attribute):
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.route(
                "https://oyun.test/**",
                lambda route: route.fulfill(content_type="image/svg+xml", body=_SVG),
            )
            await page.add_init_script(ASSET_INIT)
            await page.goto("about:blank")
            await page.evaluate(
                """async attribute => {
                document.body.innerHTML='<canvas width="100" height="100"></canvas>';
                const images=await Promise.all(['player','enemy','boss'].map(name =>
                  new Promise(resolve => {const img=new Image();img.onload=()=>resolve(img);
                    const src='https://oyun.test/assets/'+name+'.svg?cache=1';
                    if(attribute) img.setAttribute('src',src); else img.src=src;})));
                document.querySelector('canvas').getContext('2d').drawImage(images[0],0,0);
            }""",
                attribute,
            )
            report = await read_asset_usage(page)
        finally:
            await browser.close()

    assert report.loaded == (
        "https://oyun.test/assets/boss.svg",
        "https://oyun.test/assets/enemy.svg",
        "https://oyun.test/assets/player.svg",
    )
    assert report.drawn == ("https://oyun.test/assets/player.svg",)
    assert report.unobserved == (
        "https://oyun.test/assets/boss.svg",
        "https://oyun.test/assets/enemy.svg",
    )
    assert "henüz" in report.summary() and "görünürlük" in report.summary()


async def test_sonradan_dogan_sprite_cizilince_gozlemlenmis_olur():
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.route(
                "https://oyun.test/**", lambda r: r.fulfill(content_type="image/svg+xml", body=_SVG)
            )
            await page.add_init_script(ASSET_INIT)
            await page.goto("about:blank")
            await page.evaluate("""async () => {
              document.body.innerHTML='<canvas width="100" height="100"></canvas>';
              window.boss=await new Promise(resolve => {const img=new Image();
                img.onload=()=>resolve(img);img.src='https://oyun.test/assets/boss.svg';});
            }""")
            assert (await read_asset_usage(page)).unobserved == (
                "https://oyun.test/assets/boss.svg",
            )
            await page.evaluate(
                "document.querySelector('canvas').getContext('2d').drawImage(window.boss,0,0)"
            )
            assert (await read_asset_usage(page)).unobserved == ()
        finally:
            await browser.close()


async def test_bozuk_resim_yuklenmis_ve_cizilmis_sayilmaz():
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.route("https://oyun.test/**", lambda r: r.fulfill(status=404, body="yok"))
            await page.add_init_script(ASSET_INIT)
            await page.goto("about:blank")
            await page.evaluate("""async () => {
              const img=await new Promise(resolve => {const img=new Image();
                img.onerror=()=>resolve(img);img.src='https://oyun.test/missing.svg';});
              document.body.innerHTML='<canvas></canvas>';
              try {document.querySelector('canvas').getContext('2d').drawImage(img,0,0);}
              catch(e) {}
            }""")
            report = await read_asset_usage(page)
            assert report.loaded == () and report.drawn == ()
        finally:
            await browser.close()
