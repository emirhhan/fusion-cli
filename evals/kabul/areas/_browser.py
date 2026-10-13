"""Web alanı denetçilerinin ortak tarayıcı yardımcıları (playwright senkron API).

Ajanın ürettiği klasör geçici bir yerel statik sunucuyla açılır (`file://` yerine:
`fetch`, modül ve göreli yol kullanan sayfalar da çalışsın). Denetçi playwright ya da
chromium bulamazsa `BrowserUnavailableError` fırlatır; çağıran bunu `invalid_reason`
yapar — bu bir başarısızlık değil geçersizliktir. Fusion'ın kendi tarayıcı araçları
BİLEREK kullanılmaz: ölçüm ajandan bağımsız olmalıdır.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from fusion_cli.core.redaction import redact

if TYPE_CHECKING:
    from playwright.sync_api import ConsoleMessage, Dialog, Page, ViewportSize

#: Pencere boyutu; masaüstü düzeni ölçülür (animasyon/oyun için yeterli alan).
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800
#: Playwright işlemleri için varsayılan zaman aşımı (ms).
PAGE_TIMEOUT_MS = 15_000
#: Sunucunun kapanmasını bekleme süresi (sn).
SERVER_JOIN_TIMEOUT_S = 5.0
_FAVICON_PATH = "/favicon.ico"
_NO_CONTENT = 204
_ERROR_CONSOLE_TYPE = "error"


class BrowserUnavailableError(RuntimeError):
    """Playwright ya da chromium yok: ölçüm yapılamaz (geçersiz, başarısız değil)."""


class PageInteractionError(RuntimeError):
    """Sayfa açılırken/etkileşimde tarayıcı hatası (çökme, zaman aşımı); ajanın sayfası bozuk."""


class ConsoleLog:
    """Sayfanın konsol hatalarını ve yakalanmamış istisnalarını biriktirir."""

    def __init__(self) -> None:
        self._errors: list[str] = []

    def add(self, message: str) -> None:
        self._errors.append(message)

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(self._errors)


@dataclass(frozen=True, slots=True)
class OpenedPage:
    """Açık sayfa, konsol kaydı ve sunucu adresi."""

    page: Page
    console: ConsoleLog
    base_url: str


class _QuietHandler(SimpleHTTPRequestHandler):
    """Günlük yazmayan sunucu; olmayan favicon için 404 yerine 204 döner."""

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        directory = Path(self.directory or ".")
        if self.path.split("?")[0] == _FAVICON_PATH and not (directory / "favicon.ico").exists():
            self.send_response(_NO_CONTENT)
            self.end_headers()
            return
        super().do_GET()


@contextmanager
def static_server(root: Path) -> Iterator[str]:
    """Klasörü yerel bir portta sun; adresi ver, çıkışta kapat."""
    handler = partial(_QuietHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{int(server.server_address[1])}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=SERVER_JOIN_TIMEOUT_S)


def _attach_listeners(page: Page, console: ConsoleLog) -> None:
    """Konsol hatası, sayfa istisnası ve diyalog (alert) dinleyicilerini bağla."""

    def on_console(message: ConsoleMessage) -> None:
        if message.type == _ERROR_CONSOLE_TYPE:
            source_url = _console_source_url(message.location["url"])
            detail = f"{message.text} [kaynak: {source_url}]" if source_url else message.text
            console.add(detail)

    def on_dialog(dialog: Dialog) -> None:
        dialog.dismiss()

    page.on("console", on_console)
    page.on("pageerror", lambda error: console.add(str(error)))
    page.on("dialog", on_dialog)


def _console_source_url(url: str) -> str:
    """Kaynağı sır içerebilen kimlik, sorgu ve parça olmadan teşhise ekle."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https", "file"}:
        return ""
    authority = parsed.netloc.rsplit("@", 1)[-1]
    return redact(urlunsplit((parsed.scheme, authority, parsed.path, "", "")))


@contextmanager
def open_page(root: Path, *, init_script: str | None = None) -> Iterator[OpenedPage]:
    """Klasörü sunup headless chromium'da bir sayfa aç.

    `init_script` her gezintide sayfa betiklerinden ÖNCE çalışır (sayaç enjeksiyonu için).
    """
    # Playwright opsiyonel ekstradır; import yokluğunda denetçi geçersiz döner.
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise BrowserUnavailableError("playwright kurulu değil") from error
    with static_server(root) as base_url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError as error:
            raise BrowserUnavailableError(f"chromium başlatılamadı: {error}") from error
        try:
            viewport: ViewportSize = {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
            context = browser.new_context(viewport=viewport)
            if init_script is not None:
                context.add_init_script(init_script)
            page = context.new_page()
            page.set_default_timeout(PAGE_TIMEOUT_MS)
            console = ConsoleLog()
            _attach_listeners(page, console)
            yield OpenedPage(page=page, console=console, base_url=base_url)
        except PlaywrightError as error:
            raise PageInteractionError(str(error)) from error
        finally:
            browser.close()


def navigate(opened: OpenedPage, entry: str = "index.html") -> None:
    """Giriş sayfasını `domcontentloaded` olana dek aç."""
    opened.page.goto(f"{opened.base_url}/{entry}", wait_until="domcontentloaded")
