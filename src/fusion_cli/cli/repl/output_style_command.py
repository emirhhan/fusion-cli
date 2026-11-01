"""`/output-style [ad]` (P-068): çıktı stilini listele / seç; seçim kalıcıdır.

Claude Code ile aynı (#215): seçim projenin `.claude/settings.local.json` dosyasına
`outputStyle` alanı olarak (stilin özgün adıyla, ör. `Explanatory`) yazılır.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

from ...config import trust
from ...core.errors import ConfigError
from ...engines.agent.output_style import (
    DEFAULT_STYLE,
    SETTING_KEY,
    canonical_style_name,
    discover_styles,
    find_style,
    selected_style,
)
from ...tools.files import atomic_write
from ...ui import messages
from ...ui.picker import Choice
from .state import ReplState

_LOG = logging.getLogger(__name__)

#: Eski Fusion ayar yolu (yalnız Claude katmanlarında `outputStyle` yokken okunur).
SETTING_PATH = "runtime.output_style"


def _current(state: ReplState) -> str:
    style = selected_style(state.config, home=state.home, root=state.root)
    return DEFAULT_STYLE if style is None else style.name


def write_local_setting(root: Path, value: str) -> Path:
    """`outputStyle`'ı `.claude/settings.local.json`'a yaz; öteki alanlar korunur."""
    target = root / trust.PROJECT_PERMISSIONS_PATH
    data: dict[str, object] = {}
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ConfigError(f"{target} okunamadı: {error}") from error
        if not isinstance(loaded, dict):
            raise ConfigError(f"{target}: kök bir nesne olmalı")
        data = loaded
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write(target, json.dumps({**data, SETTING_KEY: value}, indent=2) + "\n")
    except OSError as error:
        raise ConfigError(f"{target} yazılamadı: {error}") from error
    try:
        trust.record_permissions_digest(root)
    except Exception as error:  # güven karması tazelenemezse yazılan değer yine geçerli
        _LOG.warning("yerel ayar güven karması tazelenemedi (%s): %s", target, error)
    return target


def style_choices(state: ReplState) -> list[Choice]:
    """Uygulama-içi seçici (TUI) ve masaüstü seçici için stil listesi."""
    current = _current(state)
    return [
        Choice(
            style.name,
            style.name + (messages.OUTPUT_STYLE_CURRENT if style.name == current else ""),
            f"{style.description} [{style.source}]".strip(),
        )
        for style in discover_styles(state.home, state.root)
    ]


def format_styles(state: ReplState) -> str:
    rows = [messages.OUTPUT_STYLE_HEADER.format(current=_current(state))]
    for choice in style_choices(state):
        rows.append(f"  {choice.label:<16} {choice.description}")
    rows.append(messages.OUTPUT_STYLE_HINT)
    return "\n".join(rows)


def output_style_command(state: ReplState, argument: str) -> str:
    # Claude Code: `/output-style` büyük/küçük harf duyarsız; eski Türkçe adlar takma addır.
    wanted = canonical_style_name(argument)
    if not wanted:
        return format_styles(state)
    style = find_style(wanted, state.home, state.root)
    if wanted != DEFAULT_STYLE and style is None:
        known = ", ".join(style.name for style in discover_styles(state.home, state.root))
        return messages.OUTPUT_STYLE_UNKNOWN.format(name=wanted, known=known)
    display = style.display if style is not None and style.display else wanted
    # Oturumda hemen geçerli (eski ayar alanı da güncel tutulur; katman yazılamazsa yedek).
    state.config = replace(state.config, runtime=replace(state.config.runtime, output_style=wanted))
    try:
        write_local_setting(state.root, display)
    except ConfigError as error:
        return messages.OUTPUT_STYLE_SET_UNSAVED.format(name=display, error=error)
    return messages.OUTPUT_STYLE_SET.format(name=display)
