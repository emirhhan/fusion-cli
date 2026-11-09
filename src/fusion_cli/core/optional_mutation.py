"""One optional daemon mutation, with bounded waiting and cooperative revocation.

The operation must stage privately, check `valid` before publication, and
serialize final commit with its owner's clear lifecycle. Already-entered OS
syscalls cannot be cancelled; this helper does not promise physical rollback.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from collections.abc import Callable
from contextlib import suppress

_LOG = logging.getLogger(__name__)


class OptionalMutationWorker:
    def __init__(self, name: str) -> None:
        self._name = name
        self._slot = threading.BoundedSemaphore(1)

    async def run(
        self,
        operation: Callable[[Callable[[], bool]], bool],
        *,
        timeout_s: float,
        still_owned: Callable[[], bool],
    ) -> bool:
        if not math.isfinite(timeout_s) or timeout_s <= 0 or not still_owned():
            return False
        if not self._slot.acquire(blocking=False):
            return False
        loop = asyncio.get_running_loop()
        deadline = time.monotonic() + timeout_s
        stopped = threading.Event()
        completed: asyncio.Future[bool] = loop.create_future()

        def valid() -> bool:
            return not stopped.is_set() and time.monotonic() < deadline and still_owned()

        def deliver(result: bool) -> None:
            if not completed.done():
                completed.set_result(result and valid())

        def worker() -> None:
            result = False
            try:
                if valid():
                    result = operation(valid)
            except Exception as error:
                _LOG.debug("Optional mutation skipped (%s).", type(error).__name__)
            finally:
                self._slot.release()
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(deliver, result)

        try:
            threading.Thread(target=worker, name=self._name, daemon=True).start()
        except Exception as error:
            self._slot.release()
            _LOG.debug("Optional mutation unavailable (%s).", type(error).__name__)
            return False
        try:
            done, _ = await asyncio.wait({completed}, timeout=max(0, deadline - time.monotonic()))
            return completed.result() if done and valid() else False
        finally:
            stopped.set()
            completed.cancel()
