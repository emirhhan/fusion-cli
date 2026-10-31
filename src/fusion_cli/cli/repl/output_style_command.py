"""`/output-style [ad]` (P-068): çıktı stilini listele / seç; seçim kalıcıdır."""

from __future__ import annotations

from dataclasses import replace

from ...config.settings_access import write_setting
from ...core.errors import ConfigError
from ...engines.agent.output_style import DEFAULT_STYLE, discover_styles, find_style
from ...ui import messages
from ...ui.picker import Choice
from .state import ReplState

#: Kalıcı yazılan ayar yolu.
SETTING_PATH = "runtime.output_style"


def style_choices(state: ReplState) -> list[Choice]:
    """Uygulama-içi seçici (TUI) ve masaüstü seçici için stil listesi."""
    current = state.config.runtime.output_style
    return [
        Choice(
            style.name,
            style.name + (messages.OUTPUT_STYLE_CURRENT if style.name == current else ""),
            f"{style.description} [{style.source}]".strip(),
        )
        for style in discover_styles(state.home, state.root)
    ]


def format_styles(state: ReplState) -> str:
    rows = [messages.OUTPUT_STYLE_HEADER.format(current=state.config.runtime.output_style)]
    for choice in style_choices(state):
        rows.append(f"  {choice.label:<16} {choice.description}")
    rows.append(messages.OUTPUT_STYLE_HINT)
    return "\n".join(rows)


def output_style_command(state: ReplState, argument: str) -> str:
    wanted = argument.strip().lower()
    if not wanted:
        return format_styles(state)
    if wanted != DEFAULT_STYLE and find_style(wanted, state.home, state.root) is None:
        known = ", ".join(style.name for style in discover_styles(state.home, state.root))
        return messages.OUTPUT_STYLE_UNKNOWN.format(name=wanted, known=known)
    try:
        state.config, _ = write_setting(state.config, SETTING_PATH, wanted)
    except ConfigError as error:
        # Dosyaya yazılamadıysa seçim yine oturumda geçerli olsun; kullanıcı nedenini görür.
        state.config = replace(
            state.config, runtime=replace(state.config.runtime, output_style=wanted)
        )
        return messages.OUTPUT_STYLE_SET_UNSAVED.format(name=wanted, error=error)
    return messages.OUTPUT_STYLE_SET.format(name=wanted)
