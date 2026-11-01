"""Eklenti açılınca/kurulunca ayarlanmamış `userConfig` seçeneklerini sor (Claude Code, #388).

Claude Code `/plugin`: seçenekleri olan eklenti etkinleştirilince yapılandırma penceresi açılır;
girilen değerler kaydedilir ("Enabled and configured <ad>"), boş geçilirse "Plugin enabled.
Configuration skipped." Hassas seçenek ekrana yansıtılmadan sorulur.

Fusion'da satır-içi REPL'de terminal varsa her ayarlanmamış seçenek sırayla sorulur (Enter =
atla). TUI'de komut bitince uygulama-içi metin istemiyle sorulur (hassas seçenek yıldızlı, girdi
geçmişine yazılmaz; `drain_tui`). Terminal olmayan yüzeylerde `/plugin configure <id>` ipucu.
"""

from __future__ import annotations

import getpass
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from ...config import plugin_user_config as user_config
from ...config.plugin_store import PluginRecord, plugin_folder, plugins_dir
from ...core.plugins import PluginError

CONFIGURED = "Enabled and configured {name}."
SKIPPED = "Plugin enabled. Configuration skipped."
HINT = "Ayarlanmamış seçenekler var: {keys}. Ayarlamak için: /plugin configure {ident}"
FAILED = "Failed to save configuration: {reason}"

Asker = Callable[[user_config.UserOption], "str | None"]
AsyncText = Callable[[], Awaitable[str]]

#: TUI'de sorulmayı bekleyen (kayıt, kimlik); komut bitince `drain_tui` sorar.
_TUI_PENDING: list[tuple[PluginRecord, str]] = []


def _tui_running() -> bool:
    try:
        from prompt_toolkit.application.current import get_app_or_none
    except ImportError:
        return False
    app = get_app_or_none()
    return app is not None and app.is_running


def can_prompt() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty() and not _tui_running()


def ask_terminal(option: user_config.UserOption) -> str | None:
    """Tek seçeneği sor; boş/iptal None."""
    label = f"{option.title} ({option.key}{', zorunlu' if option.required else ''}): "
    try:
        value = getpass.getpass(label) if option.sensitive else input(label)
    except (EOFError, KeyboardInterrupt):
        return None
    return value.strip() or None


def unset_options(record: PluginRecord, base: Path) -> tuple[user_config.UserOption, ...]:
    try:
        schema = user_config.read_schema(plugin_folder(record, base))
    except PluginError:
        return ()
    if not schema:
        return ()
    saved = set(user_config.saved_values(record.name, base))
    return tuple(o for o in schema if o.key not in saved and o.default is None)


def prompt_after_enable(
    record: PluginRecord, ident: str, *, ask: Asker | None = None, base: Path | None = None
) -> str:
    """Ayarlanmamış seçenek yoksa boş; varsa sor ve kaydet ya da ipucu ver."""
    store = base or plugins_dir()
    pending = unset_options(record, store)
    if not pending:
        return ""
    if ask is None:
        if _tui_running() and base is None:
            _TUI_PENDING.append((record, ident))
            return ""
        if not can_prompt():
            return HINT.format(keys=", ".join(o.key for o in pending), ident=ident)
        ask = ask_terminal
    answers = {o.key: value for o in pending if (value := ask(o)) is not None}
    return _save(record, ident, answers, store)


def _save(record: PluginRecord, ident: str, answers: dict[str, str], store: Path) -> str:
    if not answers:
        return SKIPPED
    schema = user_config.read_schema(plugin_folder(record, store))
    try:
        user_config.save_values(record.name, schema, answers, store)
    except PluginError as error:
        return FAILED.format(reason=error)
    return CONFIGURED.format(name=ident)


def label(option: user_config.UserOption) -> str:
    return f"{option.title} ({option.key}{', zorunlu' if option.required else ''}):"


async def drain_tui(
    show: Callable[[str], None], ask_text: AsyncText, ask_secret: AsyncText
) -> list[str]:
    """TUI: bekleyen eklentilerin ayarlanmamış seçeneklerini uygulama-içi istemle sor."""
    results: list[str] = []
    while _TUI_PENDING:
        record, ident = _TUI_PENDING.pop(0)
        store = plugins_dir()
        answers: dict[str, str] = {}
        for option in unset_options(record, store):
            show(label(option))
            value = (await (ask_secret() if option.sensitive else ask_text())).strip()
            if value:
                answers[option.key] = value
        results.append(_save(record, ident, answers, store))
    return results
