"""Asenkron çalışan, çıktısını kendi basan slash komutları (`/rc`, `/voice`).

İki REPL yüzeyi (`loop.py`, `tui_loop.py`) `commands.ASYNC_COMMANDS` içindeki komutu
buradan çalıştırır; kayıt defterindeki eşzamanlı işleyici yalnız masaüstü/uzak yoldur.
"""

from __future__ import annotations

from collections.abc import Callable

from rich.console import Console

from . import remote_control, voice_command
from .state import ReplState


async def run(
    name: str,
    state: ReplState,
    argument: str,
    console: Console,
    *,
    on_partial: Callable[[str], None] = lambda _text: None,
) -> None:
    if name == "voice":
        await voice_command.run(state, argument, console, on_partial=on_partial)
        return
    await remote_control.run(state, argument, console)
