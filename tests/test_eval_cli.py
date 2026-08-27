from __future__ import annotations

import pytest
from evals import cli
from evals.metrics import RunReport


async def test_eval_run_closes_browser_pool_before_event_loop_returns(monkeypatch):
    lifecycle: list[str] = []

    async def fake_run_suite(tasks, executor, *, repeat):
        del tasks, executor, repeat
        lifecycle.append("run")
        return RunReport(results=())

    async def fake_close_all_browser_sessions():
        lifecycle.append("close")

    monkeypatch.setattr(cli, "run_suite", fake_run_suite)
    monkeypatch.setattr(cli, "close_all_browser_sessions", fake_close_all_browser_sessions)

    await cli._run_suite_and_close((), object(), repeat=1)

    assert lifecycle == ["run", "close"]


async def test_eval_run_closes_browser_pool_when_suite_raises(monkeypatch):
    closed = False

    async def fake_run_suite(tasks, executor, *, repeat):
        del tasks, executor, repeat
        raise RuntimeError("boom")

    async def fake_close_all_browser_sessions():
        nonlocal closed
        closed = True

    monkeypatch.setattr(cli, "run_suite", fake_run_suite)
    monkeypatch.setattr(cli, "close_all_browser_sessions", fake_close_all_browser_sessions)

    with pytest.raises(RuntimeError, match="boom"):
        await cli._run_suite_and_close((), object(), repeat=1)

    assert closed is True
