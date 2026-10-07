"""Hareket kitinin gerçek DOM yerleşimi ve geometri denetimi gerilemeleri."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "fixtures" / "remotion_kit.cjs"
HAS_NODE = shutil.which("node") is not None and (ROOT / "app/node_modules/typescript").is_dir()
pytestmark = pytest.mark.skipif(not HAS_NODE, reason="Node/React test bağımlılıkları yok")


def _run(mode: str) -> str:
    return subprocess.check_output(["node", str(RUNNER), str(ROOT), mode], text=True, timeout=30)


async def test_parallax_baslik_ve_alt_yaziyi_akis_icinde_tutar():
    browser_api = pytest.importorskip("playwright.async_api")
    html = await asyncio.to_thread(_run, "dom")
    async with browser_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            await page.set_content(html)
            title = await page.locator("#title").bounding_box()
            subtitle = await page.locator("#subtitle").bounding_box()
            assert title and subtitle
            assert subtitle["y"] >= title["y"] + title["height"]
        finally:
            await browser.close()


async def test_kart_genisligi_padding_ve_kenarligi_kapsar():
    browser_api = pytest.importorskip("playwright.async_api")
    html = await asyncio.to_thread(_run, "dom")
    async with browser_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            await page.set_content(html)
            card = await page.get_by_text("Kart", exact=True).locator("..").bounding_box()
            assert card and card["width"] <= 580
        finally:
            await browser.close()


def test_yerlesim_denetimi_tasma_cakisma_ve_bos_kareyi_yakalar():
    assert _run("geometry") == "geometri geçti"


@pytest.mark.parametrize(
    "mode", ["good", "overlap", "empty", "nested", "transform", "overflow", "dim", "delayed"]
)
async def test_render_kapisi_gercek_dom_hatalarini_bildirir(mode):
    browser_api = pytest.importorskip("playwright.async_api")
    html = await asyncio.to_thread(_run, "audit")
    async with browser_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.route(
                "http://kit.test/**",
                lambda route: route.fulfill(body=html, content_type="text/html"),
            )
            if mode == "good":
                await page.goto(f"http://kit.test/?mode={mode}")
                await page.get_by_text("Başlık", exact=True).wait_for()
                assert not errors
                assert await page.get_by_text("Başlık", exact=True).count() == 1
            else:
                async with page.expect_event("pageerror", timeout=5000):
                    await page.goto(f"http://kit.test/?mode={mode}")
                assert errors and "Yerleşim denetimi" in errors[0]
                expected = {
                    "overlap": "üst üste",
                    "delayed": "üst üste",
                    "nested": "üst üste",
                    "empty": "içerik yok",
                    "dim": "içerik yok",
                    "transform": "taşıyor",
                    "overflow": "taşıyor",
                }
                assert expected[mode] in errors[0]
        finally:
            await browser.close()
