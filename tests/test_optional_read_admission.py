from __future__ import annotations

import asyncio
import threading
import time

import pytest

from fusion_cli.core.optional_read import OptionalReadWorker


async def test_waiting_reader_shares_its_original_deadline():
    reader = OptionalReadWorker("fixture-read-admission")
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    calls = []

    def first(_valid):
        loop.call_soon_threadsafe(entered.set)
        release.wait(1)
        return "first"

    task = asyncio.create_task(
        reader.run(first, timeout_s=1, fallback="skip", still_owned=lambda: True)
    )
    try:
        await asyncio.wait_for(entered.wait(), 0.2)
        started = time.monotonic()
        result = await reader.run(
            lambda _valid: calls.append(1),
            timeout_s=0.02,
            fallback=None,
            still_owned=lambda: True,
            wait_for_slot=True,
        )
        assert result is None and time.monotonic() - started < 0.2
        assert not calls
        # Existing callers retain immediate fallback when the slot is busy.
        assert (
            await reader.run(
                lambda _valid: "unexpected", timeout_s=1, fallback="skip", still_owned=lambda: True
            )
            == "skip"
        )
    finally:
        release.set()
        assert await task == "first"


async def test_cancelled_waiter_does_not_take_or_release_another_readers_permit():
    reader = OptionalReadWorker("fixture-read-admission")
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def first(_valid):
        loop.call_soon_threadsafe(entered.set)
        release.wait(1)
        return "first"

    task = asyncio.create_task(
        reader.run(first, timeout_s=1, fallback="skip", still_owned=lambda: True)
    )
    try:
        await asyncio.wait_for(entered.wait(), 0.2)
        waiter = asyncio.create_task(
            reader.run(
                lambda _valid: "second",
                timeout_s=1,
                fallback="skip",
                still_owned=lambda: True,
                wait_for_slot=True,
            )
        )
        await asyncio.sleep(0.01)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert (
            await reader.run(
                lambda _valid: "unexpected", timeout_s=1, fallback="skip", still_owned=lambda: True
            )
            == "skip"
        )
    finally:
        release.set()
        assert await task == "first"
    assert (
        await reader.run(
            lambda _valid: "next",
            timeout_s=1,
            fallback="skip",
            still_owned=lambda: True,
            wait_for_slot=True,
        )
        == "next"
    )
