"""Satır içi REPL: ajan turu sürerken yazılanı okuyup aynı tura ver (#190, #218).

Claude Code (interactive-mode, "Queue messages while Claude works"): Claude çalışırken
yazılan mesaj kuyruğa girer, araç çağrıları bitince AYNI tura verilir; tur bittiğinde
kuyrukta kalanlar tuşa basmadan gider. Komut ve `!` satırları tur sonunu bekler. Ctrl+B
süren kabuk komutunu ya da beklenen alt ajanı kesmeden arka plana alır.

Tam ekran TUI bunu prompt_toolkit ile yapar; satır içi REPL'de tur sırasında istem yoktur.
Bu modül tur boyunca stdin'i ham (cbreak) kipte okur: yazılan taslak canlı göstergenin
altında görünür, Enter satırı kuyruğa verir. Onay/soru istemi açılırken `paused()` okumayı
bırakır ve terminali geri verir. Ctrl+C sinyal olarak kalır (ISIG açık).
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Callable, Iterator
from typing import Any

from ...core.steering import SteeringQueue
from .queue_steer import SteerBridge

_CTRL_B = "\x02"
_ERASE = {"\x7f", "\x08"}
_SUBMIT = {"\r", "\n"}
_CTRL_U = "\x15"


def stdin_is_tty() -> bool:
    try:
        return os.name == "posix" and sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        return False


class InlineTurnKeys:
    """Tur boyunca yazılanları toplayan, Enter'da kuyruğa veren okuyucu."""

    def __init__(
        self,
        *,
        on_draft: Callable[[str], None],
        on_queued: Callable[[str], None],
        on_background: Callable[[], None],
        on_immediate: Callable[[str], bool] | None = None,
    ) -> None:
        self._bridge = SteerBridge()
        self._on_immediate = on_immediate
        self._on_draft = on_draft
        self._on_queued = on_queued
        self._on_background = on_background
        self._draft = ""
        self._waiting: list[str] = []
        self._fd: int | None = None
        self._saved: Any = None
        self._escape = False

    def begin(self) -> SteeringQueue:
        """Turun yönlendirme kuyruğu (motora `AgentDeps.steering` olarak verilir)."""
        return self._bridge.begin()

    # -- tuş işleme (saf; testler doğrudan çağırır) -------------------------------- #
    def feed(self, text: str) -> None:
        for char in text:
            self._feed_char(char)
        self._on_draft(self._draft)

    def _feed_char(self, char: str) -> None:
        if self._escape:
            # ESC dizisi (ok tuşları vb.): son harf ya da `~` ile biter, yok sayılır.
            self._escape = not (char.isalpha() or char == "~")
            return
        if char == "\x1b":
            self._escape = True
        elif char == _CTRL_B:
            self._on_background()
        elif char in _SUBMIT:
            self._submit()
        elif char in _ERASE:
            self._draft = self._draft[:-1]
        elif char == _CTRL_U:
            self._draft = ""
        elif char.isprintable():
            self._draft += char

    def _submit(self) -> None:
        line, self._draft = self._draft.strip(), ""
        if not line:
            return
        if self._on_immediate is not None and self._on_immediate(line):
            return  # anlık komut (#209): kuyruğa girmeden çalıştı
        if not self._bridge.offer(line):
            self._waiting.append(line)  # komut / `!` / `@`: tur sonunu bekler
        self._on_queued(line)

    def end(self) -> tuple[list[str], str]:
        """Tur bitti: (sıradaki turlara gidecek satırlar, yarım taslak)."""
        _consumed, leftover = self._bridge.end()
        lines = [*leftover, *self._waiting]
        self._waiting = []
        draft, self._draft = self._draft, ""
        return lines, draft

    # -- terminal ------------------------------------------------------------------ #
    @contextlib.contextmanager
    def reading(self) -> Iterator[None]:
        """Tur boyunca stdin'i ham kipte oku; TTY değilse hiçbir şey yapmaz."""
        if not stdin_is_tty():
            yield
            return
        self._attach()
        try:
            yield
        finally:
            self._detach()

    @contextlib.contextmanager
    def paused(self) -> Iterator[None]:
        """Onay/soru istemi: okumayı bırak, terminali normal kipe döndür."""
        was_reading = self._fd is not None
        if was_reading:
            self._detach()
        try:
            yield
        finally:
            if was_reading:
                self._attach()

    def _attach(self) -> None:
        import asyncio
        import termios
        import tty

        fd = sys.stdin.fileno()
        try:
            self._saved = termios.tcgetattr(fd)
            loop = asyncio.get_running_loop()
        except (termios.error, OSError, RuntimeError):
            return
        tty.setcbreak(fd)
        loop.add_reader(fd, self._on_readable)
        self._fd = fd

    def _detach(self) -> None:
        import asyncio
        import termios

        fd, self._fd = self._fd, None
        if fd is None:
            return
        with contextlib.suppress(RuntimeError, ValueError):
            asyncio.get_running_loop().remove_reader(fd)
        with contextlib.suppress(termios.error, OSError):
            termios.tcsetattr(fd, termios.TCSADRAIN, self._saved)

    def _on_readable(self) -> None:
        if self._fd is None:
            return
        try:
            data = os.read(self._fd, 1024)
        except OSError:
            return
        self.feed(data.decode("utf-8", errors="ignore"))
