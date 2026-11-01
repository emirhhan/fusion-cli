"""Satır içi REPL'de tur sürerken tuş okuma: Ctrl+B (Claude Code, #12).

Tam ekran TUI tuşları prompt_toolkit ile tur boyunca okur. Satır içi REPL'de
(`FUSION_INLINE=1`, `runtime.tui: inline`) terminal tur boyunca kanonik kipte kalıyordu:
Ctrl+B satır sonuna dek çekirdek tamponunda bekliyor, hiçbir şey yapmıyordu.

Bu modül tur boyunca terminali kanonik olmayan kipe alır (ISIG açık kalır: Ctrl+C yine
turu keser), `arka_plana_al` eylemine bağlı Ctrl baytını yakalar, öteki tuşları kendisi
yansıtıp tampona yazar. Tur bitince yazılan kaybolmaz: Enter'la biten satırlar sıradaki
mesaj olur, yarım satır istemi doldurur (Claude Code'da da tur sürerken yazılan mesaj
sıraya girer). Onay/soru sorulurken (`paused`) terminal eski kipine döner.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import logging
import os
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, TextIO

from ...config import keybindings

if TYPE_CHECKING:
    from .state import ReplState

try:  # Windows'ta yok: orada satır içi Ctrl+B kapalı kalır.
    import termios
except ImportError:  # pragma: no cover - platforma bağlı
    termios = None  # type: ignore[assignment]

_logger = logging.getLogger(__name__)

#: TUI tablosundaki eylem adı; satır içi yüzey aynı bağı kullanır.
BACKGROUND_ACTION = "arka_plana_al"
#: Bağlanamayan Ctrl harfleri: terminal ya da satır düzeni kullanır (c=SIGINT, d=EOF,
#: h=geri sil, i=Tab, j/m=Enter, q/s=akış denetimi, z=SIGTSTP).
_RESERVED_CTRL = frozenset("cdhijmqsz")
_BACKSPACE = frozenset({0x7F, 0x08})
_NEWLINE = frozenset({0x0A, 0x0D})
_ESC = 0x1B
_CSI_FINAL = range(0x40, 0x7F)


def trigger_bytes(bindings: Mapping[str, str]) -> frozenset[int]:
    """`arka_plana_al` eylemine bağlı `c-<harf>` tuşlarının baytları."""
    found: set[int] = set()
    for key, action in bindings.items():
        letter = key[2:].lower() if key.lower().startswith("c-") else ""
        if action != BACKGROUND_ACTION or len(letter) != 1 or not letter.isalpha():
            continue
        if letter in _RESERVED_CTRL:
            continue
        found.add(ord(letter) - ord("a") + 1)
    return frozenset(found)


@dataclass(slots=True)
class Typeahead:
    """Tur sürerken yazılanlar: tamamlanan satırlar + yarım satır."""

    lines: list[str] = field(default_factory=list)
    _partial: list[str] = field(default_factory=list)
    _decoder: Any = field(default_factory=lambda: codecs.getincrementaldecoder("utf-8")("replace"))
    #: 0: düz, 1: ESC sonrası, 2: CSI/SS3 dizisi içinde (ok tuşları yazıya girmez).
    _escape: int = 0

    def feed(self, data: bytes, triggers: frozenset[int]) -> tuple[bool, str]:
        """Baytları işle; (tetik tuşu geldi mi, ekrana yansıtılacak metin)."""
        triggered = False
        echo: list[str] = []
        for byte in data:
            if self._skip_escape(byte):
                continue
            if byte in triggers:
                triggered = True
            elif byte in _NEWLINE:
                self.lines.append("".join(self._partial))
                self._partial.clear()
                echo.append("\r\n")
            elif byte in _BACKSPACE:
                if self._partial:
                    self._partial.pop()
                    echo.append("\b \b")
            elif byte >= 0x20:
                text = self._decoder.decode(bytes([byte]))
                if text:
                    self._partial.append(text)
                    echo.append(text)
        return triggered, "".join(echo)

    def _skip_escape(self, byte: int) -> bool:
        if self._escape == 1:
            self._escape = 2 if byte in (ord("["), ord("O")) else 0
            return True
        if self._escape == 2:
            if byte in _CSI_FINAL:
                self._escape = 0
            return True
        if byte == _ESC:
            self._escape = 1
            return True
        return False

    def take_line(self) -> str | None:
        return self.lines.pop(0) if self.lines else None

    def take_partial(self) -> str:
        text, self._partial = "".join(self._partial), []
        return text


class InlineKeys:
    """Oturum boyunca yaşayan satır içi tuş gözcüsü; tur başına `watching` ile açılır."""

    def __init__(
        self,
        triggers: frozenset[int],
        fd: int | None,
        *,
        out: TextIO | None = None,
    ) -> None:
        self.typeahead = Typeahead()
        self._triggers = triggers
        self._fd = fd
        self._out = out
        self._saved: list[Any] | None = None
        self._on_trigger: Callable[[], None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        #: Açık `paused` sayısı: paralel alt ajanların onayları iç içe duraklatır.
        self._pause_depth = 0

    @property
    def active(self) -> bool:
        return self._saved is not None

    def usable(self) -> bool:
        if termios is None or self._fd is None or not self._triggers:
            return False
        try:
            return os.isatty(self._fd)
        except OSError:
            return False

    @contextlib.contextmanager
    def watching(self, on_trigger: Callable[[], None]) -> Iterator[None]:
        """Tur boyunca tetik tuşunu dinle; iç içe turda ikinci kez açılmaz."""
        if self.active or not self.usable():
            yield
            return
        self._on_trigger = on_trigger
        self._loop = asyncio.get_running_loop()
        started = self._enter()
        try:
            yield
        finally:
            if started:
                self._leave()
            self._on_trigger = None

    @contextlib.contextmanager
    def paused(self) -> Iterator[None]:
        """Onay/soru boyunca terminali eski (kanonik, yankılı) kipine döndür.

        İç içe/paralel çağrılarda yalnız ilk giriş kipi bırakır, son çıkış geri açar;
        tur o arada bittiyse (`watching` kapandıysa) gözcü yeniden açılmaz.
        """
        if self._pause_depth == 0 and not self.active:
            yield
            return
        self._pause_depth += 1
        if self._pause_depth == 1:
            self._leave()
        try:
            yield
        finally:
            self._pause_depth -= 1
            if self._pause_depth == 0 and self._on_trigger is not None:
                self._enter()

    def _enter(self) -> bool:
        assert termios is not None and self._fd is not None and self._loop is not None
        try:
            saved = termios.tcgetattr(self._fd)
        except (termios.error, OSError):
            _logger.debug("satır içi tuş gözcüsü açılamadı", exc_info=True)
            return False
        raw = list(saved)
        raw[3] = saved[3] & ~(termios.ICANON | termios.ECHO)
        raw[6] = list(saved[6])
        raw[6][termios.VMIN] = 1
        raw[6][termios.VTIME] = 0
        try:
            termios.tcsetattr(self._fd, termios.TCSANOW, raw)
            self._loop.add_reader(self._fd, self._readable)
        except (termios.error, OSError, ValueError, NotImplementedError):
            _logger.debug("satır içi tuş gözcüsü açılamadı", exc_info=True)
            # Kip değiştiyse geri yükle: yoksa terminal yankısız, bayt bayt kalır.
            with contextlib.suppress(termios.error, OSError):
                termios.tcsetattr(self._fd, termios.TCSANOW, saved)
            return False
        self._saved = saved
        return True

    def _leave(self) -> None:
        assert termios is not None and self._fd is not None
        saved, self._saved = self._saved, None
        if self._loop is not None:
            with contextlib.suppress(OSError, ValueError, NotImplementedError):
                self._loop.remove_reader(self._fd)
        if saved is not None:
            with contextlib.suppress(termios.error, OSError):
                termios.tcsetattr(self._fd, termios.TCSANOW, saved)

    def _readable(self) -> None:
        assert self._fd is not None
        try:
            data = os.read(self._fd, 1024)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:  # EOF / kopan terminal: dinlemeyi bırak, kipi geri yükle.
            self._leave()
            return
        triggered, echo = self.typeahead.feed(data, self._triggers)
        if echo:
            out = self._out or sys.stdout
            out.write(echo)
            out.flush()
        if triggered and self._on_trigger is not None:
            self._on_trigger()


class BackgroundKey(Enum):
    """Ctrl+B'nin bu anda ne yaptığı (TUI ile aynı kural)."""

    NONE = "none"
    SUBAGENT = "subagent"
    TURN = "turn"


def background_key_action(state: ReplState) -> BackgroundKey:
    """Arka plan kapalıysa hiçbir şey; bekleyen ön plan alt ajanı varsa onu taşı; yoksa tur."""
    if state.config.agent_launch.disable_background_tasks:
        return BackgroundKey.NONE
    if state.child_runs.request_background():
        return BackgroundKey.SUBAGENT
    from ...core import foreground_handoff

    if foreground_handoff.request_background():
        # Süren kabuk komutu kesilmeden `.fusion/is` işine devredilir, tur sürer (#320).
        return BackgroundKey.SUBAGENT
    return BackgroundKey.TURN


def session_keys(state: ReplState) -> InlineKeys:
    """Oturumun tuş gözcüsü (ilk turda kurulur, `state.inline_keys`'te saklanır)."""
    existing = getattr(state, "inline_keys", None)
    if isinstance(existing, InlineKeys):
        return existing
    try:
        fd: int | None = sys.stdin.fileno()
    except (AttributeError, OSError, ValueError):
        fd = None
    keymap = keybindings.load_keymap()
    created = InlineKeys(trigger_bytes(keymap.bindings(keybindings.CONTEXT_TUI)), fd)
    state.inline_keys = created
    return created


def take_typed_line(state: ReplState) -> str | None:
    """Tur sürerken Enter'la biten satır varsa sıradaki mesaj olarak al."""
    keys = getattr(state, "inline_keys", None)
    return keys.typeahead.take_line() if isinstance(keys, InlineKeys) else None


def take_typed_partial(state: ReplState) -> str:
    keys = getattr(state, "inline_keys", None)
    return keys.typeahead.take_partial() if isinstance(keys, InlineKeys) else ""


@contextlib.contextmanager
def prompt_pause(
    suspend: Callable[[], contextlib.AbstractContextManager[None]], state: ReplState
) -> Iterator[None]:
    """Prompter'ın `suspend` kancası: canlı göstergeyle birlikte tuş gözcüsünü de durdur."""
    keys = getattr(state, "inline_keys", None)
    pause = keys.paused() if isinstance(keys, InlineKeys) else contextlib.nullcontext()
    with suspend(), pause:
        yield
