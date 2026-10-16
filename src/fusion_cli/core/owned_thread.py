"""İptal sırasında da arka plan thread'inin sonucunu sahiplen."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from .errors import CleanupFailedError

_P = ParamSpec("_P")
_T = TypeVar("_T")


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
        while not owned.done():
            try:
                await asyncio.shield(owned)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if owned.done() and not owned.cancelled() and (error := owned.exception()) is not None:
            if isinstance(error, CleanupFailedError):
                raise error from None
            logging.getLogger(__name__).warning(
                "İptal sırasında thread işlemi başarısız", extra={"hata": type(error).__name__}
            )
        raise
