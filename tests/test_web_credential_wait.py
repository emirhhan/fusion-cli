"""Kilitli credential deposu event loop'u veya sınırsız worker'ı sahiplenemez."""

import asyncio
import threading

import pytest

from fusion_cli.core.types import CompletionRequest, Message
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential, WebTurn


def _request(timeout=0.1):
    return CompletionRequest(
        messages=(Message("user", "test"),), temperature=0, max_tokens=20, timeout_s=timeout
    )


def _adapter(factory, observed):
    async def transport(credential, messages, model):
        observed.append(credential.token)
        return WebTurn("ok")

    return WebProviderAdapter(
        model="test-web",
        credential=WebSessionCredential(),
        transport=transport,
        credential_factory=factory,
    )


async def test_credential_wait_yields_loop_and_can_be_cancelled():
    started, release = threading.Event(), threading.Event()
    worker = []
    observed = []

    def blocked():
        worker.append(threading.current_thread().daemon)
        started.set()
        release.wait(timeout=2)
        return WebSessionCredential(token="synthetic")

    task = asyncio.create_task(_adapter(blocked, observed).complete(_request(0.5)))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        # Senkron eski yol burada ancak worker bittikten sonra buraya gelebilir.
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not observed
        assert worker == [True]
    finally:
        release.set()


async def test_timed_out_native_call_keeps_single_worker_slot_until_it_really_finishes():
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls, observed = [], []

    def blocked():
        calls.append("started")
        started.set()
        try:
            release.wait(timeout=2)
            return WebSessionCredential(token="synthetic")
        finally:
            finished.set()

    adapter = _adapter(blocked, observed)
    first = asyncio.create_task(adapter.complete(_request(0.05)))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        assert not (await first).ok
        assert not (await adapter.complete(_request(0.03))).ok
        assert calls == ["started"]
        assert not observed
    finally:
        release.set()
        await asyncio.to_thread(finished.wait, 1)

    recovered = _adapter(lambda: WebSessionCredential(token="fresh-synthetic"), observed)
    assert (await recovered.complete(_request(1))).ok
    assert observed == ["fresh-synthetic"]


async def test_credential_error_does_not_leak_details_and_slot_recovers():
    def broken():
        raise ValueError("private synthetic credential detail")

    result = await _adapter(broken, []).complete(_request())
    assert not result.ok
    assert "private synthetic credential detail" not in (result.error or "")
    assert (await _adapter(lambda: WebSessionCredential(token="ok"), []).complete(_request())).ok
