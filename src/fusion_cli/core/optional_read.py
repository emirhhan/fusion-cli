"""Bounded optional read-only work; no executor queue or late delivery."""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from typing import TypeVar

_T = TypeVar("_T")
_LOG = logging.getLogger(__name__)


class OptionalReadWorker:
    """One daemon reader per subsystem; a stuck read keeps its permit until it exits.

    Operations must be read-only. This helper cannot cancel a filesystem write or
    provide commit/cleanup guarantees for mutations.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._slot = threading.BoundedSemaphore(1)

    async def run(
        self,
        operation: Callable[[Callable[[], bool]], _T],
        *,
        timeout_s: float,
        fallback: _T,
        still_owned: Callable[[], bool],
    ) -> _T:
        if not math.isfinite(timeout_s) or timeout_s <= 0 or not still_owned():
            return fallback
        loop = asyncio.get_running_loop()
        if not self._slot.acquire(blocking=False):
            return fallback
        deadline = time.monotonic() + timeout_s
        stopped = threading.Event()
        completed: asyncio.Future[_T] = loop.create_future()

        def valid() -> bool:
            return not stopped.is_set() and time.monotonic() < deadline

        def deliver(result: _T) -> None:
            if valid() and not completed.done():
                completed.set_result(result if still_owned() else fallback)

        def worker() -> None:
            result = fallback
            try:
                if valid():
                    result = operation(valid)
            except Exception as error:
                _LOG.debug("Optional read skipped (%s).", type(error).__name__)
            finally:
                self._slot.release()
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(deliver, result)

        try:
            threading.Thread(target=worker, name=self._name, daemon=True).start()
        except Exception as error:
            self._slot.release()
            _LOG.debug("Optional reader unavailable (%s).", type(error).__name__)
            return fallback
        try:
            done, _ = await asyncio.wait({completed}, timeout=max(0, deadline - time.monotonic()))
            return completed.result() if done and valid() and still_owned() else fallback
        finally:
            stopped.set()
            completed.cancel()
