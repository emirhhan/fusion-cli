"""Stop ownership and cancellation retry regressions without external services."""

import asyncio
from types import SimpleNamespace

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.core.events import ToolStarted


async def test_stale_stop_cannot_cancel_goal_judging(tmp_path):
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    session._goal_turn_id = "current:1"
    task = asyncio.create_task(asyncio.Event().wait())
    session._goal_task = task
    try:
        result = await session._dispatch(Request(id="s", name="tur.kes", data={"turnId": "old:1"}))
        assert result["ok"] is False
        assert not task.cancelling()
        result = await session._dispatch(
            Request(id="s2", name="tur.kes", data={"turnId": "current:1"})
        )
        assert result["ok"] is True
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_chrome_busy_does_not_emit_started_or_cancel_native(tmp_path):
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    task = asyncio.create_task(asyncio.Event().wait())
    session._turn = task
    session._steering_turn = "native:1"
    try:
        result = await session._chrome_turn("read page", "panel:1")
        assert result["ok"] is False
        assert not session._chrome._feed
        assert session._chrome_cancel("panel:1")["ok"] is False
        assert not task.cancelling()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize(
    "tool,safe", [(None, True), ("read_file", True), ("run_shell", False), ("unknown_tool", False)]
)
async def test_cancel_retry_requires_no_possible_effect(tmp_path, monkeypatch, tool, safe):
    entered = asyncio.Event()
    calls = 0

    async def execute(task, config, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            return SimpleNamespace(
                ok=True, final_text="done", messages=[], tool_calls_made=0, tool_uses=()
            )
        if tool:
            kwargs["sinks"][0].handle(ToolStarted(name=tool, args={}, call_id="t1"))
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    data = {"gorev": "today", "gonderim_id": "retry"}
    waiting = asyncio.create_task(
        session._dispatch(Request(id="a", name="tur.calistir", data=data))
    )
    await entered.wait()
    session._cancel_turn()
    first = await waiting
    assert (first["makbuz"]["hata_kodu"] == "no_tool_effect") is safe
    await session._dispatch(
        Request(id="b", name="tur.calistir", data={**data, "yeniden_dene": True})
    )
    assert (calls == 2) is safe


async def test_stale_explicit_stop_cannot_cancel_unidentified_legacy_turn(tmp_path):
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    task = asyncio.create_task(asyncio.Event().wait())
    session._turn = task
    try:
        for identifier in ("old:1", None, ""):
            result = await session._dispatch(
                Request(id="s", name="tur.kes", data={"turnId": identifier})
            )
            assert result["ok"] is False
            assert not task.cancelling()
        result = await session._dispatch(Request(id="s", name="tur.kes", data={}))
        assert result["ok"] is True
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_panel_cancel_requires_current_admitted_owner(tmp_path, monkeypatch):
    entered = asyncio.Event()

    async def execute(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    waiting = asyncio.create_task(session._chrome_turn("read", "panel:2"))
    await entered.wait()
    assert session._chrome._feed[0]["turnId"] == "panel:2"
    for identifier in ("panel:1", None, ""):
        assert session._chrome_cancel(identifier)["ok"] is False
        assert not session._turn.cancelling()
    assert session._chrome_cancel("panel:2")["ok"] is True
    assert (await waiting)["turnId"] == "panel:2"
    assert session._chrome._feed[-1]["tur"] == "bitti"
    assert session._chrome._feed[-1]["turnId"] == "panel:2"


async def test_durable_unfinished_write_blocks_retry_without_start_event(tmp_path, monkeypatch):
    from fusion_cli.core.types import Message, ToolCall

    entered = asyncio.Event()

    async def execute(task, config, **kwargs):
        kwargs["journal"].save(
            [
                Message("user", task),
                Message("assistant", "", tool_calls=(ToolCall("pending", "write_file", "{}"),)),
            ]
        )
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    waiting = asyncio.create_task(
        session._dispatch(
            Request(id="a", name="tur.calistir", data={"gorev": "write", "gonderim_id": "durable"})
        )
    )
    await entered.wait()
    session._cancel_turn()
    result = await waiting
    assert result["makbuz"]["hata_kodu"] == "executor_failed"


@pytest.mark.parametrize("previous_tool", ["read_file", "write_file"])
async def test_reused_call_id_cannot_hide_new_durable_write(tmp_path, monkeypatch, previous_tool):
    from fusion_cli.core.types import Message, ToolCall

    entered = asyncio.Event()
    previous = [
        Message("user", "previous"),
        Message("assistant", "", tool_calls=(ToolCall("reused", previous_tool, "{}"),)),
        Message("tool", "done", name=previous_tool, tool_call_id="reused", ok=True),
    ]

    async def execute(task, config, **kwargs):
        kwargs["journal"].save(
            [
                *previous,
                Message("user", task),
                Message("assistant", "", tool_calls=(ToolCall("reused", "write_file", "{}"),)),
            ]
        )
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    session._state.history = previous
    data = {"gorev": "write", "gonderim_id": "reused"}
    waiting = asyncio.create_task(
        session._dispatch(Request(id="a", name="tur.calistir", data=data))
    )
    await entered.wait()
    session._cancel_turn()
    first = await waiting
    assert first["makbuz"]["hata_kodu"] == "executor_failed"
    retry = await session._dispatch(
        Request(id="b", name="tur.calistir", data={**data, "yeniden_dene": True})
    )
    assert retry["makbuz"] == first["makbuz"]
    assert "dış etkisini doğrula" in retry["metin"]


async def test_missing_history_prefix_requires_observation_even_without_tool_events(
    tmp_path, monkeypatch
):
    from fusion_cli.core.types import Message

    entered = asyncio.Event()

    async def execute(task, config, **kwargs):
        # Compacted/replaced snapshot cannot prove the original attempt boundary.
        kwargs["journal"].save([Message("user", task)])
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    session._state.history = [Message("user", "earlier"), Message("assistant", "earlier answer")]
    waiting = asyncio.create_task(
        session._dispatch(
            Request(id="a", name="tur.calistir", data={"gorev": "read", "gonderim_id": "ambiguous"})
        )
    )
    await entered.wait()
    session._cancel_turn()
    result = await waiting
    assert result["makbuz"]["hata_kodu"] == "executor_failed"
