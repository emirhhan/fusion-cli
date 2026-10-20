"""Başlık menüsünde üzerine gelince açılan panelleri (mega menü) betiksiz kopyaya taşı.

Ölçüldü (10 Ekim 2026, sneaksup.com): ERKEK / KADIN / ÇOCUK için üç ayrı
`.sh-desktop-menu` paneli DOM'da hazır duruyor; site betiği üzerine gelince satır içi
`visibility:hidden` → `visible` yapıyor. Kopya panellerin içeriğini taşıyordu ama
betik söküldüğü için menü hiç açılmıyordu (görünür öğe sayısı 7190 → 7190).

Yakalamada her menü öğesinin üzerine gelinir; görünür olan paneller işaretlenir
(`data-kopya-ac` / `data-kopya-panel`) ve aynı davranış saf CSS ile
(`body:has([data-kopya-ac="0"]:hover) [data-kopya-panel="0"]`) yeniden kurulur.
Panelin içindeki ok taşıyan öğeler (ERKEK > AYAKKABI > SNEAKER…) bir düzey daha
gezilir; alt panel üzerindeyken üst panel de açık kalır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Page

HOVER_SCRIPT = Path(__file__).with_name("assets") / "hover_panels.js"
#: Üzerine gelince panelin açılması için beklenen süre. sneaksup'ta 900 ms yetti.
HOVER_WAIT_MS = 900
#: Panelden ayrılınca kapanma animasyonu için bekleme.
LEAVE_WAIT_MS = 600
#: Fare öğeden panele geçerken panel hemen kapanmasın (aradaki boşluk). Saniye.
HIDE_DELAY_S = 0.25
#: Fareyi "menünün üstünde değil" konumuna çekmek için görünümün sol alt köşesinden uzaklık.
_REST_MARGIN_PX = 2


@dataclass(frozen=True, slots=True)
class HoverPanel:
    """Bir menü öğesi (`key`: "0", alt düzeyde "0-2") ve açtığı kutunun görünür hali."""

    key: str
    text: str
    display: str
    opacity: str
    transform: str
    parent: str = ""
    #: Konumlu kutunun ölçülen yeri (CSS değeri, örn. "394px"); akıştaysa boş.
    position: str = ""
    left: str = ""
    top: str = ""
    width: str = ""


def _layout(panel: HoverPanel) -> list[str]:
    """Kutunun yerleşimi: display + (konumluysa) ölçülen konum."""
    yerlesim = []
    if panel.display and panel.display != "none":
        yerlesim.append(f"display:{panel.display}!important")
    yerlesim.extend(
        f"{ad}:{deger}!important"
        for ad, deger in (
            ("position", panel.position),
            ("left", panel.left),
            ("top", panel.top),
            ("width", panel.width),
        )
        if deger and deger != "auto"
    )
    return yerlesim


def _visible_state(panel: HoverPanel) -> list[str]:
    gorunur = [
        "visibility:visible!important",
        "transition-delay:0s!important",
        f"opacity:{panel.opacity or '1'}!important",
    ]
    if panel.transform and panel.transform != "none":
        gorunur.append(f"transform:{panel.transform}!important")
    return gorunur


def _panel_rules(panel: HoverPanel) -> list[str]:
    """Konumlu kutunun yerleşimi hep uygulanır, yalnız görünürlüğü (gecikmeli) değişir:
    `display:none` gecikmesiz döndüğü için fare alt panele varmadan kutu yok oluyordu
    (ölçüldü: AYAKKABI satırından 14 px sağa çıkınca alt panel 0×0 oldu)."""
    secici = f'[data-kopya-panel="{panel.key}"]'
    kosullar = [
        f'body:has([data-kopya-ac="{panel.key}"]:hover) {secici}',
        f"body {secici}:hover",
        f'body:has([data-kopya-ust="{panel.key}"]:hover) {secici}',
    ]
    yerlesim = _layout(panel)
    if panel.left or panel.top:
        return [
            f"{secici}{{{';'.join(yerlesim)}}}",
            f"{','.join(kosullar)}{{{';'.join(_visible_state(panel))}}}",
        ]
    return [f"{','.join(kosullar)}{{{';'.join([*_visible_state(panel), *yerlesim])}}}"]


def hover_css(panels: tuple[HoverPanel, ...]) -> str:
    """Panelleri gizleyen ve tetikleyicinin üzerine gelince gösteren saf CSS."""
    if not panels:
        return ""
    kurallar = [
        # pointer-events açık kalır: gizli kutu zaten olay almaz, kapanma gecikmesinde
        # ise fare panele geçebilmeli (kaynaktaki satır içi `pointer-events:none` ezilir).
        "[data-kopya-panel]{visibility:hidden!important;pointer-events:auto!important;"
        f"transition:visibility 0s linear {HIDE_DELAY_S}s!important}}"
    ]
    for panel in {item.key: item for item in panels}.values():
        kurallar.extend(_panel_rules(panel))
    return "\n".join(kurallar)


def _panel(trigger: dict[str, Any], values: dict[str, Any], parent: str) -> HoverPanel:
    return HoverPanel(
        key=str(trigger["id"]),
        text=str(trigger["text"]),
        display=str(values.get("display", "")),
        opacity=str(values.get("opacity", "")),
        transform=str(values.get("transform", "")),
        parent=parent,
        position=str(values.get("position", "")),
        left=str(values.get("left", "")),
        top=str(values.get("top", "")),
        width=str(values.get("width", "")),
    )


class _Walker:
    """Fareyi menüde gezdirir; her adımda açılan kutuları işaretler."""

    def __init__(self, page: Page, script: str) -> None:
        self.page = page
        self.script = script
        viewport = page.viewport_size or {"width": 1440, "height": 900}
        self.rest = (float(_REST_MARGIN_PX), float(viewport["height"] - _REST_MARGIN_PX))

    async def call(self, mode: str, key: str = "", scope: str = "") -> list[dict[str, Any]]:
        sonuc = await self.page.evaluate(self.script, [mode, key, scope])
        return list(sonuc) if isinstance(sonuc, list) else []

    async def leave(self) -> None:
        await self.page.mouse.move(*self.rest)
        await self.page.wait_for_timeout(LEAVE_WAIT_MS)

    async def hover(self, x: float, y: float) -> None:
        await self.page.mouse.move(x, y, steps=6)
        await self.page.wait_for_timeout(HOVER_WAIT_MS)

    async def probe(
        self, trigger: dict[str, Any], parent: dict[str, Any] | None
    ) -> list[HoverPanel]:
        """Öğenin üzerine gel ve açılanı işaretle. Alt öğede önce üst panel açılır;
        fare üst öğeden dikey inip yatay gider ki üst panel yolda kapanmasın."""
        await self.leave()
        if parent is not None:
            # Görünür küme üst panel açıkken, fare henüz panelin satırlarına inmeden alınır.
            await self.hover(float(parent["x"]), float(parent["y"]))
            await self.call("snapshot")
            await self.page.mouse.move(float(parent["x"]), float(trigger["y"]), steps=6)
        else:
            await self.call("snapshot")
        await self.hover(float(trigger["x"]), float(trigger["y"]))
        ust = "" if parent is None else str(parent["id"])
        found = await self.call("diff", str(trigger["id"]), ust)
        return [_panel(trigger, values, ust) for values in found]


async def capture_hover_panels(page: Page) -> tuple[HoverPanel, ...]:
    """Menü öğelerinin (ve panel içi alt öğelerin) üzerine gel; açılanları işaretle."""
    walker = _Walker(page, HOVER_SCRIPT.read_text(encoding="utf-8"))
    panels: list[HoverPanel] = []
    for trigger in await walker.call("triggers"):
        found = await walker.probe(trigger, None)
        panels.extend(found)
        if not found:
            continue
        for child in await walker.call("triggers", "", str(trigger["id"])):
            panels.extend(await walker.probe(child, trigger))
    await walker.leave()
    await walker.call("restore")
    return tuple(panels)
