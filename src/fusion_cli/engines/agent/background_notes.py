"""Arka plan olaylarını (biten iş, `monitor` satırı) model isteğine ekle (#334, #336).

Claude Code arka plan işinin bitişini ve Monitor satırlarını yoklama yaptırmadan bildirir;
olay sıradaki model isteğine girer. Kuyruk yoksa (tek atışlık bağlam) akış değişmez.
"""

from __future__ import annotations

from ...core.background_events import BackgroundEvents
from ...core.tools import ToolContext
from ...core.types import Message

__all__ = ["append_background_events", "background_events_of"]


def background_events_of(context: ToolContext | None) -> BackgroundEvents | None:
    """Bağlamın olay kuyruğu; eski bağlamlarda alan yoksa `None`."""
    return getattr(context, "background_events", None)


def append_background_events(messages: list[Message], context: ToolContext | None) -> bool:
    """Bekleyen olayları tek harness notu olarak ekle; eklendiyse True."""
    events = background_events_of(context)
    if events is None:
        return False
    note = events.drain_note()
    if note is None:
        return False
    messages.append(note)
    return True
