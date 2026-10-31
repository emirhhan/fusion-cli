"""Tarayıcı panelinde öğe seçici (P-041/P-045): imlecin altındaki öğe → seçici + görüntü.

Claude Code masaüstündeki "element seç" (Cmd+Shift+S) ve Codex'in Annotation kipinin
karşılığı: kullanıcı sayfada bir öğeye tıklar, ajana öğenin CSS seçicisi, etiketi, görünür
metni ve kırpılmış ekran görüntüsü gider. Seçici ajanın `browser_click`/`browser_type`
araçlarının kabul ettiği CSS biçimindedir; benzersiz olana kadar üst öğelere çıkılır
(`#id`, `data-testid`, `name`, `aria-label` önce; yoksa `etiket:nth-of-type(n)` zinciri).

Görüntü proje içine `.fusion/secimler/` altına yazılır (sembolik bağ ya da kök dışı hedefe
yazılmaz; `preview_log.save_screenshot` ile aynı kapı) ve sohbete ek olarak düşer.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .browser_guard import PlaywrightObject
from .preview_log import save_screenshot

#: Seçim görüntülerinin klasörü (proje köküne göre).
PICKS_DIR = Path(".fusion") / "secimler"
#: Klasörde tutulan en fazla seçim görüntüsü; eskileri silinir (yalnız bizim dosyalarımız).
MAX_PICKS = 30
#: Öğe görüntüsünün çevresine eklenen pay ve en küçük kenar (CSS piksel).
CLIP_PADDING = 8
MIN_CLIP = 16
MAX_TEXT = 160

_ELEMENT_AT_JS = r"""
([x, y, maxText]) => {
  const el = document.elementFromPoint(x, y);
  if (!el) return null;
  const esc = (v) => (window.CSS && CSS.escape ? CSS.escape(v) : v);
  const unique = (sel) => { try { return document.querySelectorAll(sel).length === 1; }
                            catch (e) { return false; } };
  const attrs = ["data-testid", "data-test", "data-cy", "name", "aria-label"];
  const step = (node) => {
    if (node.id && unique("#" + esc(node.id))) return ["#" + esc(node.id), true];
    for (const a of attrs) {
      const v = node.getAttribute(a);
      if (!v) continue;
      const quoted = v.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
      const s = `${node.localName}[${a}="${quoted}"]`;
      if (unique(s)) return [s, true];
    }
    let s = node.localName;
    const parent = node.parentElement;
    if (parent) {
      const same = Array.from(parent.children).filter((c) => c.localName === node.localName);
      if (same.length > 1) s += `:nth-of-type(${same.indexOf(node) + 1})`;
    }
    return [s, false];
  };
  const parts = [];
  for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
    const [s, stop] = step(node);
    parts.unshift(s);
    if (stop || node.localName === "body" || unique(parts.join(" > "))) break;
  }
  const r = el.getBoundingClientRect();
  const text = (el.innerText || el.value || el.getAttribute("alt") ||
                el.getAttribute("aria-label") || el.getAttribute("placeholder") || "")
    .replace(/\s+/g, " ").trim().slice(0, maxText);
  return { tag: el.localName, selector: parts.join(" > "), text,
           x: r.x, y: r.y, w: r.width, h: r.height, vw: innerWidth, vh: innerHeight };
}
"""


@dataclass(frozen=True, slots=True)
class PickedElement:
    tag: str
    selector: str
    text: str
    #: Öğenin kutusu (CSS piksel) ve görünüm ölçüsü.
    x: float
    y: float
    width: float
    height: float
    viewport_width: int
    viewport_height: int

    def normalized_box(self) -> dict[str, float]:
        """Paneldeki görüntüye göre 0..1 kutu (vurgu çizmek için)."""
        vw, vh = max(self.viewport_width, 1), max(self.viewport_height, 1)
        return {
            "x": self.x / vw,
            "y": self.y / vh,
            "w": self.width / vw,
            "h": self.height / vh,
        }

    def clip(self) -> dict[str, float]:
        """Görünüm içinde kalan, paylı kırpma kutusu."""
        left = max(self.x - CLIP_PADDING, 0.0)
        top = max(self.y - CLIP_PADDING, 0.0)
        right = min(self.x + self.width + CLIP_PADDING, float(self.viewport_width))
        bottom = min(self.y + self.height + CLIP_PADDING, float(self.viewport_height))
        width = max(right - left, float(MIN_CLIP))
        height = max(bottom - top, float(MIN_CLIP))
        return {"x": left, "y": top, "width": width, "height": height}


async def element_at(page: PlaywrightObject, x: float, y: float) -> PickedElement | None:
    """CSS piksel konumundaki öğe; boş alan ya da okunamayan sayfa None."""
    try:
        raw = await page.evaluate(_ELEMENT_AT_JS, [x, y, MAX_TEXT])
    except Exception:
        # Sayfa gezinirken bağlam yok olur ya da sayfa kapanır: seçim yok sayılır.
        return None
    if not isinstance(raw, dict) or not raw.get("selector"):
        return None
    return PickedElement(
        tag=str(raw.get("tag", "")),
        selector=str(raw["selector"]),
        text=str(raw.get("text", "")),
        x=float(raw.get("x", 0)),
        y=float(raw.get("y", 0)),
        width=float(raw.get("w", 0)),
        height=float(raw.get("h", 0)),
        viewport_width=int(raw.get("vw", 0)),
        viewport_height=int(raw.get("vh", 0)),
    )


async def capture(page: PlaywrightObject, element: PickedElement | None = None) -> bytes:
    """Öğenin (yoksa görünür sayfanın) PNG görüntüsü."""
    if element is None:
        return bytes(await page.screenshot(type="png"))
    return bytes(await page.screenshot(type="png", clip=element.clip()))


def save_pick(
    root: Path, data: bytes, *, prefix: str = "oge", clock: Callable[[], float] = time.time
) -> str:
    """Görüntüyü `.fusion/secimler/<önek>-<zaman>.png` olarak yaz; köke göreli yol (ya da boş)."""
    stamp = f"{clock():.3f}".replace(".", "")
    relative = PICKS_DIR / f"{prefix}-{stamp}.png"
    written = save_screenshot(root, data, relative)
    if written:
        _prune(root / PICKS_DIR)
    return written


def _prune(folder: Path) -> None:
    """Klasörde `MAX_PICKS`'ten fazla seçim görüntüsü varsa en eskileri sil."""
    try:
        files = sorted(
            (path for path in folder.glob("*.png") if path.is_file() and not path.is_symlink()),
            key=lambda path: path.stat().st_mtime,
        )
        for old in files[:-MAX_PICKS]:
            old.unlink()
    except OSError:
        return


def mention_text(element: PickedElement, url: str) -> str:
    """Sohbete eklenecek açıklama: ajan seçiciyi doğrudan araçlarına verebilir."""
    lines = [
        f"Tarayıcıda seçilen öğe ({url}):",
        f"- seçici: `{element.selector}` (<{element.tag}>)",
    ]
    if element.text:
        lines.append(f"- metin: “{element.text}”")
    return "\n".join(lines)
