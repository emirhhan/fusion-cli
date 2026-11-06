"""Bound cooperative async stream cleanup without tasks or executor work."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypeVar

T = TypeVar("T")
_CLOSE_TIMEOUT_S = 0.5
_logger = logging.getLogger(__name__)


async def close_stream(stream: object) -> None:
    """Close only a known async hook; never run arbitrary sync close code.

    The deadline requires cooperative cancellation, as does Python's async IO.
    Await inline so timeout cancellation joins cleanup rather than orphaning it.
    Only fixed diagnostic categories may cross this boundary.
    """
    task = asyncio.current_task()
    cancelling = task.cancelling() if task is not None else 0
    try:
        closer = getattr(stream, "aclose", None)
        if not callable(closer):
            return
        if not inspect.iscoroutinefunction(closer) and not inspect.isasyncgen(stream):
            return
        async with asyncio.timeout(_CLOSE_TIMEOUT_S):
            await closer()
    except asyncio.CancelledError:
        if task is not None and task.cancelling() > cancelling:
            raise
        _logger.warning("provider_stream_cleanup_cancelled")
    except TimeoutError:
        _logger.warning("provider_stream_cleanup_timeout")
    except Exception:
        _logger.warning("provider_stream_cleanup_failed")


@asynccontextmanager
async def closing_stream(stream: AsyncIterator[T]) -> AsyncIterator[AsyncIterator[T]]:
    """Give a forwarding generator ownership of its immediate inner stream."""
    try:
        yield stream
    finally:
        await close_stream(stream)
