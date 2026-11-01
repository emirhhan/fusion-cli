"""Satır içi REPL'de tur sürerken tuş okuma: Ctrl+B arka plana alır (Claude Code, #320).

Claude Code (interactive-mode › Ctrl+B): çalışan Bash komutu ya da alt ajan kesilmeden arka
plana taşınır; tmux'ta önek tuşu olduğu için iki kez basılır (tmux ikinci basışı uygulamaya
tek Ctrl+B olarak iletir; Fusion'da ek iş gerekmez). Satır içi REPL tur sürerken istem
açmadığı için terminal kanonik kipteydi ve tuş hiç okunmuyordu.

Tur boyunca terminal cbreak kipine alınır (yankı kapalı; Ctrl+C sinyali korunur) ve stdin
olay döngüsünden okunur: Ctrl+B eylemi çağırır, yazılan düz metin sonraki istemin taslağına
eklenir (önden yazma kaybolmaz). Onay/soru istemi terminali devralırken izleme `paused()` ile
durur, kanonik kip geri gelir. TTY olmayan ortamda ve Windows'ta hiçbir şey yapmaz.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import os
import sys
from collections.abc import Callable, Iterator
from typing import Any

__all__ = ["CTRL_B", "TurnKeys", "paused"]

CTRL_B = 0x02
_BACKSPACE = {0x7F, 0x08}
_NEWLINE = {0x0A, 0x0D}
_ACTIVE: list[TurnKeys] = []


class TurnKeys:
    """Tur süresince stdin'i izler; Ctrl+B'yi eyleme, metni taslağa çevirir."""

    def __init__(self, on_ctrl_b: Callable[[], None], fd: int | None = None) -> None:
        self._on_ctrl_b = on_ctrl_b
        self._fd = sys.stdin.fileno() if fd is None else fd
        self._saved: list[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="ignore")
        self.typed = ""

    def feed(self, data: bytes) -> None:
        """Okunan baytları işle (testte doğrudan çağrılır)."""
        for byte in data:
            if byte == CTRL_B:
                self._on_ctrl_b()
            elif byte in _BACKSPACE:
                self.typed = self.typed[:-1]
            elif byte in _NEWLINE or byte < 0x20:
                continue
            else:
                self.typed += self._decoder.decode(bytes([byte]))

    def _readable(self) -> None:
        try:
            data = os.read(self._fd, 256)
        except OSError:
            return
        self.feed(data)

    def _start(self) -> None:
        import termios
        import tty

        self._saved = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd, termios.TCSANOW)
        attrs = termios.tcgetattr(self._fd)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(self._fd, termios.TCSANOW, attrs)
        if self._loop is not None:
            self._loop.add_reader(self._fd, self._readable)

    def _stop(self) -> None:
        import termios

        if self._loop is not None:
            with contextlib.suppress(ValueError, OSError):
                self._loop.remove_reader(self._fd)
        if self._saved is not None:
            with contextlib.suppress(OSError, termios.error):
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
            self._saved = None

    @contextlib.contextmanager
    def watching(self) -> Iterator[TurnKeys]:
        """Tur boyunca izle; TTY değilse ya da kurulamazsa sessizce geç."""
        if sys.platform == "win32" or not os.isatty(self._fd):
            yield self
            return
        try:
            self._loop = asyncio.get_running_loop()
            self._start()
        except (OSError, RuntimeError, ValueError, ImportError):
            self._stop()
            yield self
            return
        _ACTIVE.append(self)
        try:
            yield self
        finally:
            _ACTIVE.remove(self)
            self._stop()

    @contextlib.contextmanager
    def _paused(self) -> Iterator[None]:
        was_active = self._saved is not None
        if was_active:
            self._stop()
        try:
            yield
        finally:
            if was_active:
                with contextlib.suppress(OSError, ValueError, ImportError):
                    self._start()


@contextlib.contextmanager
def paused() -> Iterator[None]:
    """Onay/soru istemi terminali devralırken izlemeyi durdur (yoksa hiçbir şey yapmaz)."""
    if not _ACTIVE:
        yield
        return
    with _ACTIVE[-1]._paused():
        yield
