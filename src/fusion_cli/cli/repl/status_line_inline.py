"""Satır içi REPL'de durum satırı tetikleri (#192, Claude Code statusline).

Claude Code betiği oturum başında, her asistan mesajında, `/compact` sonrasında, izin kipi ya
da vim kipi değişince ve `refreshInterval` saniyede bir çalıştırır; tetikler 300 ms birleşir.
Tam ekran TUI bunu `StatusLineRunner` ile yapar. Satır içi REPL oturum başı ve tur sonunu
`loop._show_status_line` ile karşılar; bu gözcü istem açıkken kip değişimini ve
`refreshInterval`'ı yakalar ve bloğu istemin üstüne (ya da `FUSION_TOOLBAR=1` alt çubuğuna) basar.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from .state import ReplState

_LOG = logging.getLogger(__name__)

#: Yoklama aralığı; Claude Code'un 300 ms birleştirmesiyle aynı.
POLL_S = 0.3


class _Reader(Protocol):
    mode: object
    vim_mode: bool
    custom_status: str

    @property
    def waiting(self) -> bool: ...

    def vi_state(self) -> str: ...

    def invalidate(self) -> None: ...

    async def print_above(self, write: Callable[[], None]) -> None: ...


def trigger_key(reader: _Reader) -> tuple[str, bool, str]:
    """Değişince betiği çalıştıran durum: izin kipi, vim açık mı, vim alt kipi."""
    return (str(getattr(reader.mode, "value", reader.mode)), reader.vim_mode, reader.vi_state())


class InlineStatusWatcher:
    """Kip değişimi ve `refreshInterval` tetikleri; `show` bloğu yazar."""

    def __init__(
        self,
        state: ReplState,
        reader: _Reader,
        show: Callable[[], Awaitable[None]],
        interval: Callable[[], int | None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._state, self._reader, self._show = state, reader, show
        self._interval, self._clock = interval, clock
        self._last_key = trigger_key(reader)
        self._last_run = clock()

    def mark_ran(self) -> None:
        """Tur sonu/oturum başı çalıştırması zamanlayıcıyı ve kip anahtarını sıfırlar."""
        self._last_key = trigger_key(self._reader)
        self._last_run = self._clock()

    def due(self) -> bool:
        if not self._reader.waiting:
            return False
        key = trigger_key(self._reader)
        refresh = self._interval()
        elapsed = self._clock() - self._last_run
        return key != self._last_key or bool(refresh and elapsed >= refresh)

    async def tick(self) -> bool:
        """Tetik varsa betiği çalıştırıp göster; çalıştıysa True."""
        if not self.due():
            return False
        self._state.approval = self._reader.mode  # type: ignore[assignment]
        self._state.vim_state = self._reader.vi_state()
        self.mark_ran()
        await self._show()
        return True

    async def run(self) -> None:
        while self._state.running:
            await asyncio.sleep(POLL_S)
            try:
                await self.tick()
            except Exception:  # gözcü REPL'i düşürmemeli; neden günlükte
                _LOG.warning("durum satırı yenilenemedi", exc_info=True)
