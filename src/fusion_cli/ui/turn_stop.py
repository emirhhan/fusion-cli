"""Bütçeyle yarıda kalan turun kullanıcıya gösterilen özeti.

Motor kullanıcı metni üretmez (RULES.md "UI ve CLI"); sebep kodu ve görev listesi
buradan metne çevrilir.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.tools import TodoItem, TodoStatus
from . import messages


def turn_stopped_summary(reason: str | None, todos: Sequence[TodoItem]) -> str:
    """Yarım kalan turun sebebini, görev ilerlemesini ve nasıl sürdürüleceğini yaz."""
    sebep = messages.APP_TURN_STOP_REASONS.get(reason or "", reason or "bilinmeyen sebep")
    satirlar = [messages.APP_TURN_STOPPED_HEAD.format(reason=sebep)]
    if todos:
        tamam = sum(1 for item in todos if item.status is TodoStatus.COMPLETED)
        satirlar.append(messages.APP_TURN_STOPPED_TODOS.format(done=tamam, total=len(todos)))
        satirlar.extend(f"{item.status.icon} {item.content}" for item in todos)
    satirlar.append(messages.APP_TURN_STOPPED_HINT)
    return "\n".join(satirlar)
