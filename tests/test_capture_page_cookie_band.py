"""capture_page.js çerez bandı sezgisi: yalnız gerçek bantlar kopyadan çıkarılır (Z1-63).

Ölçüldü (30 Ekim): sabit/yapışkan ve metninde "çerez|cookie" geçen HER öğe siliniyordu; içinde
"Çerez politikası" bağlantısı olan mobil sekme çubuğu ve uzun sabit sohbet kutusu da gidiyordu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "src/fusion_cli/tools/assets/capture_page.js"
SAYFA = (
    "<html><body><main>Merhaba</main><footer>son</footer>"
    '<div id="banner" style="position:fixed;bottom:0">Çerez tercihleri: kabul et</div>'
    '<div id="tabs" role="tablist" style="position:fixed;bottom:40px">'
    '<a href="/a">Ana sayfa</a><a href="/b">Çerez politikası</a></div>'
    '<div id="chat" style="position:fixed;right:0;top:0">'
    f"Destek: {'uzun sohbet ' * 120} cookie</div>"
    "</body></html>"
)


@pytest.mark.asyncio
async def test_yalniz_gercek_cerez_bandi_cikarilir() -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    try:
        async with playwright_api.async_playwright() as oynatici:
            browser = await oynatici.chromium.launch()
            try:
                page = await browser.new_page()
                await page.set_content(SAYFA)
                sonuc = await page.evaluate(SCRIPT.read_text(encoding="utf-8"))
            finally:
                await browser.close()
    except Exception as error:  # tarayıcı yoksa test atlanır
        pytest.skip(f"Chromium çalıştırılamadı: {error}")
    govde = sonuc["main"]
    assert 'id="banner"' not in govde
    assert 'id="tabs"' in govde
    assert 'id="chat"' in govde
