"""Oyun canvas'ının tuş öncesi/sonrası görüntü imzası.

Ölçüldü (29 Ekim): WebGL canvas'ta `preserveDrawingBuffer` kapalıyken `toDataURL()`
her seferinde aynı boş kareyi verir; imza sabit kalır ve tuşlar çalışan oyun için
"tuşlar etkisiz" alarmı çıkıyordu. Bağlam türü sayfa kodundan ÖNCE kaydedilir; 2B
canvas için `toDataURL`, diğerleri için derleyicinin çizdiği kareden (ekran
görüntüsü) imza alınır. Canvas imzası etkileşimin tek kanıtı değildir: kendiliğinden
oynayan animasyon da imzayı değiştirir.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

#: `getContext` türünü canvas'a işler.
CANVAS_INIT = """(() => {
  const original = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function(type, ...args) {
    const context = original.call(this, type, ...args);
    if (context && !this.__fusionKind) {
      const t = String(type).toLowerCase();
      this.__fusionKind = t.includes('webgl') ? 'webgl' : t === '2d' ? '2d' : 'other';
    }
    return context;
  };
})()"""

_LARGEST = """() => {
  const c = [...document.querySelectorAll('canvas')]
    .sort((a, b) => b.width * b.height - a.width * a.height)[0];
  if (!c) return null;
  const kind = c.__fusionKind || 'unknown';
  const r = c.getBoundingClientRect();
  const box = [Math.max(0, r.x), Math.max(0, r.y),
    Math.min(r.width, innerWidth - Math.max(0, r.x)),
    Math.min(r.height, innerHeight - Math.max(0, r.y))];
  let hash = null;
  if (kind === '2d') { try { const d = c.toDataURL('image/png'); let h = 0;
    for (let i = 0; i < d.length; i += 97) h = (h * 31 + d.charCodeAt(i)) | 0; hash = h; }
    catch (e) { hash = null; } }
  return { kind, hash, box };
}"""


@dataclass(frozen=True, slots=True)
class CanvasReading:
    kind: str
    signature: str | None


async def read_canvas(page: Page) -> CanvasReading | None:
    """En büyük canvas'ın türü ve imzası; canvas yoksa None."""
    info = await page.evaluate(_LARGEST)
    if info is None:
        return None
    if info["hash"] is not None:
        return CanvasReading(info["kind"], str(info["hash"]))
    x, y, width, height = info["box"]
    if width < 1 or height < 1:
        return CanvasReading(info["kind"], None)
    try:
        shot = await page.screenshot(clip={"x": x, "y": y, "width": width, "height": height})
    except Exception:
        return CanvasReading(info["kind"], None)
    return CanvasReading(info["kind"], hashlib.sha256(shot).hexdigest())


def canvas_verdict(
    before: CanvasReading | None, after: CanvasReading | None
) -> tuple[str | None, bool | None]:
    """(tür, değişti mi). Ölçülemeyen ya da tür değişen karşılaştırma None döner."""
    if before is None or after is None or before.kind != after.kind:
        return (before.kind if before else None), None
    if before.signature is None or after.signature is None:
        return before.kind, None
    return before.kind, before.signature != after.signature
