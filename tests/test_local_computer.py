"""Yerel host kimliği model girdisinden değil enjekte edilen bağımlılıktan gelir."""

import pytest

from fusion_cli.appserver.local_computer import LocalComputer, LocalHost
from fusion_cli.core.tools import ToolContent, ToolContext, ToolResult


async def cleanup(*args):
    pass


@pytest.mark.asyncio
async def test_snapshot_really_executes_and_uses_host_provenance(tmp_path):
    calls = []

    async def execute(name, args, context):
        calls.append((name, args, context))
        return ToolResult("Gerçek sonda", content=(ToolContent.image("image/png", "fixture"),))

    host = LocalHost("native-process", "session-one", "darwin")
    context = ToolContext(tmp_path)
    computer = LocalComputer(host, context, execute, lambda: True, lambda: 1, cleanup)
    result = await computer.invoke("snapshot")
    assert result.status == "observed"
    assert result.host == host and result.snapshot_id == "session-one:1"
    assert [call[0] for call in calls] == ["desktop_screenshot", "desktop_accessibility"]
    assert all(call[2] is context for call in calls)


@pytest.mark.asyncio
async def test_unavailable_host_permission_and_unknown_action_do_not_execute():
    async def execute(*args):
        pytest.fail("Executor çağrılmamalı")

    for platform, allowed, operation in [
        ("linux", True, "snapshot"),
        ("darwin", False, "snapshot"),
        ("darwin", True, "click"),
    ]:
        computer = LocalComputer(
            LocalHost("process", "session", platform),
            object(),
            execute,
            lambda allowed=allowed: allowed,
            lambda: 1,
            cleanup,
        )
        result = await computer.invoke(operation)
        assert result.status == "unavailable"


@pytest.mark.asyncio
async def test_revoked_after_execution_does_not_accept_snapshot():
    allowed = True
    calls = []

    async def execute(*args):
        nonlocal allowed
        calls.append(args[0])
        allowed = False
        return ToolResult("Sonuç")

    computer = LocalComputer(
        LocalHost("process", "session", "darwin"),
        object(),
        execute,
        lambda: allowed,
        lambda: 1,
        cleanup,
    )
    result = await computer.invoke("snapshot")
    assert result.status == "unavailable" and result.snapshot_id is None
    assert calls == ["desktop_screenshot"]


@pytest.mark.asyncio
async def test_executor_failure_and_exception_are_not_observed():
    async def failed(*args):
        return ToolResult.failure("Ekran kaydı izni yok")

    async def broken(*args):
        raise RuntimeError("Sonda çalışmadı")

    for execute in (failed, broken):
        result = await LocalComputer(
            LocalHost("process", "session", "darwin"),
            object(),
            execute,
            lambda: True,
            lambda: 1,
            cleanup,
        ).invoke("snapshot")
        assert result.status == "unavailable" and result.snapshot_id is None


@pytest.mark.asyncio
async def test_status_is_not_a_snapshot_and_empty_success_is_unverified(tmp_path):
    calls = []

    async def execute(name, args, context):
        calls.append(name)
        return ToolResult("Hazır")

    computer = LocalComputer(
        LocalHost("process", "session", "darwin"),
        ToolContext(tmp_path),
        execute,
        lambda: True,
        lambda: 1,
        cleanup,
    )
    status = await computer.invoke("status")
    assert status.status == "available" and status.snapshot_id is None and not calls
    result = await computer.invoke("snapshot")
    assert result.status == "unavailable" and result.snapshot_id is None


@pytest.mark.asyncio
async def test_snapshot_path_is_host_generated_and_rejects_unsafe_nonce(tmp_path):
    async def execute(*args):
        pytest.fail("Executor çağrılmamalı")

    computer = LocalComputer(
        LocalHost("process", "session", "darwin"),
        ToolContext(tmp_path),
        execute,
        lambda: True,
        lambda: -1,
        cleanup,
    )
    assert (await computer.invoke("snapshot")).status == "unavailable"


@pytest.mark.asyncio
async def test_reused_snapshot_id_cannot_be_accepted_as_fresh(tmp_path):
    calls = []

    async def execute(name, args, context):
        calls.append(name)
        return ToolResult("Kanıt", content=(ToolContent.image("image/png", "fixture"),))

    computer = LocalComputer(
        LocalHost("process", "session", "darwin"),
        ToolContext(tmp_path),
        execute,
        lambda: True,
        lambda: 1,
        cleanup,
    )
    assert (await computer.invoke("snapshot")).status == "observed"
    assert (await computer.invoke("snapshot")).status == "unavailable"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_repeated_sequences_use_one_owned_path_and_cleanup_every_attempt(tmp_path):
    sequence = iter([1, 2, 3])
    paths = []
    cleaned = []

    async def execute(name, args, context):
        if name == "desktop_screenshot":
            paths.append(args["path"])
        return ToolResult("Kanıt", content=(ToolContent.image("image/png", "fixture"),))

    async def clean(path, context):
        cleaned.append(path)

    computer = LocalComputer(
        LocalHost("process", "session", "darwin"),
        ToolContext(tmp_path),
        execute,
        lambda: True,
        lambda: next(sequence),
        clean,
    )
    for _ in range(3):
        assert (await computer.invoke("snapshot")).status == "observed"
    assert len(set(paths)) == 1 and cleaned == paths
    assert computer._last_sequence == 3 and not hasattr(computer, "_snapshot_ids")


@pytest.mark.asyncio
async def test_cancel_failure_cleanup_and_sanitized_diagnostics(tmp_path, caplog):
    import asyncio

    cleaned = []

    async def execute(*args):
        raise asyncio.CancelledError()

    async def clean(path, context):
        cleaned.append(path)

    computer = LocalComputer(
        LocalHost("process", "session", "darwin"),
        ToolContext(tmp_path),
        execute,
        lambda: True,
        lambda: 1,
        clean,
    )
    with pytest.raises(asyncio.CancelledError):
        await computer.invoke("snapshot")
    assert len(cleaned) == 1

    async def broken(*args):
        raise RuntimeError("SECRET-OUTPUT")

    result = await LocalComputer(
        LocalHost("process", "session", "darwin"),
        ToolContext(tmp_path),
        broken,
        lambda: True,
        lambda: 1,
        broken,
    ).invoke("snapshot")
    assert result.status == "unavailable"
    assert "SECRET-OUTPUT" not in caplog.text
    assert [record.operation for record in caplog.records] == ["snapshot", "cleanup"]


@pytest.mark.asyncio
async def test_permission_revoked_during_cleanup_cannot_return_observed(tmp_path):
    allowed = True

    async def execute(*args):
        return ToolResult("Kanıt", content=(ToolContent.image("image/png", "fixture"),))

    async def clean(*args):
        nonlocal allowed
        allowed = False

    computer = LocalComputer(
        LocalHost("process", "session", "darwin"),
        ToolContext(tmp_path),
        execute,
        lambda: allowed,
        lambda: 1,
        clean,
    )
    result = await computer.invoke("snapshot")
    assert result.status == "unavailable" and result.snapshot_id is None and not result.results
