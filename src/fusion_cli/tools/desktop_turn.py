"""Turun masaüstü oturumu: Esc ile durdurma, diğer uygulamaları gizle / geri göster (P-033).

Claude CLI computer use bir tur boyunca: tek oturum kilidi tutar, diğer uygulamaları gizler
(terminal görünür kalır), "press Esc to stop" der ve Esc'i küresel iptal sayar; bitince
gizlenen uygulamaları geri gösterir (Desktop'ta "Unhide apps when Claude finishes").

Fusion'da tur sahibi (`cli/session.run_agent_task`, REPL) turun başında `begin` ile oturumu
`ToolContext.desktop.turn`'e bağlar, sonunda `finish` ile kapatır. Tek oturum kilidi tur sonunda
BIRAKILMAZ (#429): oturum çıkınca kalkar (`desktop_lock`).
Fare/klavye araçları ilk eylemde `foreground_action` çağırır; o an (bir kez):

- `desktop.escape_stops` açıksa Esc dinleyicisi başlar; Esc → tur görevine `cancel`
  (Ctrl+C / masaüstü "Durdur" ile aynı yol).
- Öndeki uygulama ve Fusion (bu süreç + ataları: Fusion.app ya da terminal) dışındaki normal
  uygulamalar gizlenir; `finish` onları geri gösterir. CLI'de (#428) gizleme ve geri gösterme
  her zaman açıktır ("Auto-unhide toggle: Always on"); masaüstü uygulamasında
  `desktop.background` (arka planda çalış) ve `unhide_on_finish` ("Unhide apps when Claude
  finishes") seçilebilir (`use_app_surface`).

Gizleme/gösterme ve dinleyici yan etkileri enjekte edilebilir (`DesktopTurnIo`): testler
gerçek uygulamaları gizlemez, olay musluğu kurmaz.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import subprocess
import sys
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
#: Bu süreç masaüstü uygulamasının çekirdeği mi? (`appserver.server.serve` işaretler.)
_APP_SURFACE = {"on": False}


def use_app_surface(on: bool = True) -> None:
    """Masaüstü uygulaması: arka planda çalış / geri göster ayarları ve sohbet başına kilit."""
    _APP_SURFACE["on"] = on


def is_app_surface() -> bool:
    return _APP_SURFACE["on"]


def turn_settings(settings: DesktopSettings) -> DesktopSettings:
    """CLI'de (#428) diğer uygulamalar her zaman gizlenir ve tur sonunda geri gösterilir."""
    if is_app_surface():
        return settings
    return dataclasses.replace(settings, background=False, unhide_on_finish=True)


def lock_token(context: ToolContext) -> str:
    """Kilit belirteci (#429): CLI'de süreç = oturum (boş belirteç); masaüstünde sohbet."""
    return context.job_scope if is_app_surface() else ""


def lock_label(context: ToolContext) -> str:
    """Hata metninde kilidi tutan oturumun adı."""
    surface = "Fusion masaüstü" if is_app_surface() else "Fusion CLI"
    return f"{surface} · {context.root.name or context.root} · süreç {os.getpid()}"


def claim_lock(context: ToolContext) -> str | None:
    """İlk computer use eyleminde kilidi al; başka oturum tutuyorsa hata metni."""
    return desktop_lock.claim(token=lock_token(context), label=lock_label(context))


def escape_listening() -> bool:
    """Ön plandaki bir turda Esc dinleyicisi kurulu mu? (kurulamadıysa gösterge Esc demez)."""
    return any(turn.escape_active for turn in list(_LISTENING))


def _default_hide(keep: Sequence[int]) -> tuple[int, ...]:
    if sys.platform == "win32":
        from .desktop_win32_screen import hide

        return hide(keep)
    from .native_desktop import invoke_sync

    result = invoke_sync("hide", {"kind": "apps", "request": {"keep": list(keep)}})
    hidden = result.get("hidden") if result.get("ok") else None
    return tuple(pid for pid in hidden if type(pid) is int) if isinstance(hidden, list) else ()


def _default_unhide(pids: Sequence[int]) -> None:
    if sys.platform == "win32":
        from .desktop_win32_screen import unhide

        unhide(pids)
        return
    from .native_desktop import invoke_sync

    invoke_sync("unhide", {"kind": "apps", "request": {"pids": list(pids)}})


def _default_escape(on_escape: Callable[[], None]) -> Callable[[], None] | None:
    """Esc dinleyicisini başlat; durdurma işlevini döndür (kurulamadıysa None)."""
    if sys.platform == "win32":
        # Windows (#430): alçak düzey klavye kancası; fiziksel Esc uygulamaya gitmez.
        from .desktop_win32_screen import escape

        return escape(on_escape)
    from .desktop_escape import EscapeWatch
    from .native_desktop import executable_sync

    watch = EscapeWatch(on_escape, executable=executable_sync)
    return watch.stop if watch.start() else None


#: İşletim sistemi bildirimleri (#447; Claude: "Claude is using your computer · press Esc to
#: stop", bitince ikinci bildirim).
NOTIFY_START = "Fusion bilgisayarını kullanıyor · durdurmak için Esc'e bas"
NOTIFY_DONE = "Fusion bilgisayarı kullanmayı bitirdi"


def _default_notify(text: str) -> None:
    """macOS bildirimi (beklemeden); `FUSION_NO_OS_NOTIFY` ya da başka platformda sessiz."""
    if os.environ.get("FUSION_NO_OS_NOTIFY") or sys.platform != "darwin":
        return
    script = f'display notification {json.dumps(text)} with title "Fusion"'
    subprocess.Popen(
        ["/usr/bin/osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


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
    notify: Callable[[str], None] = _default_notify


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
        self._notify(NOTIFY_START)

    def _notify(self, text: str) -> None:
        try:
            self.io.notify(text)
        except (OSError, ValueError):
            _logger.warning("Bilgisayar kullanımı bildirimi gösterilemedi", exc_info=True)

    def _escape(self) -> None:
        self.stopped_by_escape = True
        self.cancel()

    def close(self) -> None:
        """Dinleyiciyi durdur, gizlenenleri (ayar açıksa) geri göster. İki kez çağrılabilir."""
        with self._lock:
            stop, self._stop_escape = self._stop_escape, None
            hidden, self._hidden = self._hidden, ()
            announce, self._started = self._started, False
        _LISTENING.discard(self)
        if stop is not None:
            stop()
        if hidden and self.settings.unhide_on_finish:
            self.io.unhide(hidden)
        if announce:
            self._notify(NOTIFY_DONE)

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

    turn = DesktopTurn(turn_settings(context.desktop_settings), cancel, io or DesktopTurnIo())
    context.desktop.turn = turn
    return turn


def finish(context: ToolContext) -> bool:
    """Tur sonu (iptal/hata dahil): oturumu kapat; Esc ile durduysa True. Kilit kalır (#429).

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
    return stopped


def end_session(token: str = "") -> None:
    """Oturumdan çıkış (masaüstünde sohbet değişimi): kilit bu oturumunsa kalkar (#429)."""
    desktop_lock.release(token=token)


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
