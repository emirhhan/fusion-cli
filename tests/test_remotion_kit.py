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
            protocol_records = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "console",
                lambda message: (
                    protocol_records.append(message.text)
                    if message.text.startswith("FUSION_FAILURE_V1:")
                    else None
                ),
            )
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
                import json

                assert protocol_records
                proof = json.loads(protocol_records[0].split(":", 1)[1])
                assert proof["version"] == 1 and proof["families"]
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


@pytest.mark.parametrize(
    "mode",
    ["good", "oversize", "too-many", "longword", "font-delayed", "near-entrance", "near-settled"],
)
async def test_feature_scene_tek_satir_ve_dogal_yukseklik_kapisi(mode):
    browser_api = pytest.importorskip("playwright.async_api")
    html = await asyncio.to_thread(_run, "feature")

    async with browser_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.route(
                "http://feature.test/**",
                lambda route: route.fulfill(body=html, content_type="text/html"),
            )
            if mode in ("good", "font-delayed", "near-entrance", "near-settled"):
                await page.goto(f"http://feature.test/?mode={mode}")
                if mode == "font-delayed":
                    assert await page.locator("[data-fusion-feature-ready]").count() == 0
                    await page.evaluate("globalThis.__releaseFonts()")
                await page.wait_for_function(
                    "document.querySelector('[data-fusion-feature-ready]')", timeout=5000
                )
                cards = await page.locator("[data-fusion-feature-cards] > div").all()
                bounds = [await card.bounding_box() for card in cards]
                assert len(bounds) == 3 and all(bounds)
                assert len({round(box["y"]) for box in bounds}) == 1
                assert max(box["width"] for box in bounds) - min(box["width"] for box in bounds) < 1
                if mode != "near-entrance":
                    assert min(box["x"] for box in bounds) >= 120
                assert max(box["x"] + box["width"] for box in bounds) <= 1800
                assert not errors
                assert await page.locator("[data-fusion-feature-body]").evaluate_all(
                    "nodes => nodes.every(node => getComputedStyle(node).fontSize === '44px')"
                )
            else:
                async with page.expect_event("pageerror", timeout=5000):
                    await page.goto(f"http://feature.test/?mode={mode}")
                expected = "1–3" if mode == "too-many" else "sahnelere böl"
                assert any(expected in error for error in errors)
        finally:
            await browser.close()


def test_feature_scene_en_buyuk_kamera_ve_derinlik_hareketinde_guvenli():
    assert _run("feature-geometry") == "özellik geometrisi geçti"


@pytest.mark.parametrize(
    "mode",
    [
        "boundary-before",
        "boundary-after",
        "first",
        "blank",
        "offscreen",
        "offscreen-short",
        "sliver",
        "partial",
        "overlap",
        "capacity",
        "duration",
        "duplicate",
        "zero",
    ],
)
async def test_timeline_kesme_siniri_ve_ortak_kapilar(mode):
    browser_api = pytest.importorskip("playwright.async_api")
    html = await asyncio.to_thread(_run, "timeline")
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
            await page.goto(f"http://kit.test/?mode={mode}")
            await page.wait_for_timeout(250)
            if mode.startswith("boundary") or mode in ("first", "partial"):
                assert errors == []
                assert await page.locator("[data-fusion-scene]").count() == 1
                if mode in ("boundary-before", "first"):
                    assert await page.locator("[data-fusion-feature-ready]").count() == 1
                    opacity = await page.get_by_text("Fusion", exact=True).evaluate(
                        "el => {let opacity=1;for(let e=el;e;e=e.parentElement)"
                        "opacity*=Number(getComputedStyle(e).opacity);return opacity;}"
                    )
                    assert opacity >= 0.5
                else:
                    assert await page.get_by_text("Custom", exact=True).is_visible()
            else:
                assert errors
                expected = {
                    "blank": "okunabilir",
                    "offscreen": "okunabilir",
                    "offscreen-short": "okunabilir",
                    "sliver": "okunabilir",
                    "overlap": "örtüşme",
                    "capacity": "doğal metin",
                    "duration": "toplam süresi",
                    "duplicate": "benzersiz",
                    "zero": "pozitif",
                }
                assert any(expected[mode] in error for error in errors)
        finally:
            await browser.close()


@pytest.mark.parametrize("mode", ["runtime", "runtime-failure", "runtime-custom-copy"])
async def test_runtime_kaydi_gercek_kare_ve_audit_sonucunu_tasir(mode):
    import json

    browser_api = pytest.importorskip("playwright.async_api")
    html = await asyncio.to_thread(_run, "timeline")
    async with browser_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            records = []
            page.on(
                "console",
                lambda message: (
                    records.append(message.text)
                    if message.text.startswith("FUSION_RUNTIME_V1:")
                    else None
                ),
            )
            await page.route(
                "http://kit.test/**",
                lambda route: route.fulfill(body=html, content_type="text/html"),
            )
            await page.goto(f"http://kit.test/?mode={mode}")
            await page.wait_for_timeout(250)
            assert records
            record = json.loads(records[-1].split(":", 1)[1])
            assert record["composition"] == "Fusion" and record["frame"] == 0
            assert record["session"] == "new-session" and record["runtimeExecuted"]
            if mode == "runtime":
                assert record["featureReady"] and record["auditSettled"]
                assert record["activeSceneKinds"] == ["feature"]
                assert record["activeScenes"] == ["first"] and record["findings"] == []
            elif mode == "runtime-custom-copy":
                assert record["featureReady"] and record["auditSettled"]
                assert record["activeSceneKinds"] == ["custom"]
                assert record["activeScenes"] == ["copied"]
            else:
                assert record["findings"] and not record["auditSettled"]
        finally:
            await browser.close()


async def test_runtime_edilmis_onceki_kare_feature_markerini_yeniden_kullanmaz():
    import json

    browser_api = pytest.importorskip("playwright.async_api")
    html = await asyncio.to_thread(_run, "timeline")
    async with browser_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": 1920, "height": 1080})
            records = []
            page.on(
                "console",
                lambda message: (
                    records.append(message.text)
                    if message.text.startswith("FUSION_RUNTIME_V1:")
                    else None
                ),
            )
            await page.route(
                "http://kit.test/**",
                lambda route: route.fulfill(body=html, content_type="text/html"),
            )
            await page.goto("http://kit.test/?mode=runtime")
            await page.wait_for_timeout(150)
            assert records
            records.clear()
            await page.evaluate("""() => {
              Object.defineProperty(document.fonts,'ready',{configurable:true,
                value:new Promise(resolve=>{globalThis.__releaseFonts=resolve;})});
              __rerenderFrame(1);
            }""")
            await page.wait_for_timeout(100)
            assert records == []
            assert await page.locator("[data-fusion-feature-ready]").count() == 0
            await page.evaluate("__releaseFonts()")
            await page.wait_for_timeout(150)
            assert records
            record = json.loads(records[-1].split(":", 1)[1])
            assert record["frame"] == 1 and record["auditSettled"] and record["featureReady"]
        finally:
            await browser.close()
