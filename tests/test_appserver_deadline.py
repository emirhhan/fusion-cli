"""Masaüstü istek süresi yerel saate çevrilir; devam turları tazelemez."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from fusion_cli.appserver import session as app
from fusion_cli.appserver.protocol import Request

from .test_turn_deadline import FakeClock


async def test_protocol_maps_duration_once_to_server_clock_before_agent_entry(
    tmp_path, monkeypatch
):
    clock = FakeClock(123)
    monkeypatch.setattr(app, "SystemClock", lambda: clock, raising=False)
    execute = AsyncMock(return_value={"ok": True, "metin": "done"})
    lines = []
    session = app.AppSession(lines.append, root=tmp_path, home=tmp_path / "home")
    monkeypatch.setattr(session, "_run_turn", execute)
    try:
        await session.handle(Request("turn", "tur.calistir", {"gorev": "merhaba", "sure_s": 5}))
        deadline = execute.call_args.kwargs["deadline"]
        assert deadline.expires_at == 128
        assert deadline.clock is clock
        assert json.loads(lines[-1])["veri"]["ok"]
    finally:
        await session.close()


@pytest.mark.parametrize("duration", [True, -1, 0, float("inf"), float("nan")])
async def test_invalid_duration_is_rejected_before_turn_starts(tmp_path, monkeypatch, duration):
    execute = AsyncMock(return_value={"ok": True})
    lines = []
    session = app.AppSession(lines.append, root=tmp_path, home=tmp_path / "home")
    monkeypatch.setattr(session, "_run_turn", execute)
    try:
        await session.handle(
            Request("turn", "tur.calistir", {"gorev": "merhaba", "sure_s": duration})
        )
        assert not execute.called
        assert not json.loads(lines[-1])["veri"]["ok"]
    finally:
        await session.close()


async def test_auto_continuation_keeps_original_deadline_and_stops_when_it_expires(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from fusion_cli.cli import session as cli
    from fusion_cli.core.tools import TodoItem, TodoStatus
    from fusion_cli.core.turn_deadline import TurnDeadline

    clock = FakeClock()
    deadline = TurnDeadline.from_duration(5, clock)
    seen = []

    async def run(task, config, **kwargs):
        seen.append((kwargs["deadline"], kwargs["deadline"].remaining_s()))
        clock.value += 2 if len(seen) == 1 else 4
        return SimpleNamespace(
            ok=False,
            final_text="kaldı",
            messages=[],
            budget_stopped=True,
            stop_reason="model_calls",
            mutating_tool_calls_made=1,
            todos=(TodoItem("iş", TodoStatus.IN_PROGRESS),),
        )

    monkeypatch.setattr(cli, "run_agent_task", run)
    session = app.AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    try:
        result = await session._run_turn("uzun iş", deadline=deadline)
        assert not result["ok"]
        assert seen == [(deadline, 5), (deadline, 3)]
    finally:
        await session.close()


async def test_absent_duration_keeps_optional_deadline_empty(tmp_path, monkeypatch):
    execute = AsyncMock(return_value={"ok": True})
    session = app.AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    monkeypatch.setattr(session, "_run_turn", execute)
    try:
        await session.handle(Request("turn", "tur.calistir", {"gorev": "merhaba"}))
        assert execute.call_args.kwargs["deadline"] is None
    finally:
        await session.close()
