"""Hareket becerisinin örneğini gerçek tarayıcı etkileşimleriyle doğrula."""

from __future__ import annotations

import re

import pytest

from fusion_cli.config.paths import bundled_skills_dir

SKILL = bundled_skills_dir() / "hareket" / "SKILL.md"


def _example() -> str:
    source = SKILL.read_text(encoding="utf-8")
    css = re.search(r"```css\n(.*?)```", source, re.DOTALL).group(1)
    javascript = re.search(r"```js\n(.*?)```", source, re.DOTALL).group(1)
    markup = re.search(r"```html\n(.*?)```", source, re.DOTALL)
    # Eski beceri reveal/hover sahipliğini ayıran HTML örneği vermiyordu.
    body = (
        markup.group(1)
        if markup
        else '<article class="reveal card"><button>İncele</button></article>'
    )
    return (
        "<html><head><style>body{margin:80px}.card{width:240px;padding:32px}"
        + css
        + "</style></head><body>"
        + body
        + "<script>"
        + javascript
        + "</script></body></html>"
    )


async def _wait_translation(page, lifted: bool) -> None:
    await page.wait_for_function(
        """lifted => {
          const transform = getComputedStyle(document.querySelector('.card')).transform;
          const y = transform === 'none' ? 0 : new DOMMatrix(transform).m42;
          return lifted ? y < -5.9 : Math.abs(y) < 0.05;
        }""",
        arg=lifted,
        timeout=2000,
    )


@pytest.mark.parametrize("interaction", ["hover", "keyboard", "reduce", "no-js"])
async def test_hareket_ornegi_reveal_hover_focus_ve_azaltilmis_hareket(interaction):
    browser_api = pytest.importorskip("playwright.async_api")
    async with browser_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(
                reduced_motion="reduce" if interaction == "reduce" else "no-preference",
                java_script_enabled=interaction != "no-js",
            )
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.set_content(_example())
            card = page.locator(".card")
            if interaction != "no-js":
                await page.wait_for_function(
                    "getComputedStyle(document.querySelector('.reveal')).opacity === '1'"
                )
            if interaction == "hover":
                await card.hover()
                await _wait_translation(page, True)
                await page.mouse.move(0, 0)
                await _wait_translation(page, False)
            elif interaction == "keyboard":
                await page.keyboard.press("Tab")
                assert await page.get_by_role("button", name="İncele").evaluate(
                    "button => button === document.activeElement"
                )
                await _wait_translation(page, True)
            elif interaction == "reduce":
                await card.hover()
                await _wait_translation(page, False)
                await page.mouse.move(0, 0)
                await page.keyboard.press("Tab")
                await _wait_translation(page, False)
                assert (
                    await page.evaluate(
                        "document.getAnimations().filter("
                        "animation => animation.playState === 'running').length"
                    )
                    == 0
                )
            else:
                assert await card.is_visible()
                assert (
                    await page.locator(".reveal").evaluate("node => getComputedStyle(node).opacity")
                    == "1"
                )
            assert not errors
        finally:
            await browser.close()
