"""Owned streams close before terminal results, without changing call outcomes."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.core.events import Channel, ModelCallAbandoned, ModelCallFinished
from fusion_cli.core.types import ModelResult, StreamDone
from fusion_cli.providers.chain import FallbackProvider
from fusion_cli.providers.eventing import EventingProvider
from fusion_cli.providers.litellm_provider import LiteLlmProvider
from fusion_cli.providers.retrying import RetryingProvider

from .fakes import request


class Response:
    def __init__(self, mode="eof", close_mode="ok"):
        self.mode = mode
        self.close_mode = close_mode
        self.reads = 0
        self.closed = 0
        self.entered = asyncio.Event()
        self.close_exited = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.reads += 1
        if self.reads == 1:
            return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))])
        self.entered.set()
        if self.mode == "wait":
            await asyncio.Event().wait()
        if self.mode == "error":
            raise ValueError("original read failure")
        raise StopAsyncIteration

    async def aclose(self):
        self.closed += 1
        try:
            if self.close_mode == "hang":
                await asyncio.Event().wait()
            if self.close_mode == "fail":
                raise RuntimeError("secret-key task payload")
        finally:
            self.close_exited.set()


def setup(monkeypatch, response, *, wrapped=False):
    async def acquire(**kwargs):
        assert kwargs["max_tokens"] == 8192
        assert kwargs["timeout"] == 600
        assert kwargs["num_retries"] == 0
        return response

    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=acquire),
    )
    monkeypatch.setattr(
        LiteLlmProvider, "_rebuild", lambda *args: ModelResult("r", "test/model", "ok", 0, True)
    )
    leaf = LiteLlmProvider("test/model", role="r", api_key="synthetic-key")
    events = []
    if wrapped:
        leaf = EventingProvider(
            FallbackProvider([RetryingProvider(leaf, delays_s=[0])], role="r"),
            publisher=SimpleNamespace(publish=events.append),
            role="r",
            channel=Channel.SUBAGENT,
        )
    req = replace(request(), max_tokens=8192, timeout_s=600, max_retries=0)
    return leaf.stream(req), events


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("mode", ["eof", "error", "cancel", "close"])
async def test_owned_response_closed_once_before_terminal(monkeypatch, wrapped, mode):
    response = Response("wait" if mode == "cancel" else mode)
    stream, events = setup(monkeypatch, response, wrapped=wrapped)
    assert (await anext(stream)).text == "ok"
    if mode == "close":
        await stream.aclose()
    elif mode == "cancel":
        pending = asyncio.create_task(anext(stream))
        await response.entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        terminal = await anext(stream)
        assert isinstance(terminal, StreamDone)
        assert terminal.result.ok == (mode == "eof")
        if mode == "error":
            assert "original read failure" in terminal.result.error
        assert response.closed == 1
        await stream.aclose()
    assert response.closed == 1
    if wrapped:
        terminal_events = [
            e for e in events if isinstance(e, (ModelCallFinished, ModelCallAbandoned))
        ]
        assert len(terminal_events) == 1
        assert isinstance(
            terminal_events[0],
            ModelCallAbandoned if mode in ("cancel", "close") else ModelCallFinished,
        )


@pytest.mark.parametrize("mode", ["eof", "error", "cancel", "close"])
async def test_close_failure_preserves_primary_outcome(monkeypatch, caplog, mode):
    response = Response("wait" if mode == "cancel" else mode, "fail")
    stream, _ = setup(monkeypatch, response)
    await anext(stream)
    if mode == "close":
        await stream.aclose()
    elif mode == "cancel":
        pending = asyncio.create_task(anext(stream))
        await response.entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    else:
        terminal = await anext(stream)
        assert terminal.result.ok == (mode == "eof")
        if mode == "error":
            assert "original read failure" in terminal.result.error
        await stream.aclose()
    assert response.closed == 1
    assert "secret-key" not in caplog.text
    assert "task payload" not in caplog.text


async def test_cooperative_hanging_close_is_bounded_without_orphan(monkeypatch):
    response = Response(close_mode="hang")
    stream, _ = setup(monkeypatch, response)
    await anext(stream)
    before = asyncio.all_tasks()
    async with asyncio.timeout(2):
        terminal = await anext(stream)
    assert terminal.result.ok
    assert response.closed == 1
    assert response.close_exited.is_set()
    assert asyncio.all_tasks() == before
    await stream.aclose()


async def test_no_close_before_acquisition(monkeypatch):
    response = Response()
    stream, _ = setup(monkeypatch, response)
    entered = asyncio.Event()

    async def acquire(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=acquire),
    )
    pending = asyncio.create_task(anext(stream))
    await entered.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert response.closed == 0


@pytest.mark.parametrize("closer", [None, "sync"])
async def test_legacy_or_unknown_sync_closer_is_not_called(monkeypatch, closer):
    response = Response()
    response.aclose = None
    if closer == "sync":

        def forbidden():
            pytest.fail("unknown synchronous close must not run on event loop")

        response.aclose = forbidden
        response.close = forbidden
    stream, _ = setup(monkeypatch, response)
    assert [item async for item in stream][-1].result.ok


@pytest.mark.parametrize("mode", ["eof", "cancel", "close", "error"])
async def test_installed_sdk_closes_httpx_stream_offline(monkeypatch, mode):
    """Exercise the pinned SDK's actual aclose hook, without sockets or DNS."""
    import socket
    from importlib.metadata import version

    import httpx
    import litellm
    from openai import AsyncOpenAI

    assert version("litellm") == "1.105.1"
    assert version("httpx") == "0.28.1"

    def forbidden(*args, **kwargs):
        pytest.fail("network access forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)

    class Body(httpx.AsyncByteStream):
        def __init__(self):
            self.closed = 0
            self.entered = asyncio.Event()

        async def __aiter__(self):
            yield (
                b'data: {"id":"synthetic","object":"chat.completion.chunk",'
                b'"created":1,"model":"synthetic","choices":[{"index":0,'
                b'"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
            )
            self.entered.set()
            if mode == "cancel":
                await asyncio.Event().wait()
            if mode == "error":
                raise httpx.ReadError("synthetic read error")
            yield b"data: [DONE]\n\n"

        async def aclose(self):
            self.closed += 1

    body = Body()
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200, stream=body, headers={"content-type": "text/event-stream"}
            )
        )
    )
    client = AsyncOpenAI(
        api_key="synthetic-key",
        base_url="https://synthetic.invalid/v1",
        http_client=http,
        max_retries=0,
    )
    acquired = []

    async def acquire(**kwargs):
        result = await litellm.acompletion(**kwargs, client=client)
        acquired.append(result)
        return result

    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=acquire),
    )
    monkeypatch.setattr(
        LiteLlmProvider,
        "_rebuild",
        lambda *args: ModelResult("r", "openai/synthetic", "ok", 0, True),
    )
    provider = LiteLlmProvider("openai/synthetic", role="r", api_key="synthetic-key")
    stream = provider.stream(replace(request(), max_tokens=8192, timeout_s=600, max_retries=0))
    try:
        assert (await anext(stream)).text == "ok"
        if mode == "close":
            await stream.aclose()
        elif mode == "cancel":
            pending = asyncio.create_task(anext(stream))
            await body.entered.wait()
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        else:
            result = [item async for item in stream][-1].result
            assert result.ok == (mode == "eof")
        assert body.closed == 1
        assert acquired[0].completion_stream is None
    finally:
        await stream.aclose()
        await client.close()


@pytest.mark.parametrize("mode", ["close", "cancel"])
@pytest.mark.parametrize("health_and_pool", [False, True])
async def test_actual_factory_path_closes_owned_leaf(monkeypatch, mode, health_and_pool):
    from fusion_cli.core.health import HealthRegistry
    from fusion_cli.core.rate_control import RateControl
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.providers.factory import build_provider
    from fusion_cli.providers.key_pool import KeyPoolRegistry

    response = Response("wait")
    setup(monkeypatch, response)
    monkeypatch.setattr("fusion_cli.providers.factory.configure_litellm", lambda: None)
    events = []
    health = (
        HealthRegistry(
            failure_threshold=3,
            cooldown_s=60,
            alpha=0.3,
            rate_control=RateControl(ledger=SimpleNamespace(cooled_until=lambda key: 0)),
        )
        if health_and_pool
        else None
    )
    pools = (
        KeyPoolRegistry({"NVIDIA_NIM_API_KEY": "synthetic-one,synthetic-two"}, cooldown_s=60)
        if health_and_pool
        else None
    )
    provider = build_provider(
        ModelSpec(name="r", model="nvidia_nim/synthetic"),
        publisher=SimpleNamespace(publish=events.append),
        channel=Channel.SUBAGENT,
        retry_delays_s=(0,),
        health=health,
        key_pools=pools,
    )
    stream = provider.stream(replace(request(), max_tokens=8192, timeout_s=600, max_retries=0))
    await anext(stream)
    if mode == "close":
        await stream.aclose()
    else:
        pending = asyncio.create_task(anext(stream))
        await response.entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
    assert response.closed == 1
    assert len([e for e in events if isinstance(e, ModelCallAbandoned)]) == 1
    assert not any(isinstance(e, ModelCallFinished) for e in events)


async def test_closer_own_cancel_does_not_invent_caller_cancellation(monkeypatch):
    response = Response()

    async def close():
        response.closed += 1
        raise asyncio.CancelledError

    response.aclose = close
    stream, _ = setup(monkeypatch, response)
    assert [item async for item in stream][-1].result.ok
    assert response.closed == 1


async def test_caller_cancel_during_close_propagates_without_orphan(monkeypatch):
    response = Response(close_mode="hang")
    entered = asyncio.Event()
    original_close = response.aclose

    async def close():
        entered.set()
        await original_close()

    response.aclose = close
    stream, _ = setup(monkeypatch, response, wrapped=True)
    await anext(stream)
    pending = asyncio.create_task(anext(stream))
    await entered.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert response.closed == 1
    assert response.close_exited.is_set()


async def test_cancel_during_display_finish_abandons_once(monkeypatch):
    entered = asyncio.Event()

    class Display:
        async def feed(self, *args):
            return []

        async def finish(self):
            entered.set()
            await asyncio.Event().wait()

    response = Response()
    leaf_stream, _ = setup(monkeypatch, response)
    monkeypatch.setattr(
        "fusion_cli.providers.eventing.display_filter.open_stream", lambda _: Display()
    )
    leaf = SimpleNamespace(label="test/model", stream=lambda req: leaf_stream)
    events = []
    provider = EventingProvider(leaf, publisher=SimpleNamespace(publish=events.append), role="r")
    stream = provider.stream(request())
    await anext(stream)
    pending = asyncio.create_task(anext(stream))
    await entered.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert response.closed == 1
    assert len([e for e in events if isinstance(e, ModelCallAbandoned)]) == 1
    assert not any(isinstance(e, ModelCallFinished) for e in events)


async def test_diagnostic_failure_after_acquisition_still_closes(monkeypatch):
    response = Response()
    stream, _ = setup(monkeypatch, response)

    def observe(req, phase):
        if phase == "sdk_stream_open":
            raise ValueError("diagnostic failed")

    monkeypatch.setattr("fusion_cli.providers.litellm_provider.observe_phase", observe)
    terminal = await anext(stream)
    assert not terminal.result.ok
    assert response.closed == 1
    await stream.aclose()
