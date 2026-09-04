"""Tipli plan yürütücüsünün sıralama ve güvenlik davranışı."""

from __future__ import annotations

from dataclasses import dataclass

from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
from fusion_cli.core.types import Message
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan


def _step(step_id: str, *, depends_on: tuple[str, ...] = ()) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        goal=f"{step_id} işini yap",
        depends_on=depends_on,
        expected_effects=(),
        allowed_tool_families=("files",),
        success_criteria=(f"{step_id} kanıtlandı",),
        verification_hint="çıktıyı denetle",
        retry_safety=RetrySafety.SAFE,
    )


@dataclass
class _FakeAgent:
    prompts: list[str]

    async def __call__(self, task, deps, **kwargs):
        del deps, kwargs
        self.prompts.append(task)
        step_id = "inspect" if "inspect işini" in task else "patch"
        return AgentOutcome(
            final_text=f"{step_id} tamamlandı",
            messages=[Message("assistant", f"{step_id} tamamlandı")],
            tool_calls_made=1,
            model_calls_made=1,
        )


async def test_runner_bagimli_adimlari_sirayla_calistirir():
    plan = ExecutionPlan(
        plan_id="p",
        task="özellik ekle",
        steps=(_step("inspect"), _step("patch", depends_on=("inspect",))),
    )
    agent = _FakeAgent([])

    result = await run_execution_plan("özellik ekle", object(), agent, plan=plan)

    assert result.ok is True
    assert len(agent.prompts) == 2
    assert "inspect tamamlandı" in agent.prompts[1]
    assert "patch tamamlandı" in result.final_text


async def test_runner_basarisiz_adimdan_sonra_bagimli_adimi_calistirmaz():
    plan = ExecutionPlan(
        plan_id="p",
        task="özellik ekle",
        steps=(_step("inspect"), _step("patch", depends_on=("inspect",))),
    )

    async def failing_agent(task, deps, **kwargs):
        del task, deps, kwargs
        return AgentOutcome(final_text="başarısız", messages=[], ok=False)

    result = await run_execution_plan("özellik ekle", object(), failing_agent, plan=plan)

    assert result.ok is False
    assert "inspect" in result.final_text


async def test_gecersiz_model_plani_yalniz_bir_kez_onarilir():
    replies = iter(("{bozuk", "{hala bozuk"))
    calls: list[str] = []

    async def invalid_agent(task, deps, **kwargs):
        del deps, kwargs
        calls.append(task)
        return AgentOutcome(final_text=next(replies), messages=[])

    result = await run_execution_plan("özellik ekle", object(), invalid_agent)

    assert result.ok is False
    assert len(calls) == 2
    assert "plan üretilemedi" in result.final_text.lower()
