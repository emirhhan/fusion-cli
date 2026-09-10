"""Missing local inventory can recover after a read-only retry."""

import json
from dataclasses import replace

import pytest

from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    RetrySafety,
    VerificationCheck,
    VerificationCheckKind,
)
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan
from tests.test_plan_repair import _deps
from tests.test_plan_runner import _step


@pytest.mark.parametrize(
    "safety,external,expected",
    [(RetrySafety.OBSERVE_FIRST, False, True), (RetrySafety.OBSERVE_FIRST, True, False)],
)
@pytest.mark.parametrize("manifest_exists", [False, True])
async def test_observed_missing_inventory_gets_only_local_repair(
    tmp_path, safety, external, expected, manifest_exists
):
    deps = _deps(tmp_path)
    if manifest_exists:
        (tmp_path / "ASSETS.json").write_text(json.dumps({"missing.txt": {"license": "CC0"}}))
    step = replace(
        _step("assets", expected_effects=("file:ASSETS.json",)),
        retry_safety=safety,
        attempts=3,
        allowed_tool_families=("files", "web", "browser") if external else ("files", "web"),
        success_criteria=("assets",),
        verification_checks=(
            VerificationCheck("assets", VerificationCheckKind.FILE_EXISTS, "ASSETS.json"),
        ),
    )
    calls = []

    async def agent(task, turn_deps, **kwargs):
        calls.append(kwargs["plan_mode"])
        if not kwargs["plan_mode"]:
            assert "download_file" in kwargs["allowed_tools"]
            assert "run_shell" not in kwargs["allowed_tools"]
            assert "browser_click" not in kwargs["allowed_tools"]
            for name, text in [
                ("sound.txt", "real asset"),
                (
                    "ASSETS.json",
                    json.dumps(
                        {
                            "sound.txt": {
                                "source_url": "https://example.com/source",
                                "license": "CC0",
                            }
                        }
                    ),
                ),
            ]:
                path = tmp_path / name
                if path.exists():
                    turn_deps.tool_context.changes.record(path)
                else:
                    turn_deps.tool_context.changes.record_created(path)
                path.write_text(text)
                turn_deps.tool_context.touched.add(path)
        return AgentOutcome(
            final_text="observed" if kwargs["plan_mode"] else "done",
            messages=[],
            model_calls_made=1,
        )

    result = await run_execution_plan(
        "assets",
        deps,
        agent,
        plan=ExecutionPlan("asset-repair", "assets", (step,)),
        self_review=False,
    )
    assert result.ok is expected
    assert calls == ([True, False] if expected else [True])


@pytest.mark.parametrize(
    "change",
    [
        {"retry_safety": RetrySafety.NEVER},
        {"revision": 1},
        {"expected_effects": ("git_push",)},
        {"expected_effects": ("file:../outside",)},
        {"allowed_tool_families": ("files", "shell")},
    ],
)
def test_inventory_repair_preserves_safety_boundaries(tmp_path, change):
    from fusion_cli.engines.agent.recovery import can_repair_local_inventory

    step = replace(
        _step("assets", expected_effects=("file:ASSETS.json",)),
        retry_safety=RetrySafety.OBSERVE_FIRST,
        verification_checks=(
            VerificationCheck("assets", VerificationCheckKind.FILE_EXISTS, "ASSETS.json"),
        ),
    )
    assert not can_repair_local_inventory(replace(step, **change), tmp_path)
