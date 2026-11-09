"""Optional original-trace reads cannot delay a turn or outlive clear ownership."""

from __future__ import annotations

import asyncio
import threading

import pytest

from fusion_cli.core.original_trace import OriginalTraceRead, OriginalTraceScope
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.memory import turn_journal


def _scope():
    return OriginalTraceScope("owner", "turn", ("segment",))


def _messages():
    return (
        Message("assistant", "", tool_calls=(ToolCall("call", "read_file", "{}"),)),
        Message("tool", "ORIGINAL", tool_call_id="call", name="read_file", ok=True),
    )


async def test_slow_original_reader_returns_unavailable_without_queuing(tmp_path, monkeypatch):
    journal = turn_journal.FileTurnJournal(tmp_path / "journal.json", original_owner_id="owner")
    release = threading.Event()
    calls = []
    monkeypatch.setattr(turn_journal, "ORIGINAL_READ_TIMEOUT_S", 0.02, raising=False)

    def slow(scope):
        calls.append(1)
        release.wait(2)
        return OriginalTraceRead(scope, "redacted_original", _messages())

    monkeypatch.setattr(journal, "_read_original", slow)
    try:
        assert (
            await asyncio.wait_for(journal.read_original(_scope()), 0.2)
        ).status == "unavailable"
        assert (
            await asyncio.wait_for(journal.read_original(_scope()), 0.2)
        ).status == "unavailable"
        assert calls == [1]
    finally:
        release.set()
    await asyncio.sleep(0.03)


@pytest.mark.parametrize("same_instance", [True, False])
async def test_clear_discards_a_pending_original_read(tmp_path, monkeypatch, same_instance):
    journal = turn_journal.FileTurnJournal(tmp_path / "journal.json", original_owner_id="owner")
    started = threading.Event()
    release = threading.Event()

    def slow(scope):
        started.set()
        release.wait(2)
        return OriginalTraceRead(scope, "redacted_original", _messages())

    monkeypatch.setattr(journal, "_read_original", slow)
    pending = asyncio.create_task(journal.read_original(_scope()))
    try:
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.001)
        assert started.is_set()
        clearer = (
            journal if same_instance else turn_journal.FileTurnJournal(tmp_path / "journal.json")
        )
        clearer.clear()
        release.set()
        assert (await asyncio.wait_for(pending, 0.2)).status == "unavailable"
    finally:
        release.set()


async def test_original_reader_io_failure_is_honest_unavailable(tmp_path, monkeypatch):
    journal = turn_journal.FileTurnJournal(tmp_path / "journal.json", original_owner_id="owner")

    def broken(scope):
        raise OSError("PRIVATE-PATH-DETAIL")

    monkeypatch.setattr(journal, "_read_original", broken)
    assert (await journal.read_original(_scope())).status == "unavailable"
