"""Oyun sondası: tarayıcı oyununu başsız Chromium'da oynat, tepkisini ölç.

Ölçüldü (4 Ekim, HTML oyun koşusu): model oyunu denemek için başsız tarayıcı
araçlarında tuş basma olmadığından 239 kez `osascript` ile kullanıcının masaüstüne
tuş gönderdi; koşu 57 dakika sürdü. "Çalışıyor" ile "oynanabilir" farkını ölçmenin
güvenli yolu budur: sayfa ayrı bir başsız tarayıcıda açılır, tuşlar basılı tutulur,
`window.__GAME_STATE__()` (varsa), canvas pikselleri, rAF canlılığı ve konsol
hataları karşılaştırılır. Sonuç metindir: görsel okuyamayan model de kullanır.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

#: Basılı tutulan varsayılan tuşlar: ok tuşları + boşluk (çoğu arcade oyunu).
DEFAULT_KEYS = ("ArrowRight", "ArrowUp", "ArrowLeft", "ArrowDown", "Space")
#: Tuş başına basılı tutma süresi (ms); hareketin görünmesine yeter.
KEY_HOLD_MS = 500
SETTLE_MS = 1_000
NAVIGATION_TIMEOUT_MS = 30_000
_RAF_COUNTER = """() => new Promise(done => { let n = 0; const t0 = performance.now();
  function tick(t) { n++; if (t - t0 < 1000) requestAnimationFrame(tick); else done(n); }
  requestAnimationFrame(tick); })"""
_STATE = """() => { try { return typeof window.__GAME_STATE__ === 'function'
  ? JSON.stringify(window.__GAME_STATE__()) : null; } catch (e) { return 'HATA: ' + e; } }"""
_CANVAS_HASH = """() => { const c = [...document.querySelectorAll('canvas')]
  .sort((a, b) => b.width * b.height - a.width * a.height)[0];
  if (!c) return null; try { const d = c.toDataURL('image/png'); let h = 0;
  for (let i = 0; i < d.length; i += 97) h = (h * 31 + d.charCodeAt(i)) | 0; return h; }
  catch (e) { return null; } }"""


@dataclass(frozen=True, slots=True)
class ProbeReport:
    """Sondanın ölçtükleri."""

    console_errors: tuple[str, ...]
    raf_per_second: int
    state_before: str | None
    state_after: str | None
    canvas_changed: bool | None
    restart_state: str | None
    #: Basıldığında durumu değiştiren tuşlar. Önce/sonra karşılaştırması tek başına
    #: yanıltır: sağ+sol ya da yukarı+aşağı birbirini götürür (ölçüldü, 4 Ekim).
    effective_keys: tuple[str, ...] = ()

    def summary(self) -> str:
        satirlar = [
            f"Konsol hatası: {len(self.console_errors)}"
            + (f" — {'; '.join(self.console_errors[:3])}" if self.console_errors else ""),
            f"requestAnimationFrame: {self.raf_per_second}/sn"
            + (" (döngü çalışmıyor!)" if self.raf_per_second < 20 else ""),
        ]
        if self.state_before is None:
            satirlar.append(
                "window.__GAME_STATE__ yok: oyuncu konumu/skor ölçülemedi. Ekle: "
                "window.__GAME_STATE__ = () => ({durum, skor, can, oyuncu: {x, y}})."
            )
        else:
            degisti = self.state_before != self.state_after or bool(self.effective_keys)
            satirlar.append(f"Durum tuşlardan önce: {self.state_before}")
            satirlar.append(
                f"Durum tuşlardan sonra: {self.state_after}"
                + ("" if degisti else "  ← TUŞLAR DURUMU DEĞİŞTİRMEDİ")
            )
            if self.effective_keys:
                tuslar = ", ".join(repr(tus) for tus in self.effective_keys)
                satirlar.append(f"Durumu değiştiren tuşlar: {tuslar}")
        if self.canvas_changed is not None:
            satirlar.append(
                f"Canvas tuşlarla değişti: {'evet' if self.canvas_changed else 'HAYIR'}"
            )
        if self.restart_state is not None:
            satirlar.append(
                f"R tuşundan sonra durum (oyun ortasında basıldı; R yalnız oyun sonunda "
                f"çalışıyorsa bu normaldir): {self.restart_state}"
            )
        return "\n".join(satirlar)


async def _press(page: Page, keys: tuple[str, ...]) -> tuple[str, ...]:
    """Tuşlara sırayla bas; her tuştan sonra durumu oku ve değiştirenleri döndür."""
    await page.locator("body").click(position={"x": 5, "y": 5}, force=True)
    etkili: list[str] = []
    onceki = await page.evaluate(_STATE)
    for tus in keys:
        await page.keyboard.down(tus)
        await page.wait_for_timeout(KEY_HOLD_MS)
        await page.keyboard.up(tus)
        simdiki = await page.evaluate(_STATE)
        if simdiki != onceki and tus not in etkili:
            etkili.append(tus)
        onceki = simdiki
    return tuple(etkili)


async def probe_game(url: str, keys: tuple[str, ...] = DEFAULT_KEYS) -> ProbeReport:
    """Oyunu aç, tuşlara bas, durumu karşılaştır. Playwright yoksa ImportError."""
    from playwright.async_api import async_playwright  # tembel: opsiyonel ekstra

    hatalar: list[str] = []
    async with async_playwright() as oynatici:
        tarayici = await oynatici.chromium.launch()
        try:
            sayfa = await tarayici.new_page(viewport={"width": 1280, "height": 800})
            sayfa.on("pageerror", lambda hata: hatalar.append(str(hata)[:200]))
            sayfa.on(
                "console",
                lambda m: hatalar.append(m.text[:200]) if m.type == "error" else None,
            )
            await sayfa.goto(url, timeout=NAVIGATION_TIMEOUT_MS, wait_until="load")
            await sayfa.wait_for_timeout(SETTLE_MS)
            raf = int(await sayfa.evaluate(_RAF_COUNTER))
            await _press(sayfa, ("Enter", "Space"))
            once, tuval_once = await sayfa.evaluate(_STATE), await sayfa.evaluate(_CANVAS_HASH)
            etkili = await _press(sayfa, keys)
            sonra, tuval_sonra = await sayfa.evaluate(_STATE), await sayfa.evaluate(_CANVAS_HASH)
            await _press(sayfa, ("r",))
            yeniden = await sayfa.evaluate(_STATE)
        finally:
            await tarayici.close()
    tuval = None if tuval_once is None else tuval_once != tuval_sonra
    return ProbeReport(tuple(hatalar), raf, once, sonra, tuval, yeniden, etkili)


def parse_keys(raw: object) -> tuple[str, ...]:
    """Model verdiği tuş listesini doğrula; boş ya da geçersizse varsayılan tuşlar."""
    liste: object = raw
    if isinstance(raw, str):
        try:
            liste = json.loads(raw)
        except ValueError:
            liste = [parca.strip() for parca in raw.split(",")]
    if not isinstance(liste, list):
        return DEFAULT_KEYS
    tuslar = tuple(t for t in liste if isinstance(t, str) and 0 < len(t) <= 20)
    return tuslar[:10] or DEFAULT_KEYS
