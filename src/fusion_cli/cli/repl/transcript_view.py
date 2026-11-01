"""Ctrl+O transcript görüntüleyici (#216, Claude Code `app:toggleTranscript`).

Claude Code: Ctrl+O ayrıntılı transcript görünümüne geçer; araç çağrıları argümanlarıyla,
araç sonuçları tam olarak görünür. Görünümde Ctrl+E (`transcript:toggleShowAll`) yalnız
son mesajlar ile bütün konuşma arasında geçer; q, Esc, Ctrl+C ya da yeniden Ctrl+O çıkar.

Bu modül konuşma geçmişini (`ReplState.history`) Rich ile ANSI metne çevirir; tam ekran
TUI bunu konuşma alanının yerine gösterir, satır içi REPL istemin üstüne basar.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence

from rich.console import Console
from rich.text import Text

from ...core.types import Message
from ...ui import theme

#: Varsayılan görünümde gösterilen son mesaj sayısı (Ctrl+E hepsini açar).
RECENT_MESSAGES = 30
#: Varsayılan görünümde araç sonucunun en çok satırı (Ctrl+E sınırı kaldırır).
RESULT_LINES = 60
TITLE = "Transcript · Ctrl+E hepsi/son {count} · q, Esc, Ctrl+O kapat"
TITLE_ALL = "Transcript (bütün konuşma) · Ctrl+E son mesajlar · q, Esc, Ctrl+O kapat"
EMPTY = "(konuşmada henüz mesaj yok)"
CLIPPED = "… {count} satır daha (Ctrl+E hepsini gösterir)"
EARLIER = "… {count} önceki mesaj gizli (Ctrl+E hepsini gösterir)"
_ROLE_LABELS = {"user": "› kullanıcı", "assistant": "● asistan", "tool": "  ⎿ araç sonucu"}


def _arguments(raw: object) -> str:
    if isinstance(raw, str):
        return raw
    try:
        return json.dumps(raw, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(raw)


def _clip(text: str, show_all: bool) -> str:
    lines = text.splitlines()
    if show_all or len(lines) <= RESULT_LINES:
        return text
    rest = len(lines) - RESULT_LINES
    return "\n".join([*lines[:RESULT_LINES], CLIPPED.format(count=rest)])


def _message_text(message: Message, show_all: bool) -> list[Text]:
    parts: list[Text] = []
    label = _ROLE_LABELS.get(message.role, message.role)
    if message.role == "tool":
        status = "" if message.ok is None else (" ✓" if message.ok else " ✗")
        parts.append(Text(f"{label} {message.name or ''}{status}", style=theme.DIM))
        parts.append(Text(_clip(message.content, show_all)))
        return parts
    parts.append(Text(label, style=f"bold {theme.ACCENT}"))
    if message.content.strip():
        parts.append(Text(message.content.rstrip()))
    if message.images:
        parts.append(Text(f"  [{len(message.images)} görüntü]", style=theme.DIM))
    for call in message.tool_calls:
        name = getattr(call, "name", "")
        args = _arguments(getattr(call, "arguments", ""))
        parts.append(Text(f"  ⏺ {name}", style="bold"))
        parts.append(Text(_clip(args, show_all), style=theme.DIM))
    return parts


def render(history: Sequence[Message], *, width: int, show_all: bool = False) -> str:
    """Geçmişin ayrıntılı ANSI görünümü; sistem mesajı ve harness notları atlanır."""
    visible = [m for m in history if m.role != "system" and not m.harness_note]
    sink = io.StringIO()
    console = Console(file=sink, force_terminal=True, color_system="truecolor", width=width)
    console.print(Text(TITLE_ALL if show_all else TITLE.format(count=RECENT_MESSAGES)))
    hidden = 0 if show_all else max(0, len(visible) - RECENT_MESSAGES)
    if hidden:
        console.print(Text(EARLIER.format(count=hidden), style=theme.DIM))
    if not visible:
        console.print(Text(EMPTY, style=theme.DIM))
    for message in visible[hidden:]:
        console.print()
        for part in _message_text(message, show_all):
            console.print(part, soft_wrap=False)
    return sink.getvalue()
