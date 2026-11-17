"""Explicit current-tab work cannot acquire authority from a model/tool request."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fusion_cli.appserver.chrome_bridge import ChromeBridge
from fusion_cli.appserver.chrome_task_scope import ChromeTaskScope, restricted_task, web_origin
from fusion_cli.appserver.protocol import Request
from tests.test_appserver_session import _session

PROMPT = (
    "Bu açık sekmenin şu an ne gösterdiğini eklentiyle kontrol edip iki kısa cümlede söyle. "
    "Başka bir siteye gitme."
)
TARGET = {"tabId": 7, "url": "https://example.com/", "scopeVersion": 1}


@pytest.mark.asyncio
async def test_first_foreign_request_blocked_before_bridge_executor(tmp_path, monkeypatch):
    session = _session(tmp_path, [])
    calls = []

    async def executor(identifier, future):
        calls.append(identifier)
        return {"ok": True, "veri": {}}

    monkeypatch.setattr(session._chrome, "_await_command", executor)
    session._chrome._server = object()  # fake transport, no listening socket
    session._chrome._mark_command_channel_alive()

    async def run(_task, _config, **kwargs):
        result = await kwargs["chrome_bridge"].invoke(
            "navigate", {"url": "https://www.magnific.com/"}
        )
        assert result["ok"] is False
        assert "görev" in result["hata"].lower()
        return SimpleNamespace(ok=True, final_text="Engellendi", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    try:
        await session._chrome_turn(PROMPT, "owned", target=TARGET)
        assert calls == []
        assert session._chrome._pending == {}
        assert session._chrome._command_leases == {}
    finally:
        session._chrome._server = None
        await session.close()


@pytest.mark.asyncio
async def test_accepted_target_survives_await_and_scope_clears(tmp_path, monkeypatch):
    session = _session(tmp_path, [])
    target = dict(TARGET)
    entered, release = asyncio.Event(), asyncio.Event()
    packets = []
    session._chrome._server = object()
    session._chrome._mark_command_channel_alive()

    async def executor(identifier, future):
        queue = session._chrome._devices.target().queue
        packets.append(queue.get_nowait())
        return {"ok": True, "veri": {}}

    monkeypatch.setattr(session._chrome, "_await_command", executor)

    async def run(_task, _config, **kwargs):
        entered.set()
        await release.wait()
        await kwargs["chrome_bridge"].invoke("snapshot", {})
        return SimpleNamespace(ok=True, final_text="ok", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    pending = asyncio.create_task(session._chrome_turn(PROMPT, "owned", target=target))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        target.update(tabId=99, url="https://foreign.test/")
        switched = await session._dispatch(
            Request("switch", "oturum.baslat", {"sohbet_id": "other"})
        )
        assert switched["ok"]
        # Model a live executor poll at this boundary. Chat switching under a loaded
        # suite can exceed the real device TTL; this test is not a disconnect test.
        session._chrome._mark_command_channel_alive()
        release.set()
        await asyncio.wait_for(pending, 5)
        assert packets[0]["taskScope"]["tabId"] == 7
        assert packets[0]["taskScope"]["origin"] == "https://example.com"
        # An unrelated unrestricted/manual command does not inherit finished work.
        await session._chrome.invoke("navigate", {"url": "https://foreign.test/"})
        assert "taskScope" not in packets[1]
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
        session._chrome._server = None
        await session.close()


@pytest.mark.asyncio
async def test_turn_transport_forwards_only_extension_target_and_request_device(monkeypatch):
    seen = []

    async def on_turn(prompt, turn_id, *, target):
        seen.append((prompt, turn_id, target))
        return {"ok": True}

    bridge = ChromeBridge(on_turn=on_turn)
    bridge._token = "fake-unit-token"
    replies = []

    async def reply(_writer, status, body, origin=""):
        replies.append((status, body))

    monkeypatch.setattr(bridge, "_reply", reply)
    body = json.dumps(
        {
            "prompt": PROMPT,
            "turnId": "owned",
            "cihaz": {"id": "request-device"},
            "target": {**TARGET, "deviceId": "model-device", "ignored": "anything"},
        }
    ).encode()
    reader = asyncio.StreamReader()
    reader.feed_data(
        b"POST /turn HTTP/1.1\r\nAuthorization: Bearer fake-unit-token\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    reader.feed_eof()
    writer = SimpleNamespace(close=lambda: None, wait_closed=AsyncMock())
    await bridge._handle(reader, writer)
    assert replies == [(200, {"ok": True})]
    assert seen == [(PROMPT, "owned", {**TARGET, "deviceId": "request-device"})]
    writer.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_scoped_device_disconnect_cannot_reconnect_or_use_another_browser(monkeypatch):
    bridge = ChromeBridge()
    bridge._server = object()
    bridge._mark_command_channel_alive("other-device")
    reconnect = AsyncMock()
    monkeypatch.setattr(bridge, "_connect_browser", reconnect)
    scope = ChromeTaskScope.from_target({**TARGET, "deviceId": "initial-device"})
    result = await bridge.invoke("snapshot", {}, task_scope=scope)
    assert result["ok"] is False
    reconnect.assert_not_called()
    assert bridge._devices.queue("other-device").empty()
    bridge._server = None


@pytest.mark.asyncio
async def test_old_executor_never_receives_a_scoped_command():
    bridge = ChromeBridge()
    bridge._server = object()
    bridge._mark_command_channel_alive()
    scope = ChromeTaskScope.from_target(TARGET)
    pending = asyncio.create_task(bridge.invoke("snapshot", {}, task_scope=scope))
    try:
        await asyncio.sleep(0)
        assert await bridge._poll("fusion-local", "Chrome") == {}
        result = await asyncio.wait_for(pending, 2)
        assert result["ok"] is False
        assert result["neden_kodu"] == "task_scope"
        assert bridge._pending == {}
        assert bridge._command_leases == {}
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        bridge._server = None


@pytest.mark.asyncio
async def test_current_executor_receives_immutable_scope_and_completes():
    bridge = ChromeBridge()
    bridge._server = object()
    bridge._mark_command_channel_alive()
    scope = ChromeTaskScope.from_target(TARGET)
    pending = asyncio.create_task(bridge.invoke("snapshot", {}, task_scope=scope))
    try:
        await asyncio.sleep(0)
        packet = await bridge._poll("fusion-local", "Chrome", task_scope_version=1)
        assert packet["taskScope"] == scope.packet()
        bridge._pending[packet["id"]].set_result({"ok": True, "veri": {"title": "Example"}})
        assert (await asyncio.wait_for(pending, 2))["ok"]
        assert bridge._pending == {}
        assert bridge._command_leases == {}
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        bridge._server = None


@pytest.mark.asyncio
async def test_old_restricted_client_without_target_fails_closed(tmp_path, monkeypatch):
    session = _session(tmp_path, [])
    called = []

    async def run(*args, **kwargs):
        called.append(True)
        return SimpleNamespace(ok=True, final_text="unexpected", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    try:
        result = await session._chrome_turn(PROMPT, "old-client")
        assert result["ok"] is False
        assert called == []
    finally:
        await session.close()


@pytest.mark.parametrize(
    "prompt",
    [
        PROMPT,
        "Use the current tab only",
        "Only this site please",
        "Sadece bu sekmeyi oku",
        "Don't go to another site",
    ],
)
def test_explicit_restriction_is_recognized(prompt):
    assert restricted_task(prompt)


@pytest.mark.parametrize(
    "prompt",
    [
        "Compare example.com and magnific.com",
        "Bu sayfayı oku ve başka bir siteye git",
        "Bu siteden component al ve projeye uygula",
    ],
)
def test_unrestricted_multisite_tasks_do_not_acquire_a_restriction(prompt):
    assert not restricted_task(prompt)


@pytest.mark.parametrize(
    ("url", "origin"),
    [
        ("https://Example.com:443/path", "https://example.com"),
        ("http://example.com:80/", "http://example.com"),
        ("https://example.com:444/", "https://example.com:444"),
        ("https://example.com:0/", "https://example.com:0"),
        ("file:///etc/passwd", None),
        ("https://user:pass@example.com", None),
        ("https://example.com:bad", None),
        ("https://example.com\n/", None),
    ],
)
def test_web_origin_has_browser_default_port_semantics(url, origin):
    assert web_origin(url) == origin


def test_task_scope_cannot_expand_via_model_arguments():
    scope = ChromeTaskScope.from_target(TARGET)
    assert scope.allows("navigate", {"url": "https://example.com:443/reload"})
    assert not scope.allows("navigate", {"url": "http://example.com/"})
    assert not scope.allows("navigate", {"url": "https://example.com:444/"})
    assert not scope.allows("snapshot", {"tabId": 99})
    assert not scope.allows("javascript", {"code": "location.href='https://foreign.test'"})


@pytest.mark.asyncio
async def test_cancelling_scoped_command_cleans_request_and_next_job(tmp_path, monkeypatch):
    session = _session(tmp_path, [])
    session._chrome._server = object()
    session._chrome._mark_command_channel_alive()
    entered = asyncio.Event()

    async def executor(identifier, future):
        entered.set()
        return await future

    monkeypatch.setattr(session._chrome, "_await_command", executor)

    async def run(_task, _config, **kwargs):
        await kwargs["chrome_bridge"].invoke("snapshot", {})
        return SimpleNamespace(ok=True, final_text="unexpected", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    pending = asyncio.create_task(session._chrome_turn(PROMPT, "cancel-owned", target=TARGET))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        session._chrome_cancel("cancel-owned")
        await asyncio.wait_for(pending, 5)
        assert session._chrome._pending == {}
        assert session._chrome._command_leases == {}
        assert await session._chrome._poll("fusion-local", "Chrome") == {}
        seen = []

        async def next_run(_task, _config, **kwargs):
            seen.append(kwargs["chrome_bridge"])
            return SimpleNamespace(ok=True, final_text="done", messages=[])

        monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", next_run)
        await session._chrome_turn("Compare example.com and magnific.com", "next")
        assert seen == [session._chrome]
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        session._chrome._server = None
        await session.close()
