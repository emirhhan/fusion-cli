"""Paylaşılan tarayıcının canlı görüntüsü ve kullanıcı girdisi (P-045 Tarayıcı paneli).

Görüntü Chromium'un ekran yayınıdır (CDP `Page.startScreencast`): yalnız sayfa DEĞİŞİNCE kare
gelir. Kareler arka plan görevi açmadan çekilir: Chromium bir kare onaylanana kadar sonrakini
göndermez, onay panelin bir sonraki isteğinde verilir. Panel bakmıyorsa onay gitmez, tarayıcı
kare üretmez (ölçüldü, 31 Ekim: boşta 2 sn'de ek kare yok). CDP yoksa (Chromium dışı)
seyrek JPEG ekran görüntüsüne düşülür.

Girdi koordinatları panelde görüntünün 0..1 aralığına göre gelir ve sayfanın CSS
piksellerine çevrilir; yeni adres açmak ajanla AYNI güvenlik kapısından geçer
(`browser_block_reason`), kullanıcının yazdığı yerel adres izin kümesine girer.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..core.browser_session import BrowserSession
from .browser import PAGE_TIMEOUT_MS, normalize_url
from .browser_guard import PlaywrightObject
from .preview_log import PageEventCollector, PageLog
from .web import browser_block_reason, loopback_origins_in

#: Ekran yayını ayarları: JPEG kalite/boyut, panel genişliği için yeterli.
SCREENCAST = {"format": "jpeg", "quality": 60, "maxWidth": 1600, "maxHeight": 1600}
#: CDP yokken yedek ekran görüntüsünün en sık alınma aralığı (sn).
FALLBACK_INTERVAL_S = 0.5
#: Kabul edilen görünüm ölçüleri (CSS piksel).
MIN_VIEWPORT, MAX_VIEWPORT = 240, 4_000
#: Panelden basılabilecek özel tuşlar (Playwright adları) ve değiştiriciler.
_KEY = re.compile(
    r"^((Control|Alt|Shift|Meta)\+){0,3}"
    r"(Enter|Tab|Escape|Backspace|Delete|Insert|Home|End|PageUp|PageDown|"
    r"ArrowUp|ArrowDown|ArrowLeft|ArrowRight|F([1-9]|1[0-2])|[A-Za-z0-9])$"
)
MAX_TYPED_CHARS = 2_000
COLOR_SCHEMES = frozenset({"light", "dark", "no-preference"})

NOT_OPEN = "Tarayıcı açık değil; panelde bir adres aç."
BAD_KEY = "Bu tuş panelden gönderilemez: {key}"
BLOCKED = "Bu adrese erişilemez: {reason}"


class LiveInputError(ValueError):
    """Panel girdisi geçersiz (kullanıcıya gösterilir)."""


@dataclass(frozen=True, slots=True)
class LiveFrame:
    seq: int
    #: Base64 JPEG.
    data: str
    #: Sayfanın CSS piksel ölçüsü (karedeki görüntü küçültülmüş olabilir).
    css_width: int
    css_height: int


@dataclass(frozen=True, slots=True)
class LiveTab:
    index: int
    title: str
    url: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    is_open: bool
    seq: int
    #: Yalnız istemcinin son gördüğünden yeni kare varsa dolu.
    frame: LiveFrame | None = None
    url: str = ""
    title: str = ""
    tabs: tuple[LiveTab, ...] = ()


class LiveView:
    """Paylaşılan oturumun etkin sekmesini izler; görüntü, sekmeler, konsol ve girdi."""

    def __init__(
        self, session: BrowserSession, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._session = session
        self._clock = clock
        self._page: Any = None
        self._cdp: Any = None
        self._pending_ack: int | None = None
        self._frame: LiveFrame | None = None
        self._seq = 0
        self._fallback_at = 0.0
        self._fallback_digest = ""
        self._context: Any = None
        #: Panelde seçilen görünüm ölçüsü; yeni sekmelere de uygulanır.
        self._viewport: tuple[int, int] | None = None
        self.collector = PageEventCollector()

    @property
    def session(self) -> BrowserSession:
        return self._session

    # ------------------------------------------------------------------ görüntü
    async def snapshot(self, since: int) -> LiveSnapshot:
        page = await self.active_page()
        if page is None:
            await self.detach()
            return LiveSnapshot(is_open=False, seq=self._seq)
        await self._attach(page)
        if self._cdp is not None and self._pending_ack is not None:
            ack, self._pending_ack = self._pending_ack, None
            with contextlib.suppress(Exception):
                await self._cdp.send("Page.screencastFrameAck", {"sessionId": ack})
        if self._cdp is None:
            await self._fallback_frame(page)
        frame = self._frame if self._frame is not None and self._frame.seq > since else None
        title = ""
        with contextlib.suppress(Exception):
            title = await page.title()
        return LiveSnapshot(True, self._seq, frame, page.url, title, await self.tabs())

    async def active_page(self) -> PlaywrightObject:
        """Etkin sekme; kapanmışsa açık kalan son sekmeye geçilir (ajanın sayfası da odur)."""
        session = self._session
        if not session.is_open:
            return None
        if session.page.is_closed():
            pages = await session.pages()
            session.page = pages[-1] if pages else None
        return session.page

    async def tabs(self) -> tuple[LiveTab, ...]:
        rows: list[LiveTab] = []
        for index, page in enumerate(await self._session.pages(), start=1):
            title = ""
            with contextlib.suppress(Exception):
                title = await page.title()
            rows.append(LiveTab(index, title, page.url, page is self._session.page))
        return tuple(rows)

    async def _attach(self, page: PlaywrightObject) -> None:
        if page is self._page:
            return
        await self.detach()
        self._page = page
        self.watch_context(page.context)
        try:
            cdp = await page.context.new_cdp_session(page)
            cdp.on("Page.screencastFrame", self._on_frame)
            await cdp.send("Page.startScreencast", SCREENCAST)
        except Exception:
            # Chromium dışı tarayıcı ya da kapanmakta olan sayfa: yedek görüntüye düşülür.
            self._cdp = None
            return
        self._cdp = cdp

    def _on_frame(self, event: dict[str, Any]) -> None:
        metadata = event.get("metadata") or {}
        self._seq += 1
        self._frame = LiveFrame(
            self._seq,
            str(event.get("data", "")),
            int(metadata.get("deviceWidth") or 0),
            int(metadata.get("deviceHeight") or 0),
        )
        self._pending_ack = int(event.get("sessionId", 0))

    async def _fallback_frame(self, page: PlaywrightObject) -> None:
        now = self._clock()
        if now - self._fallback_at < FALLBACK_INTERVAL_S:
            return
        self._fallback_at = now
        with contextlib.suppress(Exception):
            image = await page.screenshot(type="jpeg", quality=SCREENCAST["quality"])
            digest = hashlib.sha1(image, usedforsecurity=False).hexdigest()
            if digest != self._fallback_digest:
                self._fallback_digest = digest
                width, height = await self.viewport()
                self._seq += 1
                self._frame = LiveFrame(
                    self._seq, base64.b64encode(image).decode("ascii"), width, height
                )

    async def detach(self) -> None:
        """Ekran yayınını bırak (sekme değişti ya da tarayıcı kapandı)."""
        cdp, self._cdp, self._page, self._pending_ack = self._cdp, None, None, None
        if cdp is not None:
            with contextlib.suppress(Exception):
                await cdp.send("Page.stopScreencast")
                await cdp.detach()

    def watch_context(self, context: PlaywrightObject) -> None:
        """Bağlamdaki tüm sekmelerin konsolunu/ağını tek toplayıcıda biriktir."""
        if context is self._context:
            return
        self._context = context
        self.collector = PageEventCollector()
        collector = self.collector
        context.on("console", collector.console)
        context.on("weberror", lambda error: collector.page_error(getattr(error, "error", error)))
        context.on("request", collector.request)
        context.on("response", collector.response)
        context.on("requestfailed", collector.request_failed)

    def page_log(self, *, clear: bool = False) -> PageLog:
        log = PageLog(
            self._page.url if self._page is not None else "",
            self.collector.console_entries(),
            self.collector.network_entries(),
        )
        if clear:
            self.collector = PageEventCollector()
            self._context = None
        return log

    # ------------------------------------------------------------------ girdi
    async def viewport(self) -> tuple[int, int]:
        page = await self._require_page()
        size = page.viewport_size
        if size:
            return int(size["width"]), int(size["height"])
        width, height = await page.evaluate("() => [innerWidth, innerHeight]")
        return int(width), int(height)

    async def to_css(self, x: object, y: object) -> tuple[float, float]:
        """Paneldeki 0..1 konumunu sayfanın CSS piksellerine çevir."""
        nx = min(max(_number(x, "Konum x ve y 0 ile 1 arasında sayı olmalı."), 0.0), 1.0)
        ny = min(max(_number(y, "Konum x ve y 0 ile 1 arasında sayı olmalı."), 0.0), 1.0)
        width, height = await self.viewport()
        return nx * width, ny * height

    async def click(self, x: object, y: object, *, clicks: int = 1, button: str = "left") -> None:
        page = await self._require_page()
        css_x, css_y = await self.to_css(x, y)
        if button not in ("left", "right", "middle"):
            raise LiveInputError("Fare düğmesi left/right/middle olmalı.")
        await page.mouse.click(css_x, css_y, click_count=max(1, min(clicks, 3)), button=button)

    async def scroll(self, x: object, y: object, dx: object, dy: object) -> None:
        page = await self._require_page()
        css_x, css_y = await self.to_css(x, y)
        await page.mouse.move(css_x, css_y)
        await page.mouse.wheel(_scroll(dx), _scroll(dy))

    async def type_text(self, text: object) -> None:
        if not isinstance(text, str) or not text or len(text) > MAX_TYPED_CHARS:
            raise LiveInputError(f"Yazılacak metin 1-{MAX_TYPED_CHARS} karakter olmalı.")
        await (await self._require_page()).keyboard.type(text)

    async def press(self, key: object) -> None:
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise LiveInputError(BAD_KEY.format(key=key))
        await (await self._require_page()).keyboard.press(key)

    async def navigate(self, raw: object) -> None:
        url = self.checked_url(raw)
        page = await self._require_page()
        await page.goto(url, wait_until="commit", timeout=PAGE_TIMEOUT_MS)

    def checked_url(self, raw: object) -> str:
        """Kullanıcının yazdığı adres: şema eklenir, yerelse izin kümesine girer, kapıdan geçer."""
        if not isinstance(raw, str) or not raw.strip():
            raise LiveInputError("Adres gerekir.")
        url = normalize_url(raw.strip())
        origins = self._session.origins
        if origins is not None:
            origins.update(loopback_origins_in(url))
        reason = browser_block_reason(url, origins or ())
        if reason is not None:
            raise LiveInputError(BLOCKED.format(reason=reason))
        return url

    async def history(self, step: str) -> None:
        page = await self._require_page()
        if step == "geri":
            await page.go_back(wait_until="commit", timeout=PAGE_TIMEOUT_MS)
        elif step == "ileri":
            await page.go_forward(wait_until="commit", timeout=PAGE_TIMEOUT_MS)
        else:
            await page.reload(wait_until="commit", timeout=PAGE_TIMEOUT_MS)

    async def new_tab(self, raw: object = None) -> None:
        url = self.checked_url(raw) if raw else ""
        await self._require_page()
        page = await self._session.context.new_page()
        if self._viewport is not None:
            await page.set_viewport_size({"width": self._viewport[0], "height": self._viewport[1]})
        self._session.page = page
        if url:
            await page.goto(url, wait_until="commit", timeout=PAGE_TIMEOUT_MS)

    async def select_tab(self, index: object) -> None:
        self._session.page = await self._tab(index)

    async def close_tab(self, index: object) -> None:
        page = await self._tab(index)
        if len(await self._session.pages()) <= 1:
            raise LiveInputError("Son sekme kapatılamaz; tarayıcıyı kapatmak için Kapat'a bas.")
        await page.close()
        if page is self._session.page:
            self._session.page = (await self._session.pages())[-1]

    async def resize(self, width: object, height: object, scheme: object = None) -> None:
        hata = "Genişlik ve yükseklik tam sayı olmalı."
        size = (
            int(min(max(_number(width, hata), MIN_VIEWPORT), MAX_VIEWPORT)),
            int(min(max(_number(height, hata), MIN_VIEWPORT), MAX_VIEWPORT)),
        )
        self._viewport = size
        page = await self._require_page()
        await page.set_viewport_size({"width": size[0], "height": size[1]})
        if isinstance(scheme, str) and scheme in COLOR_SCHEMES:
            await page.emulate_media(color_scheme=scheme)

    async def _tab(self, index: object) -> PlaywrightObject:
        if not isinstance(index, int) or isinstance(index, bool) or index < 1:
            raise LiveInputError("Sekme numarası 1'den başlayan tam sayı olmalı.")
        pages = await self._session.pages()
        if index > len(pages):
            raise LiveInputError(f"{index} numaralı sekme yok.")
        return pages[index - 1]

    async def _require_page(self) -> PlaywrightObject:
        page = await self.active_page()
        if page is None:
            raise LiveInputError(NOT_OPEN)
        return page


#: Tek kaydırma isteğinin en büyük miktarı (CSS piksel).
MAX_SCROLL = 5_000.0


def _number(value: object, message: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise LiveInputError(message)
    return float(value)


def _scroll(value: object) -> float:
    return max(min(_number(value, "Kaydırma miktarı sayı olmalı."), MAX_SCROLL), -MAX_SCROLL)
