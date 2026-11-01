"""Terminalde Chrome bağlantısı: `--chrome`, `/chrome`, başlangıç ve kurulum soruları (#421).

Claude Code (code.claude.com/docs/en/chrome):

- `claude --chrome` oturumu tarayıcıya bağlar; `--no-chrome` kapatır. **Enabled by default**
  açıksa bayrak gerekmez. Chrome açık değilse oturum yine normal başlar.
- İlk `--chrome` açılışında bir kerelik tanıtım (Enter ile devam).
- Bayraksız açılışta eklenti bulunur ve tercih yoksa "extension detected" sorusu: **Yes** ayarı
  açar ve bu oturumu bağlar; **No**/Esc ayarı kapatır, kurulumu önermeyi bırakır.
- Eklenti yokken tarayıcı gerekince oturumda en çok bir kez "Claude wants to use your
  browser": Install extension / Not now / Don't ask again.
- Projenin `.claude/settings(.local).json` `env` bloğundaki `CLAUDE_CODE_ENABLE_CFC` yok
  sayılır ve uyarılır: bir depo kullanıcının tarayıcısını bağlatamaz.

Köprü masaüstüyle aynı `ChromeBridge`'dir (yerel 127.0.0.1, rastgele anahtar, yerel
mesajlaşma ile eşleşme); araçlar `ToolContext.chrome` doluyken modele sunulur.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from ...config import chrome_cli_prefs
from ...core.errors import ConfigError
from ...ui import chrome_messages as text
from ...ui import theme
from ...ui.picker import Choice, pick

#: Claude Code'un ortam değişkeni (kullanıcı kabuğu ya da `~/.claude/settings.json` `env`).
CFC_ENV = "CLAUDE_CODE_ENABLE_CFC"
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_PROJECT_SETTINGS = ("settings.json", "settings.local.json")

Chooser = Callable[[str, list[Choice]], Awaitable[str | None]]


class BridgeLike(Protocol):
    @property
    def running(self) -> bool: ...

    def status(self, *, reveal_token: bool = False) -> dict[str, Any]: ...

    async def start(self) -> dict[str, Any]: ...

    async def close(self) -> None: ...

    async def invoke(self, operation: str, args: dict[str, Any]) -> dict[str, Any]: ...


BridgeFactory = Callable[[Callable[[], Awaitable[dict[str, Any]]], Callable[[], bool]], BridgeLike]


async def _pick_inline(title: str, choices: list[Choice]) -> str | None:
    return await asyncio.to_thread(pick, choices, title=title)


def _extension_installed() -> bool:
    from ...appserver.chrome_install import install_status

    try:
        return bool(install_status()["eklenti_yuklu"])
    except (OSError, KeyError, ValueError):
        return False


async def _guided_install() -> dict[str, Any]:
    from ...appserver.chrome_autoinstall import auto_install_async

    return await auto_install_async()


def _default_bridge(
    installer: Callable[[], Awaitable[dict[str, Any]]], installed: Callable[[], bool]
) -> BridgeLike:
    from ...appserver.chrome_bridge import ChromeBridge

    return ChromeBridge(installer=installer, extension_installed=installed)


@dataclass
class ChromeSession:
    """Oturumun Chrome köprüsü ve oturum boyu kurulum sorusu durumu."""

    bridge: BridgeLike
    choose: Chooser = _pick_inline
    installer: Callable[[], Awaitable[dict[str, Any]]] = _guided_install
    extension_installed: Callable[[], bool] = _extension_installed
    install_asked: bool = field(default=False)

    async def install(self) -> dict[str, Any]:
        """Köprünün kurulum kancası: oturumda en çok bir kez üç seçenekli soru."""
        if self.install_asked or chrome_cli_prefs.load().dont_ask_install:
            return {"asama": "izin_gerekli", "metin": text.INSTALL_DECLINED}
        self.install_asked = True
        selected = await self.choose(text.INSTALL_TITLE, _install_choices())
        if selected == "never":
            _save_quietly(dont_ask_install=True)
        if selected != "install":
            return {"asama": "izin_gerekli", "metin": text.INSTALL_DECLINED}
        return await self.installer()


def _install_choices() -> list[Choice]:
    return [
        Choice("install", text.INSTALL_YES, text.INSTALL_YES_DESC),
        Choice("later", text.INSTALL_LATER, text.INSTALL_LATER_DESC),
        Choice("never", text.INSTALL_NEVER, text.INSTALL_NEVER_DESC),
    ]


def _save_quietly(**changes: bool | None) -> None:
    try:
        chrome_cli_prefs.update(None, **changes)
    except ConfigError:
        return


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in _TRUTHY


def _settings_env(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    env = payload.get("env") if isinstance(payload, dict) else None
    return env if isinstance(env, dict) else {}


def project_warning(root: Path) -> str:
    """Proje ayarı Chrome'u açmaya çalıştıysa uyarı; yoksa boş metin."""
    folder = root / ".claude"
    if any(_truthy(_settings_env(folder / name).get(CFC_ENV, "")) for name in _PROJECT_SETTINGS):
        return text.PROJECT_IGNORED
    return ""


def user_requested(home: Path, environ: Mapping[str, str]) -> bool:
    """Kullanıcının kabuğu ya da kullanıcı ayarı `CLAUDE_CODE_ENABLE_CFC=1` diyor mu."""
    if _truthy(environ.get(CFC_ENV, "")):
        return True
    return _truthy(_settings_env(home / ".claude" / "settings.json").get(CFC_ENV, ""))


def resolve(
    flag: bool | None,
    prefs: chrome_cli_prefs.ChromeCliPrefs,
    *,
    home: Path,
    environ: Mapping[str, str],
) -> bool:
    """`--chrome`/`--no-chrome` önce; sonra kullanıcı ortamı; sonra Enabled by default."""
    if flag is not None:
        return flag
    return user_requested(home, environ) or bool(prefs.enabled_by_default)


def _ask_detected(picker: Callable[..., str | None]) -> bool:
    choices = [
        Choice("yes", text.DETECTED_YES, text.DETECTED_YES_DESC),
        Choice("no", text.DETECTED_NO, text.DETECTED_NO_DESC),
    ]
    enabled = picker(choices, title=text.DETECTED_TITLE) == "yes"
    _save_quietly(enabled_by_default=enabled, **({} if enabled else {"dont_ask_install": True}))
    return enabled


def _show_intro(console: Console, wait_enter: Callable[[], object]) -> None:
    console.print(Panel(text.INTRO_BODY, title=f"[bold]{text.INTRO_TITLE}[/bold]"))
    with contextlib.suppress(EOFError, KeyboardInterrupt):
        wait_enter()
    _save_quietly(intro_seen=True)


async def open_for_session(
    console: Console,
    *,
    root: Path,
    home: Path,
    flag: bool | None,
    interactive: bool,
    environ: Mapping[str, str] | None = None,
    picker: Callable[..., str | None] = pick,
    wait_enter: Callable[[], object] | None = None,
    bridge_factory: BridgeFactory = _default_bridge,
    extension_installed: Callable[[], bool] = _extension_installed,
) -> ChromeSession | None:
    """Oturum açılışında Chrome'u bağla; kapalıysa `None`."""
    env = os.environ if environ is None else environ
    warning = project_warning(root)
    if warning:
        console.print(f"[{theme.WARN}]{escape(warning)}[/{theme.WARN}]")
    prefs = chrome_cli_prefs.load()
    enabled = resolve(flag, prefs, home=home, environ=env)
    if (
        not enabled
        and flag is None
        and interactive
        and prefs.enabled_by_default is None
        and not prefs.dont_ask_install
        and extension_installed()
    ):
        enabled = _ask_detected(picker)
    if not enabled:
        return None
    if interactive and not prefs.intro_seen:
        _show_intro(console, wait_enter or (lambda: console.input(text.INTRO_CONTINUE)))
    session = ChromeSession(bridge=_placeholder(), extension_installed=extension_installed)
    session.bridge = bridge_factory(session.install, extension_installed)
    try:
        await session.bridge.start()
    except OSError as error:
        console.print(f"[{theme.WARN}]{escape(str(error))}[/{theme.WARN}]")
    return session


def _placeholder() -> BridgeLike:
    """Köprü kurulum kancası `session.install`'a bağlanmadan önceki geçici değer."""
    return _ClosedBridge()


class _ClosedBridge:
    @property
    def running(self) -> bool:
        return False

    def status(self, *, reveal_token: bool = False) -> dict[str, Any]:
        return {"calisiyor": False, "bagli": False}

    async def start(self) -> dict[str, Any]:
        return self.status()

    async def close(self) -> None:
        return None

    async def invoke(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        raise ConnectionError(text.STATUS_OFF_HINT)


async def close_session(session: ChromeSession | None) -> None:
    if session is not None:
        await session.bridge.close()


def bind_chooser(session: ChromeSession | None, chooser: Chooser) -> None:
    """Tam ekran TUI kendi modal seçicisini verir (iç içe seçici açılmaz)."""
    if session is not None:
        session.choose = chooser


def bridge_of(session: ChromeSession | None) -> BridgeLike | None:
    """Turun `ToolContext.chrome` değeri: Chrome kapalıyken `None` (araçlar sunulmaz)."""
    return session.bridge if session is not None else None
