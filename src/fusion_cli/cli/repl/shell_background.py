"""Ctrl+B ile süren `!` komutunu kesmeden arka plana al (#218, Claude Code).

Claude Code: "Background Bash commands" — Ctrl+B çalışan kabuk komutunu durdurmadan arka
plana taşır, istem hemen serbest kalır; `!` kabuk kipinde de geçerlidir. Fusion'da `!`
komutu bir iş parçacığında koşar (`prefixes.run_shell_prefix`); arka plana alma beklemeyi
bırakmaktır: komut sürer, bitince çıktısı ekrana basılır ve bağlama girer.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import TypeVar

_LOG = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(slots=True)
class ShellDetach:
    """Süren `!` komutu için arka plana alma isteği (Ctrl+B bunu tetikler)."""

    event: asyncio.Event = field(default_factory=asyncio.Event)

    def request(self) -> None:
        self.event.set()


async def run_detachable(
    job: Awaitable[T], detach: ShellDetach, on_done: Callable[[T], None]
) -> T | None:
    """İşi bekle; arka plana alma istenirse beklemeyi bırak ve `None` döndür.

    Arka plana alınan iş kesilmez; bitince `on_done(sonuç)` çağrılır. Tur iptal edilirse
    (Esc) iş de iptal edilir — eski davranış.
    """
    task = asyncio.ensure_future(job)
    waiter = asyncio.ensure_future(detach.event.wait())
    try:
        await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        task.cancel()
        raise
    finally:
        waiter.cancel()
    if task.done():
        return task.result()
    task.add_done_callback(lambda finished: _finish(finished, on_done))
    return None


def _finish(task: asyncio.Future[T], on_done: Callable[[T], None]) -> None:
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        _LOG.warning("arka plandaki ! komutu hata verdi: %s", error)
        return
    try:
        on_done(task.result())
    except Exception:  # bildirim geri çağrısı arka plan işini düşürmesin
        _LOG.exception("arka plandaki ! komutunun sonucu gösterilemedi")


#: Ctrl+B'nin terminal baytı.
_CTRL_B = b"\x02"


@contextlib.contextmanager
def watch_ctrl_b(detach: ShellDetach, *, enabled: bool = True) -> Iterator[None]:
    """Satır içi REPL: süren `!` sırasında stdin'i ham kipte izle, Ctrl+B arka plana alır.

    Yalnız gerçek terminalde (TTY, POSIX) etkindir; tam ekran TUI'de prompt_toolkit tuşu
    kendisi okur (`enabled=False`). Çıkışta terminal kipi geri yüklenir.
    """
    if not enabled or not _stdin_is_tty():
        yield
        return
    import termios
    import tty

    fd = sys.stdin.fileno()
    try:
        saved = termios.tcgetattr(fd)
        loop = asyncio.get_running_loop()
    except (termios.error, OSError, RuntimeError):
        yield
        return
    tty.setcbreak(fd)
    loop.add_reader(fd, lambda: _on_key(fd, detach))
    try:
        yield
    finally:
        loop.remove_reader(fd)
        with contextlib.suppress(termios.error, OSError):
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def _stdin_is_tty() -> bool:
    try:
        return os.name == "posix" and sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def _on_key(fd: int, detach: ShellDetach) -> None:
    try:
        data = os.read(fd, 64)
    except OSError:
        return
    if _CTRL_B in data:
        detach.request()
