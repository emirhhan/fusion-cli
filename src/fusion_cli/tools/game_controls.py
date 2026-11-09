"""Requested pause UI and bounded hook transitions; never a full gameplay proof."""

from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page


def requires_pause_button(task: str) -> bool:
    """Only an explicit affirmative button request adds this narrow requirement."""
    quoted = r'```.*?```|`[^`]*`|^[ \t]*>[^\n]*|["“][^"”\n]*["”]|‘[^’\n]*’'
    prose = re.sub(quoted, " ", task.casefold(), flags=re.M | re.S)
    for sentence in re.split(r"[.!?;\n]", prose):
        if not re.search(r"duraklat|pause", sentence):
            continue
        if not re.search(r"düğme|buton|button", sentence):
            continue
        if re.search(
            r"olmasın|gerekmez|gerek yok|istemiyorum|isteğe bağlı|zorunlu değil"
            r"|\b(?:not|no|never|without|optional|don.t)\b",
            sentence,
        ):
            continue
        if re.search(
            r"\b(?:olsun|ekle|ekleyin|ekleyiniz|bulunsun|sağla|sağlayın|sağlayınız|include|add|provide|must)\b",
            sentence,
        ):
            return True
    return False


async def _actionable(button: Locator) -> bool:
    return bool(
        await button.is_visible()
        and await button.is_enabled()
        and await button.evaluate("""el => {
                let opacity = 1;
                for(let e=el; e; e=e.parentElement) {
                    const s=getComputedStyle(e); opacity *= Number(s.opacity);
                    // Target visibility is checked above; children may override a hidden parent.
                    if(s.display==='none'||e.inert||opacity<0.05)
                        return false;
                }
                const r=el.getBoundingClientRect();
                const x=Math.max(0, Math.min(innerWidth-1, r.x+r.width/2));
                const y=Math.max(0, Math.min(innerHeight-1, r.y+r.height/2));
                const hit=document.elementFromPoint(x,y);
                return !!hit && el.contains(hit);
            }""")
    )


async def pause_button_problems(page: Page) -> tuple[str, ...]:
    """Measure actual visible enabled button metadata after starting the game."""
    buttons = page.get_by_role("button", name=re.compile(r"duraklat|pause|⏸", re.I))
    for index in range(min(await buttons.count(), 100)):
        button = buttons.nth(index)
        if await _actionable(button):
            return ()
    return (
        "İstenen görünür ve etkin duraklat düğmesi oyun sırasında bulunamadı; "
        "klavye kısayolu düğme gereksinimini karşılamaz.",
    )


_PHASE = """() => {
  try {
    if(typeof window.__GAME_STATE__ !== 'function') return 'unknown';
    const s=window.__GAME_STATE__();
    if(!s || typeof s!=='object') return 'unknown';
    if(s.paused===true || s.duraklatildi===true) return 'paused';
    for(const k of ['durum','state','mode','phase','status']) {
      if(typeof s[k]!=='string') continue;
      const v=s[k].toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')
        .replace(/ı/g,'i');
      if(['paused','pause','duraklatildi','duraklatilmis','duraklat'].includes(v)) return 'paused';
      if(['playing','running','oynuyor','oyun','aktif'].includes(v)) return 'playing';
    }
    if(s.running===true && s.paused===false) return 'playing';
    return 'unknown';
  } catch(e) { return 'unknown'; }
}"""


async def _observe_phase(page: Page, expected: str) -> str:
    """Require 120 ms of sampled phase stability inside the one-second window."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 1
    stable_since: float | None = None
    while True:
        phase: str = await page.evaluate(_PHASE)
        now = loop.time()
        if phase == "unknown":
            return phase
        remaining = deadline - now
        if remaining <= 0:
            # A late expected sample without its settling window is not proof.
            return "unknown" if phase == expected else phase
        if phase == expected:
            if stable_since is None:
                stable_since = now
            elif now - stable_since >= 0.12:
                return phase
        else:
            stable_since = None
        await asyncio.sleep(min(0.05, remaining))


async def pause_button_behavior(page: Page) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Optional control measurement has one fixed deadline including UI restoration."""
    try:
        async with asyncio.timeout(4):
            return await _pause_button_behavior(page)
    except TimeoutError:
        return (), ("Duraklat/devam düğmesi davranışı süre sınırında ölçülemedi.",)


async def _pause_button_behavior(page: Page) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Click only actual UI; unknown hooks are unmeasured, never invented failures."""
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    missing = await pause_button_problems(page)
    if missing:
        return missing, ()
    buttons = page.get_by_role("button", name=re.compile(r"duraklat|pause|⏸", re.I))
    for index in range(min(await buttons.count(), 100)):
        button = buttons.nth(index)
        if not await _actionable(button):
            continue
        before = await page.evaluate(_PHASE)
        if before == "unknown":
            return (), ("Duraklat/devam düğmesi davranışı durum kancasıyla ölçülemedi.",)
        try:
            await button.click(timeout=1000)
        except PlaywrightTimeoutError:
            continue
        after = await _observe_phase(page, "paused")
        if before == "playing" and after == "playing":
            return (
                "Ölçüm süresi içinde duraklat düğmesine tıklama sonrası oyun oynuyor olarak kaldı.",
            ), ()
        if after != "paused":
            return (), ("Duraklat/devam düğmesi davranışı durum kancasıyla ölçülemedi.",)
        # Restore through UI so subsequent keyboard/HUD probes still exercise live gameplay.
        resume = page.get_by_role("button", name=re.compile(r"devam|resume|continue|sürdür", re.I))
        restored = False
        for candidate in range(min(await resume.count(), 10)):
            control = resume.nth(candidate)
            if await _actionable(control):
                try:
                    await control.click(timeout=1000)
                    if await _observe_phase(page, "playing") == "playing":
                        restored = True
                        break
                except PlaywrightTimeoutError:
                    continue
        if not restored and after == "paused":
            with suppress(PlaywrightTimeoutError):
                await button.click(timeout=1000)
            final = await _observe_phase(page, "playing")
        else:
            final = await page.evaluate(_PHASE)
        if after == "paused" and final == "paused":
            return (
                "Ölçüm süresi içinde duraklatma sonrası görünür düğmelerle oyuna devam edilemedi.",
            ), ()
        if before == "playing" and after == "paused" and final == "playing":
            return (), ()
        return (), ("Duraklat/devam düğmesi davranışı durum kancasıyla ölçülemedi.",)
    return ("Duraklat düğmesi gerçek tıklama için erişilebilir değil.",), ()
