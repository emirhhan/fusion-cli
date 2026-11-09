from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pytest import MonkeyPatch

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop_background, desktop_policy, native_desktop


def full_ref(label: str = "Delete", *, window: int = 2, pid: int = 20) -> str:
    return base64.b64encode(
        json.dumps(
            {
                "path": [0, 3, 7],
                "identity": f"AXButton\x1f{label}\x1fbutton\x1f",
                "fingerprint": "a" * 64,
                "id": window,
                "pid": pid,
            }
        ).encode()
    ).decode()


async def observe(monkeypatch: MonkeyPatch, context: ToolContext, ref: str) -> str:
    monkeypatch.setattr(
        native_desktop.SwiftDesktop,
        "invoke",
        AsyncMock(
            return_value={
                "ok": True,
                "id": 2,
                "pid": 20,
                "fingerprint": "a" * 64,
                "elements": [{"ref": ref, "title": "Delete", "unique": True}],
            }
        ),
    )
    result = await desktop_background.desktop_background_inspect(
        {"window_id": 2, "pid": 20}, context
    )
    assert result.ok
    return str(json.loads(result.output)["elements"][0]["ref"])


async def test_observation_shortens_and_action_restores_exact_native_ref(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    context = ToolContext(tmp_path)
    ref = full_ref()
    alias = await observe(monkeypatch, context, ref)
    assert alias.startswith("dref_") and len(alias) < 40
    invoke = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await desktop_background.desktop_background_action(
        {"window_id": 2, "pid": 20, "action": "press", "ref": alias}, context
    )
    assert result.ok
    assert invoke.call_args.args[1]["request"]["ref"] == ref


@pytest.mark.parametrize(
    "mismatch",
    ["context", "shared-child", "session", "turn", "window", "pid", "unknown", "reinspect"],
)
async def test_alias_mismatch_never_reaches_native(
    monkeypatch: MonkeyPatch, tmp_path: Path, mismatch: str
) -> None:
    context = ToolContext(tmp_path)
    alias = await observe(monkeypatch, context, full_ref())
    args: dict[str, object] = {"window_id": 2, "pid": 20, "action": "press", "ref": alias}
    if mismatch in {"context", "shared-child"}:
        child = (
            replace(context)
            if mismatch == "shared-child"
            else ToolContext(tmp_path, job_scope=context.job_scope)
        )
        if mismatch == "shared-child":
            assert child.desktop is context.desktop
        context = child
    elif mismatch == "session":
        context = replace(context, job_scope="different-session")
    elif mismatch == "turn":
        context.desktop.begin_observation_turn("next-turn")
    elif mismatch in {"window", "pid"}:
        args["window_id" if mismatch == "window" else "pid"] = 999
    elif mismatch == "unknown":
        args["ref"] = "dref_unknown"
    else:
        await observe(monkeypatch, context, full_ref("Other"))
    invoke = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await desktop_background.desktop_background_action(args, context)
    assert not result.ok
    invoke.assert_not_called()


async def test_alias_preserves_destructive_risk_before_approval(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    context = ToolContext(tmp_path)
    ref = full_ref()
    alias = await observe(monkeypatch, context, ref)
    probe = AsyncMock(
        return_value={"ok": True, "app": "Notes", "bundle": "com.apple.Notes", "pid": 20}
    )
    args = {"window_id": 2, "pid": 20, "action": "press", "ref": ref}
    original = await desktop_policy.assess("desktop_background_action", args, context, probe)
    short = await desktop_policy.assess(
        "desktop_background_action", {**args, "ref": alias}, context, probe
    )
    assert original is not None and original.risky is not None
    assert short == original


async def test_alias_keeps_native_stale_failure(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    context = ToolContext(tmp_path)
    alias = await observe(monkeypatch, context, full_ref())
    invoke = AsyncMock(
        return_value={
            "ok": False,
            "metin": "stale; inspect again",
            "action_checks": {"fingerprint_matches": False},
        }
    )
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await desktop_background.desktop_background_action(
        {"window_id": 2, "pid": 20, "action": "press", "ref": alias}, context
    )
    assert not result.ok and "stale" in result.output
    assert json.loads(result.output)["action_checks"]["fingerprint_matches"] is False


def test_table_expires_and_bounds_storage() -> None:
    from fusion_cli.core.desktop_ref_handles import DesktopRefHandles

    clock = [0.0]
    table = DesktopRefHandles(max_entries=2, max_bytes=1000, ttl_seconds=10, clock=lambda: clock[0])
    scope = (1, "session", "turn", 0)
    aliases = table.observe(scope, 20, 2, [full_ref(), full_ref("Save")])
    assert table.resolve(aliases[0], scope, 20, 2) == full_ref()
    with pytest.raises(ValueError):
        table.observe(scope, 20, 3, [full_ref(window=3)])
    clock[0] = 11
    with pytest.raises(ValueError):
        table.resolve(aliases[0], scope, 20, 2)
    assert table.entry_count == 0
    with pytest.raises(ValueError):
        table.observe(scope, 20, 2, ["x" * 1001])


async def test_late_inspect_cannot_publish_into_another_turn(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = ToolContext(tmp_path)

    async def invoke(*_args: object) -> dict[str, object]:
        context.desktop.begin_observation_turn("different-turn")
        return {"ok": True, "elements": [{"ref": full_ref()}]}

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await desktop_background.desktop_background_inspect(
        {"window_id": 2, "pid": 20}, context
    )
    assert not result.ok
    assert context.desktop.ref_handles.entry_count == 0


async def test_older_inspection_completion_preserves_newer_window_handles(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = ToolContext(tmp_path)
    first_started, release_first = asyncio.Event(), asyncio.Event()
    calls = 0

    async def invoke(*_args: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        label = "Old" if calls == 1 else "New"
        if calls == 1:
            first_started.set()
            await release_first.wait()
        return {"ok": True, "elements": [{"ref": full_ref(label)}]}

    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    args = {"window_id": 2, "pid": 20}
    old_task = asyncio.create_task(desktop_background.desktop_background_inspect(args, context))
    try:
        await asyncio.wait_for(first_started.wait(), timeout=1)
        newer = await desktop_background.desktop_background_inspect(args, context)
        assert newer.ok
        alias = json.loads(newer.output)["elements"][0]["ref"]
    finally:
        release_first.set()
        older = await old_task
    assert not older.ok
    invoke_action = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke_action)
    result = await desktop_background.desktop_background_action(
        {**args, "action": "press", "ref": alias},
        context,
    )
    assert result.ok
    assert invoke_action.call_args.args[1]["request"]["ref"] == full_ref("New")


@pytest.mark.parametrize("rewrite", ["none", "hook-foreign", "approval-expiry", "approval-foreign"])
async def test_real_execution_resolves_before_approval_recovery_and_native(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    rewrite: str,
) -> None:
    from fusion_cli.core.events import ToolOutcome
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.approval import Allowance, ApprovalRequest
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.hook_bridge import ToolGate

    from .fakes import tool_call
    from .test_native_stale_recovery import setup

    deps, state, registry, _sink, _messages = setup(tmp_path)
    ref = full_ref()
    alias = await observe(monkeypatch, deps.tool_context, ref)
    args = {"window_id": 2, "pid": 20, "ref": alias, "action": "press"}
    seen = []

    async def resolve(tool, arguments, *_args, **_kwargs):
        seen.append(arguments)
        assert arguments["ref"] == ref
        if rewrite == "approval-expiry":
            deps.tool_context.desktop.ref_handles.clear()
        return ApprovalRequest(tool, arguments, danger=None, pre_allowed=True, effect=tool.effect)

    monkeypatch.setattr(loop, "resolve_request", resolve)
    if rewrite == "approval-foreign":
        from types import SimpleNamespace

        policy = SimpleNamespace(
            decide=AsyncMock(return_value=Allowance({**args, "ref": "dref_foreign"}))
        )
        monkeypatch.setattr(loop, "_current_policy", lambda _deps: policy)
    if rewrite == "hook-foreign":
        monkeypatch.setattr(
            loop, "pre_tool_use", AsyncMock(return_value=ToolGate({**args, "ref": "dref_foreign"}))
        )
    invoke = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    invocations = []
    result, outcome = await loop._execute(
        tool_call("desktop_background_action", **args),
        args,
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
        state=state,
        native_invocations=invocations,
    )
    if rewrite == "none":
        assert result.ok
        assert seen and invocations[0].arguments["ref"] == ref
        assert invoke.call_args.args[1]["request"]["ref"] == ref
    else:
        assert not result.ok and outcome is ToolOutcome.BLOCKED
        invoke.assert_not_called()
        assert not invocations


async def test_production_boundary_fixture_measurement(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = ToolContext(tmp_path)
    baseline_chars = compact_chars = full_ref_chars = short_ref_chars = 0
    for observation in range(11):
        elements = [
            {
                "ref": full_ref(f"Synthetic control {index} for observation {observation}"),
                "title": f"Synthetic control {index}",
                "role": "AXButton",
                "unique": True,
            }
            for index in range(37)
        ]
        native_output = {
            "ok": True,
            "id": 2,
            "pid": 20,
            "fingerprint": "a" * 64,
            "elements": elements,
        }
        baseline_chars += len(json.dumps(native_output, ensure_ascii=False))
        full_ref_chars += sum(len(row["ref"]) for row in elements)
        monkeypatch.setattr(
            native_desktop.SwiftDesktop, "invoke", AsyncMock(return_value=native_output)
        )
        result = await desktop_background.desktop_background_inspect(
            {"window_id": 2, "pid": 20}, context
        )
        assert result.ok
        compact_chars += len(result.output)
        short_ref_chars += sum(len(row["ref"]) for row in json.loads(result.output)["elements"])
        assert all(not row["ref"].startswith("dref_") for row in native_output["elements"])
    metrics = {
        "observations": 11,
        "elements_per_observation": 37,
        "baseline_output_chars": baseline_chars,
        "compact_output_chars": compact_chars,
        "full_ref_chars": full_ref_chars,
        "short_ref_chars": short_ref_chars,
    }
    print(json.dumps(metrics, sort_keys=True))
    assert short_ref_chars < full_ref_chars * 0.1
    assert compact_chars < baseline_chars * 0.4
