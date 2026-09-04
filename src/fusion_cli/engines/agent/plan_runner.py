"""Tipli yürütme planını mevcut agent motorunun temiz alt turlarında çalıştırır."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ...core.execution_plan import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    StepStatus,
    ready_steps,
    validate_plan,
)
from ...core.types import Message
from .plan_parser import PlanParseError, parse_execution_plan
from .step_verification import verify_plan_acceptance, verify_step

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome

_PLAN_PROMPT = (Path(__file__).parent / "prompts" / "execution_plan.md").read_text(
    encoding="utf-8"
)


class RunAgent(Protocol):
    """Plan üretimi ve adım yürütmede kullanılan agent çağrı yüzeyi."""

    async def __call__(
        self,
        task: str,
        deps: AgentDeps,
        *,
        plan_mode: bool = ...,
        depth: int = ...,
        self_review: bool | None = ...,
        allowed_tools: set[str] | None = ...,
        verify: bool = ...,
        internal: bool = ...,
    ) -> AgentOutcome: ...


def _repair_prompt(task: str, invalid_output: str, error: PlanParseError) -> str:
    """Geçersiz plan için tek onarım çağrısının istemini üret."""
    return (
        f"Aşağıdaki plan geçersiz: {error}\n"
        "Şemaya uyan eksiksiz JSON'u yeniden üret. Yalnızca JSON döndür.\n\n"
        f"Asıl görev:\n{task}\n\nGeçersiz çıktı:\n{invalid_output[:4000]}"
    )


async def _generate_plan(task: str, deps: AgentDeps, run_agent: RunAgent) -> ExecutionPlan:
    """Planı üret; biçim hatasında yalnızca bir onarım turu kullan."""
    prompt = _PLAN_PROMPT.replace("{task}", task)
    outcome = await run_agent(
        prompt,
        deps,
        depth=1,
        self_review=False,
        plan_mode=True,
        verify=False,
        internal=True,
        allowed_tools=set(),
    )
    try:
        return parse_execution_plan(outcome.final_text)
    except PlanParseError as first_error:
        repaired = await run_agent(
            _repair_prompt(task, outcome.final_text, first_error),
            deps,
            depth=1,
            self_review=False,
            plan_mode=True,
            verify=False,
            internal=True,
            allowed_tools=set(),
        )
        return parse_execution_plan(repaired.final_text)


def _step_prompt(
    task: str,
    step: PlanStep,
    dependency_evidence: dict[str, str],
) -> str:
    """Bir adım için dar kapsamlı, kanıta bağlı alt-tur istemi üret."""
    evidence = "\n".join(
        f"- {dependency}: {dependency_evidence[dependency][:1200]}"
        for dependency in step.depends_on
    ) or "- Yok"
    return (
        f"ANA GÖREV:\n{task}\n\n"
        f"PLAN ADIMI [{step.step_id}]:\n{step.goal}\n\n"
        f"BAĞIMLILIK KANITLARI:\n{evidence}\n\n"
        "BAŞARI KOŞULLARI:\n"
        + "\n".join(f"- {criterion}" for criterion in step.success_criteria)
        + f"\n\nDOĞRULAMA İPUCU:\n{step.verification_hint}\n\n"
        "Yalnızca bu adımı tamamla. Sonuçta yaptığını ve gözlediğin kanıtı açıkça yaz."
    )


def _replace_step(plan: ExecutionPlan, updated: PlanStep) -> ExecutionPlan:
    """Plan içindeki tek adımı değişmez veri modeliyle güncelle."""
    return replace(
        plan,
        steps=tuple(updated if step.step_id == updated.step_id else step for step in plan.steps),
    )


async def run_execution_plan(
    task: str,
    deps: AgentDeps,
    run_agent: RunAgent,
    *,
    plan: ExecutionPlan | None = None,
    promotion: str | None = None,
) -> AgentOutcome:
    """Plan üretip hazır adımları sırayla temiz agent alt turlarında çalıştır."""
    from .loop import AgentOutcome

    del promotion  # İlerleyen hızlı yolun gerekçesi için ayrılmış sözleşme alanı.
    try:
        current = plan or await _generate_plan(task, deps, run_agent)
    except PlanParseError as exc:
        text = f"Plan üretilemedi: {exc}"
        return AgentOutcome(final_text=text, messages=[Message("assistant", text)], ok=False)

    validation = validate_plan(current)
    if not validation.ok:
        text = f"Yürütme planı geçersiz: {' '.join(validation.errors)}"
        return AgentOutcome(final_text=text, messages=[Message("assistant", text)], ok=False)

    current = replace(current, status=PlanStatus.RUNNING)
    evidence: dict[str, str] = {}
    outcomes: list[AgentOutcome] = []
    while ready := ready_steps(current):
        step = ready[0]
        running = replace(step, status=StepStatus.RUNNING, attempts=step.attempts + 1)
        current = _replace_step(current, running)
        outcome = await run_agent(
            _step_prompt(task, running, evidence),
            deps,
            depth=1,
            self_review=False,
            verify=False,
            internal=True,
        )
        outcomes.append(outcome)
        verification = await verify_step(running, outcome, deps)
        succeeded = verification.ok
        final_status = StepStatus.COMPLETED if succeeded else StepStatus.FAILED
        current = _replace_step(current, replace(running, status=final_status))
        if not succeeded:
            detail = "; ".join(verification.findings) or outcome.final_text
            text = f"Plan adımı başarısız oldu: {step.step_id}. {detail}"
            return AgentOutcome(
                final_text=text,
                messages=[Message("assistant", text)],
                tool_calls_made=sum(item.tool_calls_made for item in outcomes),
                model_calls_made=sum(item.model_calls_made for item in outcomes),
                failed_tool_calls=sum(item.failed_tool_calls for item in outcomes),
                mutating_tool_calls_made=sum(
                    item.mutating_tool_calls_made for item in outcomes
                ),
                ok=False,
            )
        evidence[step.step_id] = " | ".join(verification.evidence)

    if any(step.status is not StepStatus.COMPLETED for step in current.steps):
        text = "Yürütme planı ilerleyemedi: tamamlanmamış adımların bağımlılıkları hazır değil."
        return AgentOutcome(final_text=text, messages=[Message("assistant", text)], ok=False)

    current = replace(current, status=PlanStatus.COMPLETED)
    acceptance = await verify_plan_acceptance(current, deps)
    if not acceptance.ok:
        detail = "; ".join(acceptance.findings) or acceptance.summary
        text = f"Planın final doğrulaması başarısız oldu: {detail}"
        return AgentOutcome(
            final_text=text,
            messages=[Message("assistant", text)],
            tool_calls_made=sum(item.tool_calls_made for item in outcomes),
            model_calls_made=sum(item.model_calls_made for item in outcomes),
            failed_tool_calls=sum(item.failed_tool_calls for item in outcomes),
            mutating_tool_calls_made=sum(
                item.mutating_tool_calls_made for item in outcomes
            ),
            ok=False,
        )
    text = outcomes[-1].final_text if outcomes else "Yürütme planı tamamlandı."
    return AgentOutcome(
        final_text=text,
        messages=[Message("assistant", text)],
        tool_calls_made=sum(item.tool_calls_made for item in outcomes),
        model_calls_made=sum(item.model_calls_made for item in outcomes),
        failed_tool_calls=sum(item.failed_tool_calls for item in outcomes),
        mutating_tool_calls_made=sum(item.mutating_tool_calls_made for item in outcomes),
        hit_step_limit=any(item.hit_step_limit for item in outcomes),
        ok=True,
    )
