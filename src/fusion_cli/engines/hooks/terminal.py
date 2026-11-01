"""`terminalSequence`: kancanın istediği izinli diziyi terminale basma (#128).

Claude Code: dizi (OSC 0/1/2/9/99/777, BEL; `core/hooks/output.terminal_sequence`
doğrular) YALNIZ etkileşimli oturumda ve arayüz ekrandayken yazılır; `-p` ve SDK'da
yok sayılır. Fusion'da yazıcı yalnız çıktı gerçek bir terminalse kurulur: masaüstü
sunucusunun stdout'u JSON-RPC borusudur, oraya dizi yazılmaz.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TextIO


def tty_writer(stream: TextIO | None = None) -> Callable[[str], None] | None:
    """Akış terminalse diziyi yazan işlev; boru/dosya/CI'da `None`.

    Varsayılan `sys.__stdout__`: prompt_toolkit'in `patch_stdout` vekili kaçış dizilerini
    ayıklar; OSC dizileri imleci oynatmadığı için gerçek akışa doğrudan yazılır.
    """
    target = stream if stream is not None else sys.__stdout__
    if target is None:
        return None
    try:
        if not target.isatty():
            return None
    except (AttributeError, ValueError, OSError):
        return None

    def _write(sequence: str) -> None:
        try:
            target.write(sequence)
            target.flush()
        except (OSError, ValueError):
            # Kapanmış akış kancanın sonucunu bozmaz.
            return

    return _write
