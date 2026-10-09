"""Başlat düğmesini gerçek tıklamayla, klavye yedeği devreye girmeden ölç."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

BUTTON_SELECTOR = "button, [role=button], a, input[type=button]"
_FIND_START = """() => {
  const matches = /ba[sş]la|start|play|oyna/i;
  const restart = /yeniden|tekrar|restart/i;
  const shown = el => { const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    for (let e=el;e;e=e.parentElement) {const s=getComputedStyle(e);
      if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity)<0.05) return false;}
    return true;};
  const buttons=[...document.querySelectorAll('button, [role=button], a, input[type=button]')];
  const index=buttons.findIndex(el => {const text=el.innerText||el.value||'';
    return matches.test(text)&&!restart.test(text)&&shown(el);});
  return index < 0 ? null : index;
}"""
#: Başla düğmesinin konumlu (fixed/absolute) en dış atası = menü katmanı. Tıklamadan
#: sonra ekranın ortası hâlâ bu katmana düşüyorsa menü oyunu örtüyordur (dalga44:
#: `.hidden` sınıfı eklendi ama CSS kuralı yoktu, durum 'playing' iken menü kaldı).
_MARK_MENU = """(index) => {
  const button=[...document.querySelectorAll(
    'button, [role=button], a, input[type=button]')][index];
  let menu=null;
  for (let e=button;e&&e!==document.body;e=e.parentElement) {
    const p=getComputedStyle(e).position; if (p==='fixed'||p==='absolute') menu=e; }
  if (menu) menu.setAttribute('data-fusion-start-menu','');
  return menu !== null;
}"""
_MENU_COVERS = """() => {
  const menu=document.querySelector('[data-fusion-start-menu]');
  if (!menu) return false;
  const hit=document.elementFromPoint(innerWidth/2, innerHeight/2);
  return hit !== null && menu.contains(hit);
}"""
_MENU_STUCK = (
    "Başla düğmesine basıldı ama menü ekranda kaldı: ekranın ortası hâlâ menü katmanı; "
    "gizleme sınıfının (ör. #start-screen.hidden {display:none}) CSS kuralı var mı bak"
)


@dataclass(frozen=True, slots=True)
class StartupReport:
    """Başlangıç kontrolü bulundu mu, tıklama sonrası hangi kusur kaldı?"""

    has_button: bool
    problems: tuple[str, ...] = ()


def _phase(snapshot: str | None) -> str | None:
    """Sayaç/oyuncu animasyonu başlangıç geçişi değildir; yalnız durumu karşılaştır."""
    if snapshot is None:
        return None
    try:
        state = json.loads(snapshot)
    except (ValueError, TypeError):
        return None
    if isinstance(state, str):
        return state
    if isinstance(state, dict):
        for name in ("durum", "state", "mode", "phase", "status"):
            value = state.get(name)
            if isinstance(value, str):
                return value
    return None


async def start_game(
    page: Page, *, settle_ms: int, timeout_ms: int, state_script: str
) -> StartupReport:
    """Görünür Başla varsa yalnız ona bas; keyboard başlangıcı hatayı örtmesin."""
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    index = await page.evaluate(_FIND_START)
    if index is None:
        return StartupReport(has_button=False)
    before = await page.evaluate(state_script)
    has_menu = await page.evaluate(_MARK_MENU, index)
    try:
        await page.locator(BUTTON_SELECTOR).nth(index).click(timeout=timeout_ms)
    except PlaywrightTimeoutError:
        return StartupReport(True, ("Başla düğmesi gerçek kullanıcı tıklamasını alamıyor",))
    await page.wait_for_timeout(settle_ms)
    after = await page.evaluate(state_script)
    if has_menu and await page.evaluate(_MENU_COVERS):
        return StartupReport(True, (_MENU_STUCK,))
    before_phase, after_phase = _phase(before), _phase(after)
    if before_phase is not None and after_phase is not None:
        if before_phase == after_phase:
            return StartupReport(
                True, ("Başla düğmesine basıldı ama başlangıç ekranı/durumu değişmedi",)
            )
    elif await page.evaluate(_FIND_START) is not None:
        return StartupReport(
            True,
            (
                "Başla düğmesinin başlatma geçişi doğrulanamadı; "
                "__GAME_STATE__ kancasına durum alanını ekleyip yeniden dene",
            ),
        )
    return StartupReport(has_button=True)
