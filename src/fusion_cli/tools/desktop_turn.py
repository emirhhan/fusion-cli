"""Turun masaüstü oturumu: Esc ile durdurma, diğer uygulamaları gizle / geri göster (P-033).

Claude CLI computer use bir tur boyunca: tek oturum kilidi tutar, diğer uygulamaları gizler
(terminal görünür kalır), "press Esc to stop" der ve Esc'i küresel iptal sayar; bitince
gizlenen uygulamaları geri gösterir (Desktop'ta "Unhide apps when Claude finishes").

Fusion'da tur sahibi (`cli/session.run_agent_task`, REPL) turun başında `begin` ile oturumu
`ToolContext.desktop.turn`'e bağlar, sonunda `finish` ile kapatır (kilit de bırakılır).
Fare/klavye araçları ilk eylemde `foreground_action` çağırır; o an (bir kez):

- `desktop.escape_stops` açıksa Esc dinleyicisi başlar; Esc → tur görevine `cancel`
  (Ctrl+C / masaüstü "Durdur" ile aynı yol).
- `desktop.background` kapalıysa öndeki uygulama ve Fusion (bu süreç + ataları: Fusion.app ya
  da terminal) dışındaki normal uygulamalar gizlenir; `unhide_on_finish` açıksa `finish`
  onları geri gösterir.

Gizleme/gösterme ve dinleyici yan etkileri enjekte edilebilir (`DesktopTurnIo`): testler
gerçek uygulamaları gizlemez, olay musluğu kurmaz.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import weakref
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ..core.desktop_settings import DesktopSettings
from ..core.tools import ToolContext
from . import desktop_lock

_logger = logging.getLogger(__name__)
#: Esc dinleyicisi gerçekten kurulmuş turlar (gösterge "durdurmak için Esc"i buna bağlar).
#: Masaüstü kilidi süreç genelinde tek olduğu için aynı anda en çok bir tur ön plandadır.
_LISTENING: weakref.WeakSet[DesktopTurn] = weakref.WeakSet()


def escape_listening() -> bool:
    """Ön plandaki bir turda Esc dinleyicisi kurulu mu? (kurulamadıysa gösterge Esc demez)."""
    return any(turn.escape_active for turn in list(_LISTENING))


def _default_hide(keep: Sequence[int]) -> tuple[int, ...]:
    from .native_desktop import invoke_sync

    result = invoke_sync("hide", {"kind": "apps", "request": {"keep": list(keep)}})
    hidden = result.get("hidden") if result.get("ok") else None
    return tuple(pid for pid in hidden if type(pid) is int) if isinstance(hidden, list) else ()


def _default_unhide(pids: Sequence[int]) -> None:
    from .native_desktop import invoke_sync

    invoke_sync("unhide", {"kind": "apps", "request": {"pids": list(pids)}})


def _default_escape(on_escape: Callable[[], None]) -> Callable[[], None] | None:
    """Esc dinleyicisini başlat; durdurma işlevini döndür (kurulamadıysa None)."""
    from .desktop_escape import EscapeWatch
    from .native_desktop import executable_sync

    watch = EscapeWatch(on_escape, executable=executable_sync)
    return watch.stop if watch.start() else None


def _default_keep() -> tuple[int, ...]:
    from .desktop_screen import fusion_pids

    return tuple(fusion_pids())


@dataclass(frozen=True, slots=True)
class DesktopTurnIo:
    """Oturumun dış dünyaya dokunan işlemleri (sahte verilebilir)."""

    hide: Callable[[Sequence[int]], tuple[int, ...]] = _default_hide
    unhide: Callable[[Sequence[int]], None] = _default_unhide
    start_escape: Callable[[Callable[[], None]], Callable[[], None] | None] = _default_escape
    keep_pids: Callable[[], tuple[int, ...]] = _default_keep


@dataclass(eq=False)  # kimlikle karşılaştırılır: `_LISTENING` kümesinde tutulur
class DesktopTurn:
    """Bir turun masaüstü oturumu; araç iş parçacıklarından çağrılabilir (kilitli)."""

    settings: DesktopSettings
    cancel: Callable[[], None]
    io: DesktopTurnIo = field(default_factory=DesktopTurnIo)
    #: Esc ile durdurulduysa True (tur sonu mesajı ve test için).
    stopped_by_escape: bool = False
    _started: bool = False
    _hidden: tuple[int, ...] = ()
    _stop_escape: Callable[[], None] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def foreground_action(self, keep: Sequence[int] = ()) -> None:
        """İlk fare/klavye eyleminde Esc dinleyicisini kur ve (istenirse) diğerlerini gizle.

        `keep`: eylemin politika hedefi (onaylanan uygulama). Ölçüldü (31 Ekim): yalnız öndeki
        uygulama ve Fusion korunuyordu; arkadaki hedef gizlenince tık altındaki başka
        (değerlendirilmemiş) uygulamaya gidiyordu.
        """
        with self._lock:
            if self._started:
                return
            self._started = True
            if self.settings.escape_stops:
                self._stop_escape = self.io.start_escape(self._escape)
                if self._stop_escape is not None:
                    _LISTENING.add(self)
            if not self.settings.background:
                extra = tuple(pid for pid in keep if pid > 0)
                self._hidden = self.io.hide((*self.io.keep_pids(), *extra))

    def _escape(self) -> None:
        self.stopped_by_escape = True
        self.cancel()

    def close(self) -> None:
        """Dinleyiciyi durdur, gizlenenleri (ayar açıksa) geri göster. İki kez çağrılabilir."""
        with self._lock:
            stop, self._stop_escape = self._stop_escape, None
            hidden, self._hidden = self._hidden, ()
        _LISTENING.discard(self)
        if stop is not None:
            stop()
        if hidden and self.settings.unhide_on_finish:
            self.io.unhide(hidden)

    @property
    def escape_active(self) -> bool:
        return self._stop_escape is not None


def begin(context: ToolContext, io: DesktopTurnIo | None = None) -> DesktopTurn | None:
    """Tur görevinin içinden çağrılır: Esc iptali o göreve (`current_task`) bağlanır."""
    if not context.desktop_settings.enabled:
        return None
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    if task is None:
        return None

    def cancel() -> None:
        loop.call_soon_threadsafe(task.cancel)

    turn = DesktopTurn(context.desktop_settings, cancel, io or DesktopTurnIo())
    context.desktop.turn = turn
    return turn


def finish(context: ToolContext) -> bool:
    """Tur sonu (iptal/hata dahil): oturumu kapat, kilidi bırak; Esc ile durduysa True.

    Ölçüldü (31 Ekim): `stopped_by_escape` hiç okunmuyordu; kullanıcı Esc ile durdurduğunu
    değil genel "Tur iptal edildi"yi görüyordu. Çağıran (REPL, `run_agent_task`) bunu söyler.
    """
    turn = context.desktop.turn
    context.desktop.turn = None
    stopped = isinstance(turn, DesktopTurn) and turn.stopped_by_escape
    if isinstance(turn, DesktopTurn):
        try:
            turn.close()
        except (OSError, RuntimeError, ValueError):
            _logger.warning("Masaüstü oturumu kapatılamadı", exc_info=True)
    desktop_lock.release(token=context.job_scope)
    return stopped


def foreground_action(context: ToolContext) -> None:
    """Fare/klavye aracından: tur oturumu bağlıysa ilk eylem hazırlığını yap."""
    turn = context.desktop.turn
    if turn is None:
        return
    try:
        turn.foreground_action((context.desktop.target_pid,))
    except (OSError, RuntimeError, ValueError):
        # Gizleme ya da dinleyici kurulamasa da eylem sürer; neden günlüğe düşer.
        _logger.warning("Masaüstü ön plan hazırlığı başarısız", exc_info=True)
