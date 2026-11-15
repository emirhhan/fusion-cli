"""Claude Code Settings paneli: Status · Config · Usage sekmeleri (#210, #225).

Claude Code'da argümansız `/config` Settings arayüzünü Config sekmesinde, `/status` aynı
arayüzü Status sekmesinde açar; sekmeler arasında sol/sağ oklarla geçilir. Config
sekmesinde Enter seçili ayarın değer listesini açar; seçilen değer `/config key=value`
yoluyla (Claude ayar adları, kalıcı yazma) uygulanır. Panel yüzeyden bağımsızdır:
tam ekran TUI `FusionTui.await_choice`, satır içi REPL `ui.picker.pick` ile sürer.
"""

from __future__ import annotations

import io
from collections.abc import Awaitable, Callable, Sequence

from rich.console import Console

from ...ui import messages
from ...ui.picker import Choice
from . import model_picker, output_style_command
from .config_claude_keys import CLAUDE_THEMES
from .config_command import config_command
from .state import ReplState

STATUS, CONFIG, USAGE = "Status", "Config", "Usage"
TABS = (STATUS, CONFIG, USAGE)
TAB_KEYS = ("left", "right")
#: Bilgi satırlarının değer öneki; Enter bunlarda paneli kapatır.
INFO_PREFIX = "info:"
_RENDER_WIDTH = 100

Asker = Callable[[str, Sequence[Choice], tuple[str, ...], str], str | None]
AsyncAsker = Callable[[str, Sequence[Choice], tuple[str, ...], str], Awaitable[str | None]]


def tab_title(tab: str) -> str:
    bar = "  ".join(f"[{name}]" if name == tab else name for name in TABS)
    return messages.SETTINGS_TITLE.format(tabs=bar)


def _rendered_lines(render: Callable[[Console], None]) -> list[str]:
    console = Console(file=io.StringIO(), record=True, width=_RENDER_WIDTH, no_color=True)
    render(console)
    return [line.rstrip() for line in console.export_text().splitlines() if line.strip()]


def _info_rows(lines: Sequence[str]) -> tuple[Choice, ...]:
    return tuple(Choice(f"{INFO_PREFIX}{index}", line) for index, line in enumerate(lines))


def status_rows(state: ReplState) -> tuple[Choice, ...]:
    from .status_view import render_status

    return _info_rows(_rendered_lines(lambda console: render_status(state, console)))


def usage_rows(state: ReplState) -> tuple[Choice, ...]:
    from .help_view import _usage

    return _info_rows(_rendered_lines(lambda console: _usage(state, console)))


def _theme_name(state: ReplState) -> str:
    current = getattr(state.config.runtime, "terminal_theme", "koyu")
    return next((claude for claude, fusion in CLAUDE_THEMES.items() if fusion == current), current)


def config_values(state: ReplState) -> dict[str, str]:
    """Claude ayar adı → etkin değer (panelin Config sekmesi)."""
    runtime = state.config.runtime
    return {
        "model": state.config.agent.model,
        "theme": _theme_name(state),
        "outputStyle": str(getattr(runtime, "output_style", "default")),
        "editorMode": "vim" if getattr(runtime, "vim_mode", False) else "normal",
        "tui": "fullscreen" if getattr(runtime, "tui", "fullscreen") == "fullscreen" else "default",
    }


def config_rows(state: ReplState) -> tuple[Choice, ...]:
    return tuple(Choice(key, f"{key}: {value}") for key, value in config_values(state).items())


def value_choices(state: ReplState, key: str) -> tuple[Choice, ...]:
    """Bir ayarın seçilebilir değerleri; bilinmeyen ad için boş."""
    if key == "model":
        return model_picker.model_choices(state.config)
    if key == "theme":
        return tuple(Choice(name, name) for name in CLAUDE_THEMES)
    if key == "outputStyle":
        return tuple(output_style_command.style_choices(state))
    if key == "editorMode":
        return (Choice("normal", "normal"), Choice("vim", "vim"))
    if key == "tui":
        return (Choice("default", "default"), Choice("fullscreen", "fullscreen"))
    return ()


def tab_rows(state: ReplState, tab: str) -> tuple[Choice, ...]:
    if tab == STATUS:
        return status_rows(state)
    if tab == USAGE:
        return usage_rows(state)
    return config_rows(state)


def _split(picked: str) -> tuple[str, str]:
    for key in TAB_KEYS:
        if picked.startswith(f"{key}:"):
            return key, picked[len(key) + 1 :]
    return "", picked


def _next_tab(tab: str, key: str) -> str:
    step = -1 if key == "left" else 1
    return TABS[(TABS.index(tab) + step) % len(TABS)]


def run(state: ReplState, ask: Asker, tab: str = CONFIG) -> str:
    """Paneli sür (eşzamanlı seçici); uygulanan ayarların notlarını döndür."""
    notes: list[str] = []
    while state.running:
        picked = ask(tab_title(tab), tab_rows(state, tab), TAB_KEYS, "")
        key, value = _split(picked) if picked is not None else ("", "")
        if key:
            tab = _next_tab(tab, key)
            continue
        if picked is None or tab != CONFIG:
            break
        current = config_values(state).get(value, "")
        chosen = ask(value, value_choices(state, value), (), current)
        if chosen is not None:
            notes.append(config_command(state, f"{value}={chosen}"))
    return "\n".join(notes)


async def run_async(state: ReplState, ask: AsyncAsker, tab: str = CONFIG) -> str:
    """`run`'un tam ekran TUI eşi."""
    notes: list[str] = []
    while state.running:
        picked = await ask(tab_title(tab), tab_rows(state, tab), TAB_KEYS, "")
        key, value = _split(picked) if picked is not None else ("", "")
        if key:
            tab = _next_tab(tab, key)
            continue
        if picked is None or tab != CONFIG:
            break
        current = config_values(state).get(value, "")
        chosen = await ask(value, value_choices(state, value), (), current)
        if chosen is not None:
            notes.append(config_command(state, f"{value}={chosen}"))
    return "\n".join(notes)
