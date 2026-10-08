"""Planın final kabulü eski veya tamamlanmamış render ürününü teslim edemez."""

import pytest

from fusion_cli.core.events import ExecutionCompleted, ExecutionPaused
from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.execution_plan import ExecutionPlan
from fusion_cli.core.job_evidence import JobCompletion, JobPhase
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan
from fusion_cli.tools import jobs, shell

from .test_plan_runner import _FakeDeps, _step


class PassingVerifier:
    async def verify(self):
        return VerificationResult(ok=True, summary="yeni kaynak kareleri geçti")


def render(context, mode):
    if mode in {"pending", "legacy"}:
        start = JobCompletion("fixture", "render", JobPhase.STARTED)
        uses = (ToolUse("run_shell", job_completion=start),)
        if mode == "legacy":
            done = JobCompletion("fixture", "render", JobPhase.COMPLETED, 0)
            uses = (*uses, ToolUse("job_status", job_completion=done))
        return uses
    command = "cat src/a.tsx > out.mp4" + ("; exit 1" if mode == "nonzero" else "")
    start = shell.run_shell(
        {
            "command": command,
            "background": True,
            "failure_check": "render",
            "failure_sources": ["src"],
            "expected_outputs": ["out.mp4"],
        },
        context,
    )
    done = jobs.job_status({"id": start.job_completion.job_id, "wait_s": 10}, context)
    return (
        ToolUse("run_shell", job_completion=start.job_completion),
        ToolUse("job_status", job_completion=done.job_completion),
    )


async def execute_plan(tmp_path, change):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.tsx").write_text("before")
    deps = _FakeDeps(ToolContext(root=tmp_path), verifier=PassingVerifier())
    receipts = []

    async def agent(task, step_deps, **kwargs):
        if "[Plan adımı render-step]" in task:
            uses = render(step_deps.tool_context, change)
            receipts.append(uses[-1].job_completion)
        else:
            uses = ()
            if change in {"source", "retry"}:
                (tmp_path / "src/a.tsx").write_text("after")
                uses = (ToolUse("edit_file", mutating=True),)
            elif change == "output":
                (tmp_path / "out.mp4").write_text("different product")
            elif change == "delete":
                (tmp_path / "out.mp4").unlink()
            elif change == "membership":
                (tmp_path / "src/new.tsx").write_text("new member")
            if change == "retry":
                uses = (*uses, *render(step_deps.tool_context, "unchanged"))
        return AgentOutcome(final_text="adım bitti", messages=[], tool_uses=uses)

    plan = ExecutionPlan(
        "render-plan",
        "video teslim et",
        (
            _step("render-step"),
            _step("change-step", depends_on=("render-step",)),
        ),
    )
    result = await run_execution_plan("video teslim et", deps, agent, plan=plan, self_review=False)
    return result, deps, receipts


@pytest.mark.parametrize(
    "change", ["source", "output", "delete", "membership", "pending", "nonzero"]
)
async def test_gercek_plan_pass_kapisi_eski_veya_basarisiz_teslimi_tamamlandi_saymaz(
    tmp_path, change
):
    result, deps, receipts = await execute_plan(tmp_path, change)
    assert not result.ok
    assert not any(isinstance(event, ExecutionCompleted) for event in deps.publisher.events)
    assert any(isinstance(event, ExecutionPaused) for event in deps.publisher.events)
    if change not in {"pending", "legacy"}:
        assert receipts[0].sources_before == receipts[0].sources_after
    assert "final kapsamını doğrulamadı" in result.final_text


@pytest.mark.parametrize("change", ["unchanged", "retry", "legacy"])
async def test_gercek_plan_taze_teslim_retry_ve_legacy_surec_korunur(tmp_path, change):
    result, deps, _ = await execute_plan(tmp_path, change)
    assert result.ok
    assert any(isinstance(event, ExecutionCompleted) for event in deps.publisher.events)
    assert not any(isinstance(event, ExecutionPaused) for event in deps.publisher.events)
    if change == "retry":
        assert "taze aynı kapsamla çözüldü" in result.final_text


async def test_kalite_onarimi_sonrasi_yazilan_kaynak_tamamlanma_oncesi_olculur(
    monkeypatch, tmp_path
):
    from fusion_cli.engines.agent.plan_runner import _PlanRun

    async def quality_gate(self):
        (tmp_path / "src/a.tsx").write_text("quality correction")
        return VerificationResult(ok=True)

    monkeypatch.setattr(_PlanRun, "quality_gate", quality_gate)
    result, deps, _ = await execute_plan(tmp_path, "unchanged")
    assert not result.ok and "tamamlandıktan sonra kaynak değişti" in result.final_text
    assert not any(isinstance(event, ExecutionCompleted) for event in deps.publisher.events)
