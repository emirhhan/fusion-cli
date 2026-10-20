"""Gerçek DOM: textarea boş innerText yerine value alanından okunur."""

from __future__ import annotations

from playwright.async_api import async_playwright

from fusion_cli.providers.web_browser import _editor_icerigi, _fill_editor


async def test_textarea_and_contenteditable_delivery_use_actual_dom_value() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(
                '<textarea id="prompt"></textarea><div id="rich" contenteditable="true"></div>'
            )
            text = "Fusion görev metni\nSon satır korunur."
            textarea = page.locator("#prompt")
            await textarea.fill(text)
            assert await _editor_icerigi(textarea) == text
            await _fill_editor(textarea, text)
            assert await textarea.input_value() == text
            rich = page.locator("#rich")
            await _fill_editor(rich, text)
            assert await _editor_icerigi(rich) == text
        finally:
            await browser.close()
