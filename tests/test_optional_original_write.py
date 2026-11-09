from __future__ import annotations

import asyncio
import os
import stat
import threading

import pytest

from fusion_cli.core.original_trace import OriginalTraceScope
from fusion_cli.core.types import Message
from fusion_cli.memory import turn_journal


def scope(segment="segment"):
    return OriginalTraceScope("owner", "turn", (segment,))


@pytest.mark.parametrize("ending", ["deadline", "cancel", "clear-peer", "owner-change"])
async def test_blocked_staging_write_never_publishes_after_revocation(
    tmp_path, monkeypatch, ending
):
    path = tmp_path / "journal.json"
    journal = turn_journal.FileTurnJournal(path, original_owner_id="owner")
    peer = turn_journal.FileTurnJournal(path, original_owner_id="owner")
    assert await journal.append_original(scope("old"), [Message("assistant", "baseline")])
    before = journal.original_path.read_bytes()
    entered, exited = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original_fsync = os.fsync
    calls = []

    def blocked_fsync(descriptor):
        calls.append(1)
        assert stat.S_IMODE(os.fstat(descriptor).st_mode) == 0o600
        loop.call_soon_threadsafe(entered.set)
        try:
            release.wait(2)
            original_fsync(descriptor)
        finally:
            loop.call_soon_threadsafe(exited.set)

    monkeypatch.setattr(turn_journal, "ORIGINAL_WRITE_TIMEOUT_S", 0.03, raising=False)
    monkeypatch.setattr(turn_journal.os, "fsync", blocked_fsync)
    task = asyncio.create_task(journal.append_original(scope("new"), [Message("assistant", "new")]))
    try:
        await asyncio.wait_for(entered.wait(), 0.2)
        workers = [
            worker for worker in threading.enumerate() if worker.name == "fusion-original-write"
        ]
        assert len(workers) == 1 and workers[0].daemon
        if ending == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 0.2)
        elif ending == "clear-peer":
            peer.clear()
            assert not await asyncio.wait_for(task, 0.2)
        elif ending == "owner-change":
            journal._original_owner_id = "different-owner"
            assert not await asyncio.wait_for(task, 0.2)
        else:
            assert not await asyncio.wait_for(task, 0.2)
        # The stuck daemon retains the subsystem permit; no second worker queues.
        assert not await asyncio.wait_for(
            journal.append_original(scope("extra"), [Message("assistant", "skip")]), 0.2
        )
        assert calls == [1]
        if ending == "clear-peer":
            assert not journal.original_path.exists()
        else:
            assert journal.original_path.read_bytes() == before
    finally:
        release.set()
        if not task.done():
            await asyncio.gather(task, return_exceptions=True)
    await asyncio.wait_for(exited.wait(), 0.2)
    await asyncio.sleep(0.03)
    if ending == "clear-peer":
        assert not journal.original_path.exists()
    else:
        assert journal.original_path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


async def test_clear_serializes_with_an_already_entered_atomic_publish(tmp_path, monkeypatch):
    from pathlib import Path

    path = tmp_path / "journal.json"
    journal = turn_journal.FileTurnJournal(path, original_owner_id="owner")
    peer = turn_journal.FileTurnJournal(path, original_owner_id="owner")
    entered, cleared = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original_replace = Path.replace

    def blocked_replace(staged, target):
        loop.call_soon_threadsafe(entered.set)
        release.wait(2)
        return original_replace(staged, target)

    def clear():
        peer.clear()
        loop.call_soon_threadsafe(cleared.set)

    monkeypatch.setattr(Path, "replace", blocked_replace)
    monkeypatch.setattr(turn_journal, "ORIGINAL_WRITE_TIMEOUT_S", 0.03)
    task = asyncio.create_task(journal.append_original(scope(), [Message("assistant", "original")]))
    try:
        await asyncio.wait_for(entered.wait(), 0.2)
        assert not await asyncio.wait_for(task, 0.2)
        threading.Thread(target=clear, daemon=True).start()
        await asyncio.sleep(0.01)
        assert not cleared.is_set(), "clear cannot claim completion before the admitted OS publish"
    finally:
        release.set()
        if not task.done():
            await asyncio.gather(task, return_exceptions=True)
    await asyncio.wait_for(cleared.wait(), 0.3)
    assert not journal.original_path.exists()


async def test_append_deadline_can_expire_before_any_filesystem_work(tmp_path, monkeypatch):
    journal = turn_journal.FileTurnJournal(tmp_path / "journal.json", original_owner_id="owner")
    monkeypatch.setattr(turn_journal, "ORIGINAL_WRITE_TIMEOUT_S", 0, raising=False)
    assert not await journal.append_original(scope(), [Message("assistant", "private")])
    assert not list(tmp_path.iterdir())


async def test_oversized_original_append_leaves_previous_trace_intact(tmp_path, monkeypatch):
    journal = turn_journal.FileTurnJournal(tmp_path / "journal.json", original_owner_id="owner")
    assert await journal.append_original(scope("old"), [Message("assistant", "baseline")])
    before = journal.original_path.read_bytes()
    monkeypatch.setattr(turn_journal, "_ORIGINAL_FILE_BYTES", len(before) + 10)
    assert not await journal.append_original(scope("new"), [Message("assistant", "too large")])
    assert journal.original_path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


async def test_shared_path_owner_privacy_and_staged_redaction(tmp_path, monkeypatch):
    path = tmp_path / "journal.json"
    journal = turn_journal.FileTurnJournal(path, original_owner_id="owner")
    other = turn_journal.FileTurnJournal(path, original_owner_id="other-owner")
    canary = "sk-or-v1-" + "q" * 48
    original_fsync = os.fsync
    inspected = []

    def inspect_stage(descriptor):
        staged = list(tmp_path.glob(".fusion-original-*.tmp"))
        assert len(staged) == 1
        assert canary not in staged[0].read_text()
        assert stat.S_IMODE(staged[0].stat().st_mode) == 0o600
        inspected.append(1)
        original_fsync(descriptor)

    monkeypatch.setattr(turn_journal.os, "fsync", inspect_stage)
    assert await journal.append_original(scope(), [Message("assistant", "api_key=" + canary)])
    before = journal.original_path.read_bytes()
    assert not await other.append_original(scope(), [Message("assistant", "invalid owner")])
    foreign_scope = OriginalTraceScope("other-owner", "turn", ("foreign",))
    assert not await other.append_original(foreign_scope, [Message("assistant", "foreign")])
    assert journal.original_path.read_bytes() == before
    assert inspected == [1]
    assert not list(tmp_path.glob("*.tmp"))
