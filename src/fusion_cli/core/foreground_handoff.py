"""Süren ön plan kabuk komutlarını kesmeden arka plana alma isteği (Claude Code Ctrl+B, #320).

Claude Code (interactive-mode, "Ctrl+B"): çalışan Bash komutu kesilmeden arka plana taşınır,
tur sürer. Ön plan komutu çalışırken burada bir olay kaydeder; Ctrl+B `request_background()`
ile olayları kurar, `run_foreground` yoklama döngüsü bunu görüp sahipliği devreder.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_LOCK = threading.Lock()
_ACTIVE: set[threading.Event] = set()


@contextmanager
def handoff_slot() -> Iterator[threading.Event]:
    """Komut sürdükçe kayıtlı kalan devir olayı."""
    event = threading.Event()
    with _LOCK:
        _ACTIVE.add(event)
    try:
        yield event
    finally:
        with _LOCK:
            _ACTIVE.discard(event)


def request_background() -> bool:
    """Süren devredilebilir komut varsa hepsini arka plana iste; varsa True."""
    with _LOCK:
        active = list(_ACTIVE)
    for event in active:
        event.set()
    return bool(active)
