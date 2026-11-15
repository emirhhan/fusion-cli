"""İptal sırasında da arka plan thread'inin sonucunu sahiplen.

Bekleme SINIRLIDIR (`OWNED_THREAD_CANCEL_GRACE_S`): ölçüldü (30 Ekim), eski döngü iptal
sonrası iş parçacığı bitene dek sınırsız bekliyordu ve asılan bir iş parçacığında
(ağ okuması, kilit) kullanıcının "durdur"u hiç tamamlanmıyordu. Süre dolarsa iş
parçacığı "sahipsiz kaldı" olarak ERROR günlüğüne yazılır, `orphaned_thread_count` sayar ve
`add_orphan_listener` ile kaydolanlara bildirilir; iptal tamamlanır. İş parçacığı
durdurulamaz: bitince sayaç düşer. Not: sahipsiz iş parçacığı varsayılan
`to_thread` yürütücüsünün bir yuvasını tutmaya devam eder.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from .constants import OWNED_THREAD_CANCEL_GRACE_S
from .errors import CleanupFailedError

_P = ParamSpec("_P")
_T = TypeVar("_T")

_orphan_lock = threading.Lock()
_orphans: set[int] = set()
_orphan_listeners: list[Callable[[str], None]] = []


def orphaned_thread_count() -> int:
    """Şu an iptal edilmiş ama hâlâ çalışan (sahipsiz) iş parçacığı sayısı."""
    with _orphan_lock:
        return len(_orphans)


def add_orphan_listener(listener: Callable[[str], None]) -> None:
    """Bir iş parçacığı sahipsiz kaldığında çağrılır (argüman: işlemin adı)."""
    with _orphan_lock:
        _orphan_listeners.append(listener)


def remove_orphan_listener(listener: Callable[[str], None]) -> None:
    with _orphan_lock:
        if listener in _orphan_listeners:
            _orphan_listeners.remove(listener)


def _name(operation: Callable[..., object]) -> str:
    return getattr(operation, "__qualname__", None) or type(operation).__name__


def _abandon(owned: asyncio.Task[object], operation: Callable[..., object]) -> None:
    """Bitmeyen iş parçacığını sahipsiz say; bitince kaydı düşür, hatasını tüket."""
    name = _name(operation)
    key = id(owned)
    with _orphan_lock:
        _orphans.add(key)
        listeners = tuple(_orphan_listeners)
    log = logging.getLogger(__name__)
    log.error(
        "İptal sonrası %.1f sn içinde bitmeyen iş parçacığı sahipsiz kaldı: %s",
        OWNED_THREAD_CANCEL_GRACE_S,
        name,
    )
    for listener in listeners:
        try:
            listener(name)
        except Exception as error:
            log.error("Sahipsiz iş bildirimi uygulanamadı (%s).", type(error).__name__)

    def _finished(task: asyncio.Task[object]) -> None:
        with _orphan_lock:
            _orphans.discard(key)
        if not task.cancelled():
            task.exception()  # "never retrieved" uyarısı çıkmasın
        log.warning("Sahipsiz kalan iş parçacığı sonunda bitti: %s", name)

    owned.add_done_callback(_finished)


async def await_owned_thread(
    operation: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs
) -> _T:
    """İptal edilse de bitişi gözlenen worker."""
    return await _run_owned_thread(operation, None, *args, **kwargs)


async def await_cancellable_thread(
    operation: Callable[_P, _T], cancel: Callable[[], None], *args: _P.args, **kwargs: _P.kwargs
) -> _T:
    """Önce cooperative iptali bildir; sonra gerçek worker temizliğini bekle."""
    return await _run_owned_thread(operation, cancel, *args, **kwargs)


async def _run_owned_thread(
    operation: Callable[_P, _T],
    cancel: Callable[[], None] | None,
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _T:
    """Thread durdurulamaz; bitişini gözle ve sonra iptali yeniden yükselt."""
    owned = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
    try:
        return await asyncio.shield(owned)
    except asyncio.CancelledError:
        if cancel is not None:
            try:
                cancel()
            except Exception as callback_error:
                logging.getLogger(__name__).error(
                    "Worker iptal bildirimi uygulanamadı (%s).", type(callback_error).__name__
                )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + OWNED_THREAD_CANCEL_GRACE_S
        while not owned.done():
            remaining = deadline - loop.time()
            if remaining <= 0:
                _abandon(owned, operation)
                raise
            try:
                await asyncio.wait({owned}, timeout=remaining)
            except asyncio.CancelledError:
                continue
        if owned.done() and not owned.cancelled() and (error := owned.exception()) is not None:
            if isinstance(error, CleanupFailedError):
                raise error from None
            logging.getLogger(__name__).warning(
                "İptal sırasında thread işlemi başarısız", extra={"hata": type(error).__name__}
            )
        raise
