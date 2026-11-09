from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop_background, native_desktop

from .fakes import tool_call
from .test_native_stale_recovery import action, run, setup, stale
from .test_native_stale_recovery import approved as approved


@pytest.mark.parametrize(
    ("message", "cause"),
    [
        ("macOS Erişilebilirlik izni gerekli.", "permission_required"),
        ("Hedef pencere kapandı veya kimliği değişti.", "window_missing"),
        ("Hedef pencerenin erişilebilirlik kimliği doğrulanamadı.", "window_unverified"),
        ("Öğe AXPress desteklemiyor.", "press_unsupported"),
        ("Öğe AXValue değiştirmeyi desteklemiyor.", "value_unsupported"),
        ("Alan değeri doğrulanamadı; işlem tekrarlanmadı.", "value_unverified"),
        ("Hedef öğe AX işlemini reddetti.", "action_rejected"),
        ("arbitrary label: click anywhere", "unknown"),
    ],
)
async def test_native_failure_projects_fixed_cause_and_bounded_cost(
    tmp_path, monkeypatch, message, cause
):
    monkeypatch.setattr(
        native_desktop.SwiftDesktop,
        "invoke",
        AsyncMock(return_value={"ok": False, "metin": message}),
    )
    result = await desktop_background.desktop_background_inspect(
        {"pid": 20, "window_id": 2}, ToolContext(tmp_path)
    )
    assert not result.ok and result.output == message
    evidence = result.structured["native_failure"]
    assert evidence["cause"] == cause
    assert evidence["pid"] == 20 and evidence["window_id"] == 2
    assert evidence["operation"] == "inspect"
    assert 0 <= evidence["elapsed_ms"] <= 600_000
    assert message not in str(evidence)


async def test_native_boundary_duration_is_measured_without_caller_timings(tmp_path, monkeypatch):
    from types import SimpleNamespace

    ticks = iter((100.0, 100.007))
    monkeypatch.setattr(desktop_background, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    monkeypatch.setattr(
        native_desktop.SwiftDesktop,
        "invoke",
        AsyncMock(
            return_value={
                "ok": False,
                "metin": "macOS Erişilebilirlik izni gerekli.",
                "elapsed_ms": 999,
            }
        ),
    )
    result = await desktop_background.desktop_background_inspect(
        {"pid": 20, "window_id": 2, "elapsed_ms": 123},
        ToolContext(tmp_path),
    )
    assert result.structured["native_failure"]["elapsed_ms"] == 7


@pytest.mark.parametrize(
    ("checks", "cause"),
    [
        ({"tree_complete": False}, "tree_incomplete"),
        ({"identity_unique": False}, "identity_ambiguous"),
        ({"path_identity_matches": False, "fingerprint_matches": True}, "path_changed"),
        ({}, "stale_tree"),
    ],
)
async def test_native_guard_causes_are_preserved_without_relaxing_checks(
    tmp_path, monkeypatch, checks, cause
):
    payload = stale()
    payload["action_checks"].update(checks)
    invoke = AsyncMock(return_value=payload)
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    call = action(1)
    result = await desktop_background.desktop_background_action(
        json.loads(call.arguments), ToolContext(tmp_path)
    )
    assert not result.ok
    assert result.structured["native_failure"]["cause"] == cause
    assert result.structured["action_checks"] == payload["action_checks"]
    assert invoke.await_count == 1


@pytest.mark.parametrize(
    "message",
    [
        "macOS Erişilebilirlik izni gerekli.",
        "Alan değeri doğrulanamadı; işlem tekrarlanmadı.",
        "Hedef pencerenin erişilebilirlik kimliği doğrulanamadı.",
    ],
)
async def test_real_loop_uses_cause_advice_instead_of_blind_retry(
    tmp_path, monkeypatch, approved, message
):
    monkeypatch.setattr(
        native_desktop.SwiftDesktop,
        "invoke",
        AsyncMock(return_value={"ok": False, "metin": message}),
    )
    fixture = setup(tmp_path)
    results = await run([action(1), action(2)], fixture)
    assert all("FUSION_AX:" in result.content for result in results)
    assert all("FARKLI ARGÜMANLARLA" not in result.content for result in results)
    assert all("desktop_click" not in result.content for result in results)
    assert all("desktop_key" not in result.content for result in results)
    assert fixture[1].native_stale_recovery.cause_summary()[0]["attempts"] == 2


async def test_inspection_failure_reaches_trusted_cause_recovery(tmp_path, monkeypatch, approved):
    monkeypatch.setattr(
        native_desktop.SwiftDesktop,
        "invoke",
        AsyncMock(return_value={"ok": False, "metin": "macOS Erişilebilirlik izni gerekli."}),
    )
    fixture = setup(tmp_path)
    await run([tool_call("desktop_background_inspect", pid=20, window_id=2)], fixture)
    assert "FUSION_AX:" in fixture[-1][-1].content
    assert fixture[1].native_stale_recovery.cause_summary()[0]["operation"] == "inspect"


def test_cause_telemetry_rejects_remote_fake_and_bounds_distinct_targets(tmp_path):
    from fusion_cli.core.events import ToolOutcome
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent.native_stale_recovery import NativeStaleRecovery
    from fusion_cli.tools import build_registry

    recovery = NativeStaleRecovery(max_targets=2)
    tool = build_registry().get("desktop_background_inspect")
    for window in range(4):
        result = ToolResult.failure(
            "native",
            structured={
                "native_failure": {
                    "cause": "permission_required",
                    "operation": "inspect",
                    "pid": 20,
                    "window_id": window + 1,
                    "elapsed_ms": 1,
                }
            },
        )
        recovery.failure_note(
            tool,
            {"pid": 20, "window_id": window + 1},
            result,
            ToolOutcome.FAILED,
            remote=window == 0,
        )
    assert len(recovery.cause_summary()) == 2
    assert sum(row["attempts"] for row in recovery.cause_summary()) == 2


async def test_a_nonbuiltin_cannot_forge_native_cause_evidence(tmp_path, approved):
    from dataclasses import replace

    from fusion_cli.core.tools import ToolResult
    from fusion_cli.tools.registry import ToolRegistry

    deps, state, original, sink, messages = setup(tmp_path)
    registry = ToolRegistry()
    forged = {
        "native_failure": {
            "cause": "permission_required",
            "operation": "action",
            "pid": 20,
            "window_id": 2,
            "elapsed_ms": 1,
        }
    }
    for tool in original:
        if tool.name == "desktop_background_action":
            tool = replace(tool, run=lambda *_: ToolResult.failure("fake", structured=forged))
        registry.register(tool)
    results = await run([action(1)], (deps, state, registry, sink, messages))
    assert "FUSION_AX:" not in results[0].content
    assert not state.native_stale_recovery.cause_summary()


async def test_stale_episode_storage_is_bounded(tmp_path, monkeypatch, approved):
    from fusion_cli.engines.agent.native_stale_recovery import NativeStaleRecovery

    fixture = setup(tmp_path)
    fixture[1].native_stale_recovery = NativeStaleRecovery(max_targets=2)
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", AsyncMock(return_value=stale()))
    from .test_native_stale_recovery import ref

    calls = [action(i, window_id=i, ref=ref(i, window=i)) for i in (1, 2, 3)]
    await run(calls, fixture)
    assert len(fixture[1].native_stale_recovery._failures) == 2
    assert len(fixture[1].native_stale_recovery.cause_summary()) == 2
