"""`/chrome`: bağlantı durumu, Reconnect extension, Select browser…, Enabled by default (#421).

Claude Code'da `/chrome` durum panelini ("Status: Enabled", "Extension: Installed") ve
seçenekleri gösterir. Fusion terminalinde seçenekler alt komuttur:
`/chrome reconnect`, `/chrome select`, `/chrome default on|off`, `/chrome install`,
`/chrome permissions`. Enabled by default sonraki oturumlara uygulanır (çalışan oturuma değil).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from ...config import chrome_cli_prefs
from ...core.errors import ConfigError
from ...ui import chrome_messages as text
from ...ui import theme
from .chrome_cli import ChromeSession

_ON = frozenset({"on", "ac", "aç", "true", "1"})
_OFF = frozenset({"off", "kapat", "false", "0"})


def status_lines(session: ChromeSession | None, *, extension_installed: bool) -> list[str]:
    prefs = chrome_cli_prefs.load()
    if session is None:
        status = text.STATUS_DISABLED
    elif session.bridge.running:
        status = text.STATUS_ENABLED
    else:
        status = text.STATUS_NOT_CONNECTED
    extension = text.EXTENSION_INSTALLED if extension_installed else text.EXTENSION_MISSING
    lines = [
        text.STATUS_LINE.format(status=status),
        text.EXTENSION_LINE.format(extension=extension),
    ]
    if session is not None and session.bridge.running:
        connected = bool(session.bridge.status().get("bagli"))
        browser = text.BROWSER_CONNECTED if connected else text.BROWSER_WAITING
        lines.append(text.BROWSER_LINE.format(browser=browser))
        in_use = next((b for b in _browsers(session) if b.get("inUse")), None)
        if in_use is not None:
            lines.append(text.BROWSER_SELECTED.format(name=in_use["name"], device=in_use["deviceId"]))
    default = text.DEFAULT_ON if prefs.enabled_by_default else text.DEFAULT_OFF
    lines.append(text.DEFAULT_LINE.format(value=default))
    lines.append("")
    lines.append(text.STATUS_OFF_HINT if session is None else text.STATUS_OPTIONS)
    return lines


async def reconnect(session: ChromeSession | None) -> str:
    if session is None:
        return text.STATUS_OFF_HINT
    await session.bridge.close()
    await session.bridge.start()
    return text.RECONNECTED


def _browsers(session: ChromeSession) -> list[dict[str, Any]]:
    """Köprünün bağlı tarayıcıları (çoklu cihaz bilmeyen köprüde boş)."""
    lister = getattr(session.bridge, "browsers", None)
    return list(lister()) if callable(lister) else []


def select(session: ChromeSession | None, argument: str) -> str:
    """Select browser… (#432): bağlı tarayıcıları listeler; numara ya da deviceId ile seçer."""
    if session is None:
        return text.SELECT_OFF
    browsers = _browsers(session)
    if not browsers:
        return text.SELECT_NONE
    choice = argument.strip()
    if not choice:
        items = [
            text.SELECT_ITEM.format(
                index=index,
                name=browser["name"],
                device=browser["deviceId"],
                mark=text.SELECT_IN_USE if browser.get("inUse") else "",
            )
            for index, browser in enumerate(browsers, start=1)
        ]
        return "\n".join([text.SELECT_LIST_TITLE, *items])
    device = choice
    if choice.isdigit() and 1 <= int(choice) <= len(browsers):
        device = str(browsers[int(choice) - 1]["deviceId"])
    selector = getattr(session.bridge, "select_browser", None)
    chosen = selector(device) if callable(selector) else None
    if chosen is None:
        return text.SELECT_UNKNOWN.format(argument=choice)
    return text.SELECT_DONE.format(name=chosen["name"], device=chosen["deviceId"])


def set_default(argument: str) -> str:
    value = argument.strip().lower()
    if value not in _ON | _OFF:
        return text.DEFAULT_USAGE
    enabled = value in _ON
    try:
        chrome_cli_prefs.update(enabled_by_default=enabled)
    except ConfigError as error:
        return text.SAVE_FAILED.format(error=error)
    return text.DEFAULT_SET_ON if enabled else text.DEFAULT_SET_OFF


async def install(installer: Callable[[], Awaitable[dict[str, Any]]]) -> str:
    try:
        result = await installer()
    except (OSError, RuntimeError, ValueError) as error:
        return text.INSTALL_FAILED.format(error=error)
    detail = str(result.get("metin") or result.get("asama") or "")
    return text.INSTALL_STARTED.format(detail=detail)


async def run(session: ChromeSession | None, argument: str, console: Console) -> None:
    """REPL'in asenkron `/chrome` işleyicisi; çıktıyı kendisi basar."""
    action, _, rest = argument.strip().partition(" ")
    action = action.lower()
    installed = session.extension_installed if session is not None else _probe_installed
    if action in ("", "status", "durum"):
        body = "\n".join(status_lines(session, extension_installed=installed()))
        console.print(Panel(escape(body), title=f"[bold]{text.STATUS_TITLE}[/bold]"))
        return
    if action in ("reconnect", "yeniden-bagla"):
        message = await reconnect(session)
    elif action in ("select", "sec", "seç"):
        message = select(session, rest)
    elif action in ("default", "varsayilan"):
        message = set_default(rest)
    elif action in ("install", "kur"):
        message = await install(session.installer if session is not None else _guided)
    elif action in ("permissions", "izinler"):
        message = text.PERMISSIONS_HINT
    else:
        message = text.UNKNOWN.format(argument=action)
    console.print(f"[{theme.INFO}]{escape(message)}[/{theme.INFO}]")


def _probe_installed() -> bool:
    from .chrome_cli import _extension_installed

    return _extension_installed()


async def _guided() -> dict[str, Any]:
    from .chrome_cli import _guided_install

    return await _guided_install()


def desktop_handler(_state: object, _argument: str) -> str:
    """Kayıt defterindeki eşzamanlı işleyici (masaüstü/uzak yol)."""
    return text.DESKTOP_ONLY_CLI
