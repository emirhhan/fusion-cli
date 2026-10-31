"""Çalışan önizleme sayfasının KONSOL ve AĞ günlüğü ile ekran görüntüsü (Playwright).

Ölçüldü (31 Ekim, P-041): önizleme paneli iframe'i ayrı kökenli olduğundan ana pencere
onun konsolunu ve isteklerini okuyamaz; `preview_probe` yalnız HATA satırlarını topluyor,
ağ isteklerini hiç listelemiyordu. Claude Code'un Browser pane'inde
`read_console_messages`/`read_network_requests` ile görülen şey burada aynı başsız
tarayıcı yoluyla üretilir: sayfa açılır, yüklenir, `settle_ms` beklenir, toplananlar
döner. Canlı akış değil, o anın fotoğrafıdır; Playwright kurulu değilse `error` dolu
bir günlük döner, hiçbir şey çökmez.

Yalnız yerel (loopback) adresler açılır: panelin gömdüğü adres kümesiyle aynı.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .preview_launch import is_local_url
from .preview_probe import PROBE_TIMEOUT_S, SCREENSHOT_HEIGHT, SCREENSHOT_WIDTH

if TYPE_CHECKING:
    from playwright.async_api import ConsoleMessage, Request, Response

#: Sayfa `load` olayından sonra günlüğün toplanmaya devam edeceği süre (geç istekler, timer'lar).
DEFAULT_SETTLE_MS = 1_000
MAX_SETTLE_MS = 10_000
#: Bellek ve çıktı sınırları (modele giden metin bütçesi).
MAX_CONSOLE_ENTRIES = 200
MAX_NETWORK_ENTRIES = 300
MAX_TEXT_CHARS = 500
#: Ekran görüntüsünün proje içindeki dosyası (`.fusion/onizleme.jpg` ajanın ölçüm karesidir).
SCREENSHOT_FILE = Path(".fusion") / "onizleme-ekran.png"
#: Kabul edilen görünüm ölçüleri (piksel).
MIN_VIEWPORT = 240
MAX_VIEWPORT = 4_000
COLOR_SCHEMES = frozenset({"light", "dark"})

PLAYWRIGHT_MISSING = (
    "Playwright kurulu değil; konsol/ağ günlüğü ve ekran görüntüsü için "
    "`pip install 'fusion-cli[web]'` ve `playwright install chromium`."
)
NOT_LOCAL = "Yalnız yerel (localhost/127.0.0.1) adreslerin günlüğü okunur."


@dataclass(frozen=True, slots=True)
class ConsoleEntry:
    #: `log`, `info`, `warning`, `error`, `debug`; sayfa istisnaları `pageerror`.
    level: str
    text: str
    #: Mesajın geldiği betik ve satır (`main.js:12`); bilinmiyorsa boş.
    source: str = ""


@dataclass(frozen=True, slots=True)
class NetworkEntry:
    method: str
    url: str
    #: HTTP durumu; istek hiç tamamlanmadıysa 0.
    status: int
    #: Kaynak türü (`document`, `script`, `xhr`, `fetch`, `image`…).
    resource_type: str
    #: Ağ hatası metni (bağlantı reddi, iptal); başarılıysa boş.
    failure: str = ""

    @property
    def is_failed(self) -> bool:
        return bool(self.failure) or self.status >= 400 or self.status == 0


@dataclass(frozen=True, slots=True)
class PageLog:
    url: str
    console: tuple[ConsoleEntry, ...] = ()
    requests: tuple[NetworkEntry, ...] = ()
    screenshot: bytes | None = None
    #: Günlük toplanamadıysa nedeni (Playwright yok, adres yerel değil, sayfa açılmadı).
    error: str = ""

    @property
    def error_count(self) -> int:
        return sum(1 for entry in self.console if entry.level in ("error", "pageerror"))

    @property
    def failed_requests(self) -> tuple[NetworkEntry, ...]:
        return tuple(entry for entry in self.requests if entry.is_failed)


@dataclass(frozen=True, slots=True)
class CaptureOptions:
    viewport: tuple[int, int] = (SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT)
    settle_ms: int = DEFAULT_SETTLE_MS
    screenshot: bool = False
    full_page: bool = False
    #: `dark`/`light` ile sayfanın `prefers-color-scheme`'i taklit edilir; None sistemdeki.
    color_scheme: str | None = None


def clamp_settle(value: object) -> int:
    """Kullanıcı/model verisinden bekleme süresi: tam sayı değilse varsayılan, sınır içinde."""
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_SETTLE_MS
    return max(0, min(value, MAX_SETTLE_MS))


def clamp_viewport(width: object, height: object) -> tuple[int, int]:
    def _side(value: object, default: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            return default
        return max(MIN_VIEWPORT, min(value, MAX_VIEWPORT))

    return _side(width, SCREENSHOT_WIDTH), _side(height, SCREENSHOT_HEIGHT)


DEFAULT_CAPTURE = CaptureOptions()


async def collect_page_log(url: str, options: CaptureOptions = DEFAULT_CAPTURE) -> PageLog:
    """Sayfayı başsız tarayıcıda aç; konsol, ağ ve istenirse ekran görüntüsünü topla."""
    if not is_local_url(url):
        return PageLog(url, error=NOT_LOCAL)
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright
    except ImportError:
        return PageLog(url, error=PLAYWRIGHT_MISSING)
    collector = _Collector()
    try:
        async with async_playwright() as driver:
            browser = await driver.chromium.launch()
            try:
                page_options: dict[str, Any] = {
                    "viewport": {"width": options.viewport[0], "height": options.viewport[1]}
                }
                if options.color_scheme in COLOR_SCHEMES:
                    page_options["color_scheme"] = options.color_scheme
                page = await browser.new_page(**page_options)
                page.on("console", collector.console)
                page.on("pageerror", collector.page_error)
                page.on("request", collector.request)
                page.on("response", collector.response)
                page.on("requestfailed", collector.request_failed)
                await page.goto(url, timeout=PROBE_TIMEOUT_S * 1000, wait_until="load")
                if options.settle_ms:
                    await asyncio.sleep(options.settle_ms / 1000)
                shot = (
                    await page.screenshot(type="png", full_page=options.full_page)
                    if options.screenshot
                    else None
                )
            finally:
                await browser.close()
    except PlaywrightError as error:
        return PageLog(url, error=f"Sayfa açılamadı: {str(error).splitlines()[0][:MAX_TEXT_CHARS]}")
    except (OSError, TimeoutError) as error:
        return PageLog(url, error=f"Tarayıcı başlatılamadı: {error}")
    return PageLog(url, collector.console_entries(), collector.network_entries(), shot)


def save_screenshot(root: Path, data: bytes) -> str:
    """Görüntüyü proje içine yaz; köke göreli yol döner (yazılamazsa boş)."""
    try:
        target = root / SCREENSHOT_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError:
        return ""
    return SCREENSHOT_FILE.as_posix()


def format_console(log: PageLog, *, limit: int = 60, only_errors: bool = False) -> str:
    """Modele giden metin: `[seviye] metin (kaynak)` satırları."""
    if log.error:
        return log.error
    entries = [
        entry
        for entry in log.console
        if not only_errors or entry.level in ("error", "pageerror", "warning")
    ]
    if not entries:
        return "Konsolda mesaj yok." if not only_errors else "Konsolda hata ya da uyarı yok."
    lines = [
        f"[{entry.level}] {entry.text}" + (f" ({entry.source})" if entry.source else "")
        for entry in entries[:limit]
    ]
    head = f"{len(entries)} konsol mesajı ({log.error_count} hata)"
    if len(entries) > limit:
        head += f", ilk {limit} gösteriliyor"
    return head + ":\n" + "\n".join(lines)


def format_network(log: PageLog, *, limit: int = 80, only_failed: bool = False) -> str:
    """Modele giden metin: `DURUM YÖNTEM adres [tür]` satırları; başarısızlar başa alınır."""
    if log.error:
        return log.error
    entries = list(log.failed_requests) if only_failed else list(log.requests)
    if not entries:
        return "Başarısız istek yok." if only_failed else "Ağ isteği kaydedilmedi."
    if not only_failed:
        entries.sort(key=lambda entry: not entry.is_failed)  # kararlı: başarısızlar önce
    lines = [
        f"{entry.status or 'YOK'} {entry.method} {entry.url} [{entry.resource_type}]"
        + (f" — {entry.failure}" if entry.failure else "")
        for entry in entries[:limit]
    ]
    head = f"{len(log.requests)} istek, {len(log.failed_requests)} başarısız"
    if len(entries) > limit:
        head += f"; ilk {limit} gösteriliyor"
    return head + ":\n" + "\n".join(lines)


@dataclass
class _Collector:
    """Playwright olaylarını sınırlı tamponlarda toplar; birikim sırasına göre döndürür."""

    _console: list[ConsoleEntry] = field(default_factory=list)
    _requests: dict[int, NetworkEntry] = field(default_factory=dict)
    _order: list[int] = field(default_factory=list)

    def console(self, message: ConsoleMessage) -> None:
        if len(self._console) >= MAX_CONSOLE_ENTRIES:
            return
        location = message.location
        source = ""
        if location.get("url"):
            # Satır içi betikte dosya adı sayfanın kendisidir ("" kalır): "sayfa:12" yazılır.
            dosya = str(location["url"]).rsplit("/", 1)[-1].split("?")[0] or "sayfa"
            source = f"{dosya}:{location.get('lineNumber', 0)}"
        self._console.append(ConsoleEntry(str(message.type), message.text[:MAX_TEXT_CHARS], source))

    def page_error(self, error: object) -> None:
        if len(self._console) < MAX_CONSOLE_ENTRIES:
            self._console.append(ConsoleEntry("pageerror", str(error)[:MAX_TEXT_CHARS]))

    def request(self, request: Request) -> None:
        if len(self._requests) >= MAX_NETWORK_ENTRIES:
            return
        key = id(request)
        self._order.append(key)
        self._requests[key] = NetworkEntry(
            request.method, request.url[:MAX_TEXT_CHARS], 0, request.resource_type
        )

    def response(self, response: Response) -> None:
        key = id(response.request)
        entry = self._requests.get(key)
        if entry is not None:
            self._requests[key] = NetworkEntry(
                entry.method, entry.url, response.status, entry.resource_type
            )

    def request_failed(self, request: Request) -> None:
        key = id(request)
        entry = self._requests.get(key)
        if entry is not None:
            failure = ""
            with contextlib.suppress(AttributeError, TypeError):
                failure = str(request.failure)
            # 404 stylesheet önce `response(404)` sonra `requestfailed(ERR_ABORTED)` üretir
            # (ölçüldü, 31 Ekim): bilinen HTTP durumu silinmez, hata metni eklenir.
            self._requests[key] = NetworkEntry(
                entry.method,
                entry.url,
                entry.status,
                entry.resource_type,
                failure or "istek tamamlanmadı",
            )

    def console_entries(self) -> tuple[ConsoleEntry, ...]:
        return tuple(self._console)

    def network_entries(self) -> tuple[NetworkEntry, ...]:
        return tuple(self._requests[key] for key in self._order if key in self._requests)
