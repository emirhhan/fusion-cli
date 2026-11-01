"""`/config` için Claude Code ayar adları (#210, #217).

Claude Code `/config key=value ...` biçiminde `model`, `theme`, `outputStyle`, `editorMode`
gibi adları kabul eder. Bu modül o adları Fusion'ın karşılıklarına bağlar; her biri Fusion'ın
kendi komutundaki doğrulama ve kalıcı yazma yolunu kullanır. Fusion'ın `bölüm.alan` yolları
`config_command` içinde olduğu gibi çalışmaya devam eder.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ...config.settings_access import write_setting
from ...core.errors import ConfigError
from ...ui import messages
from . import model_switch, output_style_command, view_commands
from .state import ReplState

#: Claude `theme` değerleri → Fusion terminal paleti (`runtime.terminal_theme`).
CLAUDE_THEMES = {
    "dark": "koyu",
    "light": "acik",
    "dark-ansi": "ansi",
    "light-ansi": "ansi",
    "dark-daltonized": "daltonizm",
    "light-daltonized": "daltonizm",
}
#: Claude `editorMode` değerleri → `runtime.vim_mode`.
EDITOR_MODES = {"vim": True, "normal": False}
VIM_SETTING_PATH = "runtime.vim_mode"


def set_editor_mode(state: ReplState, value: str) -> str:
    """`editorMode=vim|normal` — vim düzenleme kipini aç/kapa ve kalıcı yaz."""
    wanted = value.strip().lower()
    if wanted not in EDITOR_MODES:
        return messages.CONFIG_EDITOR_MODE_UNKNOWN.format(value=value)
    enabled = EDITOR_MODES[wanted]
    try:
        state.config, _ = write_setting(
            state.config, VIM_SETTING_PATH, "true" if enabled else "false"
        )
    except ConfigError as error:
        state.config = replace(
            state.config, runtime=replace(state.config.runtime, vim_mode=enabled)
        )
        return messages.CONFIG_EDITOR_MODE_UNSAVED.format(mode=wanted, error=error)
    return messages.CONFIG_EDITOR_MODE_SET.format(mode=wanted)


def _theme(state: ReplState, value: str) -> str:
    wanted = value.strip().lower()
    return view_commands.theme_command(state, CLAUDE_THEMES.get(wanted, wanted))


def _model(state: ReplState, value: str) -> str:
    try:
        state.config, message = model_switch.switch_and_save(state.config, value.strip())
    except ConfigError as error:
        return str(error)
    return message


#: Claude ayar adı → işleyici (değer metnini alır, kullanıcıya satır döndürür).
CLAUDE_KEYS: dict[str, Callable[[ReplState, str], str]] = {
    "model": _model,
    "theme": _theme,
    "outputStyle": output_style_command.output_style_command,
    "editorMode": set_editor_mode,
    "tui": view_commands.tui_command,
}


def claude_handler(key: str) -> Callable[[ReplState, str], str] | None:
    """Claude ayar adının işleyicisi; ad büyük/küçük harf duyarlıdır (Claude ile aynı)."""
    return CLAUDE_KEYS.get(key)
