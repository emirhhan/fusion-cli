"""HTML oyun denetçisinin tarayıcı ölçümleri (sayaç enjeksiyonu, tuş basma, HUD okuma).

Sayfa betiklerinden ÖNCE bir betik enjekte edilir: `requestAnimationFrame` çağrılarını
sayar ve canvas'a çizilen metinleri (`fillText`/`strokeText`) zaman damgasıyla kaydeder.
Böylece canvas içine çizilen skor/can yazısı da gerçekten ölçülür, tahmin edilmez.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from evals.kabul.areas._pixels import changed_pixel_ratio

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

#: Sayfa betiklerinden önce çalışan enjeksiyon.
INIT_SCRIPT = """
(() => {
  window.__fusionRaf = 0;
  const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (callback) => { window.__fusionRaf += 1; return raf(callback); };
  window.__fusionTexts = [];
  const proto = CanvasRenderingContext2D.prototype;
  for (const name of ['fillText', 'strokeText']) {
    const original = proto[name];
    proto[name] = function (text, ...rest) {
      const list = window.__fusionTexts;
      list.push([performance.now(), String(text)]);
      if (list.length > 400) list.shift();
      return original.call(this, text, ...rest);
    };
  }
})();
"""
#: Son çizim karesinde (40 ms içinde) canvas'a yazılan metinler.
_LAST_FRAME_TEXTS_JS = """() => {
  const list = window.__fusionTexts || [];
  if (!list.length) return [];
  const last = list[list.length - 1][0];
  return list.filter((entry) => last - entry[0] <= 40).map((entry) => entry[1]);
}"""
_DOM_TEXT_JS = "document.body ? document.body.innerText : ''"
_RAF_COUNT_JS = "window.__fusionRaf || 0"

#: Bir oyun alanı sayılması için en küçük alan (px²).
MIN_AREA_PIXELS = 10_000
#: Aranacak en çok aday sayısı.
MAX_AREA_CANDIDATES = 8
#: Tuş basışında otomatik tekrar (autorepeat) aralığı (ms).
KEY_REPEAT_MS = 50
#: Enerji ölçümünde her adımın süresi (ms).
KEY_HOLD_MS = 250
#: Ok tuşları + boşluk dizisi.
KEY_SEQUENCE = ("ArrowRight", "ArrowUp", "ArrowLeft", "ArrowDown", "Space")
_AREA_SELECTOR = (
    "[id*='game' i], [class*='game' i], [id*='arena' i], [id*='board' i], [id*='stage' i]"
)
HUD_PATTERN = re.compile(
    r"(?:(?:skor|score|puan|can|canlar|lives?|health|hp)\s*[:=x×-]?\s*\d"
    r"|[♥❤]|\d\s*(?:puan|points?))",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class HudReading:
    """Sayfadaki skor/can benzeri metinler: DOM'dan ve canvas'a çizilenlerden."""

    dom: tuple[str, ...] = ()
    canvas: tuple[str, ...] = ()

    @property
    def lines(self) -> tuple[str, ...]:
        return tuple(sorted({*self.dom, *self.canvas}))

    @property
    def found(self) -> bool:
        return bool(self.dom or self.canvas)


def _hud_lines(texts: list[str]) -> tuple[str, ...]:
    lines = (_WHITESPACE.sub(" ", line).strip() for text in texts for line in text.splitlines())
    return tuple(dict.fromkeys(line for line in lines if line and HUD_PATTERN.search(line)))


def read_hud(page: Page) -> HudReading:
    """DOM metninde ve canvas'ın son karesinde HUD benzeri satırları ara."""
    dom_text = cast("str", page.evaluate(_DOM_TEXT_JS))
    canvas_texts = cast("list[str]", page.evaluate(_LAST_FRAME_TEXTS_JS))
    return HudReading(dom=_hud_lines([dom_text]), canvas=_hud_lines(canvas_texts))


def raf_count(page: Page) -> int:
    """Enjekte sayaca göre şimdiye dek yapılan `requestAnimationFrame` çağrısı."""
    return int(page.evaluate(_RAF_COUNT_JS))


def find_game_area(page: Page) -> Locator | None:
    """En büyük canvas'ı, yoksa oyun alanına benzeyen en büyük öğeyi bul."""
    for selector in ("canvas", _AREA_SELECTOR):
        locator = page.locator(selector)
        best: Locator | None = None
        best_size = float(MIN_AREA_PIXELS)
        for index in range(min(locator.count(), MAX_AREA_CANDIDATES)):
            box = locator.nth(index).bounding_box()
            if box is not None and box["width"] * box["height"] >= best_size:
                best, best_size = locator.nth(index), box["width"] * box["height"]
        if best is not None:
            return best
    return None


def make_shooter(page: Page, area: Locator | None) -> Callable[[], bytes]:
    """Oyun alanının (yoksa pencerenin) ekran görüntüsünü veren fonksiyon."""

    def shoot() -> bytes:
        return area.screenshot(type="png") if area is not None else page.screenshot(type="png")

    return shoot


def hold_key(page: Page, key: str, duration_ms: int) -> None:
    """Tuşu basılı tut; gerçek klavyedeki gibi otomatik tekrar (autorepeat) gönder."""
    page.keyboard.down(key)
    for _ in range(max(0, duration_ms // KEY_REPEAT_MS)):
        page.wait_for_timeout(KEY_REPEAT_MS)
        page.keyboard.down(key)
    page.keyboard.up(key)


def motion_energy(page: Page, shoot: Callable[[], bytes], *, press_keys: bool) -> float:
    """Her adım sonrası alınan ardışık karelerin değişen piksel oranlarının toplamı.

    `press_keys` kapalıysa aynı sürede tuşsuz beklenir; ikisi karşılaştırılarak oyunun
    tuşlara tepkisi, kendi kendine hareketinden (düşman, zamanlayıcı) ayrılır.
    """
    previous = shoot()
    energy = 0.0
    for key in KEY_SEQUENCE:
        if press_keys:
            hold_key(page, key, KEY_HOLD_MS)
        else:
            page.wait_for_timeout(KEY_HOLD_MS)
        current = shoot()
        energy += changed_pixel_ratio(previous, current)
        previous = current
    return energy
