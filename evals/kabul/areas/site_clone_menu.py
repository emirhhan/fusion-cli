"""Kaynak ve kopya menülerinin davranış karşılaştırması."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from evals.kabul.model import Check

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Mevcut kaynak/kopya ölçümündeki menü animasyonu bekleme süresi (ms).
MENU_HOVER_MS = 900
VIEWPORT_HEIGHT = 900
_VISIBLE_JS = """(mode) => {
  const visible = (node) => {
    const r = node.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || r.bottom <= 0 || r.right <= 0
      || r.top >= innerHeight || r.left >= innerWidth) return false;
    let left = Math.max(r.left, 0), right = Math.min(r.right, innerWidth);
    let top = Math.max(r.top, 0), bottom = Math.min(r.bottom, innerHeight);
    for (let current = node; current; current = current.parentElement) {
      const s = getComputedStyle(current);
      if (s.display === 'none' || Number(s.opacity) === 0) return false;
      if (current !== node) {
        const box = current.getBoundingClientRect();
        if (s.overflowX !== 'visible') {
          left = Math.max(left, box.left); right = Math.min(right, box.right);
        }
        if (s.overflowY !== 'visible') {
          top = Math.max(top, box.top); bottom = Math.min(bottom, box.bottom);
        }
        if (right <= left || bottom <= top) return false;
      }
    }
    return getComputedStyle(node).visibility === 'visible';
  };
  const text = (node) => (node.innerText || '').replace(/\\s+/g, ' ').trim();
  if (mode === 'links') return [...document.querySelectorAll('a')]
    .filter(visible).map(text).filter(Boolean);
  return [...document.querySelectorAll(
    'header a, nav a, [role=banner] a, header button, nav button, [role=banner] button'
  )].filter(visible).flatMap((node) => {
    const r = node.getBoundingClientRect(), label = text(node);
    return label && label.length <= 30 && r.top < 200
      ? [{label, x: r.x + r.width / 2, y: r.y + r.height / 2}] : [];
  });
}"""


@dataclass(frozen=True, slots=True)
class MenuPanel:
    """Üzerine gelinen başlık ve açılan paneldeki bağlantı metinleri."""

    label: str
    links: tuple[str, ...]


def menu_check(clone: tuple[MenuPanel, ...], source: tuple[MenuPanel, ...] | None) -> Check:
    """Her kaynak menüsü kopyada aynı bağlantı metinleriyle açılmalı."""
    if source is None:
        return Check("menu_paneli_acilir", False, "kaynak ölçülmedi")
    eksikler = []
    for panel in source:
        adaylar = [p for p in clone if _normalized(p.label) == _normalized(panel.label)]
        beklenen = {_normalized(link) for link in panel.links}
        if any(beklenen <= {_normalized(link) for link in p.links} for p in adaylar):
            continue
        # Birden çok aynı adlı menünün içerikleri birleştirilmez: her panel tam olmalı.
        en_yakin = max(
            adaylar,
            key=lambda p: len(beklenen & {_normalized(link) for link in p.links}),
            default=None,
        )
        bulunan = {_normalized(link) for link in en_yakin.links} if en_yakin else set()
        eksik = [link for link in panel.links if _normalized(link) not in bulunan]
        eksikler.append(f"{panel.label}: {', '.join(eksik) or 'panel açılmadı'}")
    detay = f"açılan menü: kopya {len(clone)}, kaynak {len(source)}"
    if eksikler:
        detay += "; eksik: " + "; ".join(eksikler)
    return Check("menu_paneli_acilir", not eksikler, detay)


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def menu_panels_opened(page: Page) -> tuple[MenuPanel, ...]:
    """Görünür başlıkların üzerine gel; yeni görünür bağlantıları panel kanıtı say."""
    panels = []
    bottom = (page.viewport_size or {"height": VIEWPORT_HEIGHT})["height"] - 2
    page.mouse.move(2, bottom)
    page.wait_for_timeout(MENU_HOVER_MS)
    candidates = page.evaluate(_VISIBLE_JS, "items")
    try:
        for candidate in candidates:
            page.mouse.move(2, bottom)
            page.wait_for_timeout(MENU_HOVER_MS)
            before = Counter(page.evaluate(_VISIBLE_JS, "links"))
            page.mouse.move(candidate["x"], candidate["y"], steps=5)
            page.wait_for_timeout(MENU_HOVER_MS)
            after = Counter(page.evaluate(_VISIBLE_JS, "links"))
            links = tuple((after - before).elements())
            if links:
                panels.append(MenuPanel(candidate["label"], links))
    finally:
        page.mouse.move(2, bottom)
        page.wait_for_timeout(MENU_HOVER_MS)
    return tuple(panels)
