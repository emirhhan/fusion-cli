"""Açılış banner'ı ve durum çubuğu.

Renk ve simge değerleri `theme` modülünden gelir; buraya hex gömülmez.
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from . import messages, theme

_BANNER_LINES = (
    "███████╗██╗   ██╗███████╗██╗ ██████╗ ███╗   ██╗",
    "██╔════╝██║   ██║██╔════╝██║██╔═══██╗████╗  ██║",
    "█████╗  ██║   ██║███████╗██║██║   ██║██╔██╗ ██║",
    "██╔══╝  ██║   ██║╚════██║██║██║   ██║██║╚██╗██║",
    "██║     ╚██████╔╝███████║██║╚██████╔╝██║ ╚████║",
    "╚═╝      ╚═════╝ ╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝",
)


def gradient(text: str, start: str = theme.ACCENT, end: str = theme.ACCENT_ALT) -> Text:
    """Metni karakter karakter iki renk arasında geçişli boya."""
    rendered = Text()
    visible = [char for char in text if char != "\n"]
    total = len(visible)
    index = 0
    for char in text:
        if char == "\n":
            rendered.append("\n")
            continue
        ratio = 0.0 if total <= 1 else index / (total - 1)
        rendered.append(char, style=_blend(start, end, ratio))
        index += 1
    return rendered


def print_banner(console: Console) -> None:
    console.print()
    for line in _BANNER_LINES:
        console.print(gradient(line))
    console.print(f"[{theme.DIM}]{messages.REPL_TAGLINE}[/{theme.DIM}]")
    console.print()


def print_status(
    console: Console, *, engine: str, approval: str, task_type: str, model: str
) -> None:
    """Aktif oturum ayarlarını tek satırda göster."""
    separator = f"[{theme.ACCENT}]│[/{theme.ACCENT}]"
    parts = (
        _field("motor", engine, theme.ACCENT),
        _field("onay", approval, _mode_color(approval)),
        _field("görev", task_type, theme.ACCENT_ALT),
        _field("model", model, theme.INFO),
    )
    console.print(f" {separator} ".join(parts))


def _field(label: str, value: str, color: str) -> str:
    return f"[{theme.DIM}]{label}:[/{theme.DIM}] [{color}]{value}[/{color}]"


def _mode_color(mode: str) -> str:
    return {"auto": theme.OK, "plan": theme.WARN, "security": theme.ERROR}.get(mode, theme.DIM)


def _blend(start: str, end: str, ratio: float) -> str:
    """İki #RRGGBB rengi arasında doğrusal geçiş."""
    left, right = start.lstrip("#"), end.lstrip("#")
    channels = (
        round(
            int(left[i : i + 2], 16)
            + (int(right[i : i + 2], 16) - int(left[i : i + 2], 16)) * ratio
        )
        for i in (0, 2, 4)
    )
    return "#" + "".join(f"{value:02X}" for value in channels)
