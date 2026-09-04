"""Tipli yürütme planını mevcut agent motorunun temiz alt turlarında çalıştırır."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ...core.checkpoint import WorkflowCheckpoint
from ...core.events import (
    ExecutionCheckpointSaved,
    ExecutionCompleted,
    ExecutionPaused,
    ExecutionPlanCreated,
    ExecutionRetryScheduled,
    ExecutionStepStarted,
    ExecutionStepVerified,
)
from ...core.execution_plan import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    StepStatus,
    ready_steps,
    validate_plan,
)
from ...core.failure import RecoveryAction
from ...core.types import Message
from ..workflow.model import BudgetEnvelope, BudgetLedger, WorkflowBudget
from .plan_parser import PlanParseError, parse_execution_plan
from .promotion import PromotionContext
from .recovery import choose_recovery, classify_failure
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


async def _generate_plan(
    task: str,
    deps: AgentDeps,
    run_agent: RunAgent,
    promotion: PromotionContext | None = None,
) -> tuple[ExecutionPlan, int]:
    """Planı üret; biçim hatasında yalnızca bir onarım turu kullan.

    Görev hızlı yoldan yükseltildiyse plan üreten alt tur o turun KANITINI da görür:
    aksi halde zaten yapılmış işi baştan planlar ve yan etkiyi ikinci kez üretir.
    """
    prompt = _PLAN_PROMPT.replace("{task}", task)
    if promotion is not None:
        prompt = f"{promotion.render()}\n\n{prompt}"
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
        return parse_execution_plan(outcome.final_text), max(1, outcome.model_calls_made)
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
        calls = max(1, outcome.model_calls_made) + max(1, repaired.model_calls_made)
        return parse_execution_plan(repaired.final_text), calls


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


def _save_checkpoint(plan: ExecutionPlan, deps: AgentDeps) -> None:
    """Varsa checkpoint deposuna yalnızca gerekli plan durumunu yaz."""
    if deps.checkpoint_store is None or not deps.conversation_id:
        return
    deps.checkpoint_store.save(
        WorkflowCheckpoint(
            plan=plan,
            root=str(deps.tool_context.root.resolve()),
            conversation_id=deps.conversation_id,
            completed_step_ids=tuple(
                step.step_id for step in plan.steps if step.status is StepStatus.COMPLETED
            ),
            updated_at=time.time(),
        )
    )
    deps.publisher.publish(
        ExecutionCheckpointSaved(
            plan_id=plan.plan_id,
            completed_steps=sum(
                step.status is StepStatus.COMPLETED for step in plan.steps
            ),
        )
    )


def _invalidate_step_and_dependents(plan: ExecutionPlan, step_id: str) -> ExecutionPlan:
    """Post-condition'ı bozulan adımı ve ona bağlı tamamlanmış adımları sıfırla."""
    invalid = {step_id}
    changed = True
    while changed:
        before = len(invalid)
        invalid.update(
            step.step_id for step in plan.steps if set(step.depends_on) & invalid
        )
        changed = len(invalid) != before
    return replace(
        plan,
        steps=tuple(
            replace(step, status=StepStatus.PENDING)
            if step.step_id in invalid
            else step
            for step in plan.steps
        ),
    )


async def _resume_plan(
    checkpoint: WorkflowCheckpoint,
    deps: AgentDeps,
) -> tuple[ExecutionPlan, dict[str, str]]:
    """Tamamlanmış checkpoint adımlarını yeniden ölçerek güvenli devam planı kur."""
    from .loop import AgentOutcome

    plan = checkpoint.plan
    evidence: dict[str, str] = {}
    for step in plan.steps:
        if step.status is not StepStatus.COMPLETED:
            continue
        observed = AgentOutcome(
            final_text="checkpoint post-condition yeniden denetimi",
            messages=[],
            tool_calls_made=1,
            mutating_tool_calls_made=1,
        )
        verification = await verify_step(step, observed, deps)
        if not verification.ok:
            plan = _invalidate_step_and_dependents(plan, step.step_id)
            break
        evidence[step.step_id] = " | ".join(verification.evidence)
    return replace(plan, status=PlanStatus.RUNNING), evidence


async def run_execution_plan(
    task: str,
    deps: AgentDeps,
    run_agent: RunAgent,
    *,
    plan: ExecutionPlan | None = None,
    promotion: PromotionContext | None = None,
) -> AgentOutcome:
    """Plan üretip hazır adımları sırayla temiz agent alt turlarında çalıştır.

    `promotion` yalnız hızlı yoldan yükseltilen turlarda doludur ve plan üretimine
    o turun tipli kanıtını taşır; ham mesaj geçmişi kopyalanmaz.
    """
    from .loop import AgentOutcome

    runtime = getattr(getattr(deps, "config", None), "runtime", None)
    workflow_budget = WorkflowBudget(
        planning=getattr(runtime, "workflow_planning_calls", 2),
        per_step=getattr(runtime, "workflow_step_calls", 8),
        recovery=getattr(runtime, "workflow_recovery_calls", 2),
        final=getattr(runtime, "workflow_final_verification_calls", 2),
    )
    ledger = BudgetLedger(workflow_budget)
    checkpoint = None
    if plan is None and deps.checkpoint_store is not None and deps.conversation_id:
        checkpoint = deps.checkpoint_store.find_resumable(
            str(deps.tool_context.root.resolve()), deps.conversation_id
        )
    try:
        current = plan or (checkpoint.plan if checkpoint is not None else None)
        if current is None:
            current, planning_calls = await _generate_plan(task, deps, run_agent, promotion)
            if not ledger.charge(BudgetEnvelope.PLANNING, planning_calls).allowed:
                text = "Workflow planlama bütçesi tükendi; görev güvenle duraklatıldı."
                return AgentOutcome(
                    final_text=text,
                    messages=[Message("assistant", text)],
                    ok=False,
                    budget_stopped=True,
                )
    except PlanParseError as exc:
        text = f"Plan üretilemedi: {exc}"
        return AgentOutcome(final_text=text, messages=[Message("assistant", text)], ok=False)

    validation = validate_plan(current)
    if not validation.ok:
        text = f"Yürütme planı geçersiz: {' '.join(validation.errors)}"
        return AgentOutcome(final_text=text, messages=[Message("assistant", text)], ok=False)

    deps.publisher.publish(
        ExecutionPlanCreated(plan_id=current.plan_id, total_steps=len(current.steps))
    )

    if checkpoint is not None:
        current, evidence = await _resume_plan(checkpoint, deps)
    else:
        current = replace(current, status=PlanStatus.RUNNING)
        evidence = {}
    _save_checkpoint(current, deps)
    outcomes: list[AgentOutcome] = []
    while ready := ready_steps(current):
        step = ready[0]
        deps.publisher.publish(
            ExecutionStepStarted(
                plan_id=current.plan_id,
                step_id=step.step_id,
                index=next(
                    index
                    for index, candidate in enumerate(current.steps, start=1)
                    if candidate.step_id == step.step_id
                ),
                total_steps=len(current.steps),
                goal=step.goal,
            )
        )
        guidance = ""
        recovering = False
        while True:
            running = replace(step, status=StepStatus.RUNNING, attempts=step.attempts + 1)
            current = _replace_step(current, running)
            prompt = _step_prompt(task, running, evidence)
            if guidance:
                prompt = f"{prompt}\n\nKURTARMA YÖNERGESİ:\n{guidance}"
            outcome = await run_agent(
                prompt,
                deps,
                depth=1,
                self_review=False,
                verify=False,
                internal=True,
            )
            outcomes.append(outcome)
            envelope = BudgetEnvelope.RECOVERY if recovering else BudgetEnvelope.PER_STEP
            calls = max(1, outcome.model_calls_made)
            if not ledger.charge(envelope, calls).allowed:
                current = _replace_step(current, replace(running, status=StepStatus.BLOCKED))
                current = replace(current, status=PlanStatus.PAUSED)
                _save_checkpoint(current, deps)
                text = (
                    f"Workflow {envelope.value} bütçesi tükendi; "
                    f"'{step.step_id}' adımında checkpoint alınarak duraklatıldı."
                )
                deps.publisher.publish(
                    ExecutionPaused(plan_id=current.plan_id, reason=text)
                )
                return AgentOutcome(
                    final_text=text,
                    messages=[Message("assistant", text)],
                    tool_calls_made=sum(item.tool_calls_made for item in outcomes),
                    model_calls_made=sum(item.model_calls_made for item in outcomes),
                    ok=False,
                    budget_stopped=True,
                )
            verification = await verify_step(running, outcome, deps)
            deps.publisher.publish(
                ExecutionStepVerified(
                    plan_id=current.plan_id,
                    step_id=step.step_id,
                    ok=verification.ok,
                    evidence=verification.evidence,
                    findings=verification.findings,
                )
            )
            if verification.ok:
                current = _replace_step(
                    current, replace(running, status=StepStatus.COMPLETED)
                )
                evidence[step.step_id] = " | ".join(verification.evidence)
                _save_checkpoint(current, deps)
                break

            failure = classify_failure(outcome, verification)
            recovery = choose_recovery(failure, running, running.attempts)
            if recovery.action is RecoveryAction.PAUSE:
                current = _replace_step(current, replace(running, status=StepStatus.BLOCKED))
                current = replace(current, status=PlanStatus.PAUSED)
                _save_checkpoint(current, deps)
                deps.publisher.publish(
                    ExecutionPaused(plan_id=current.plan_id, reason=recovery.reason)
                )
                detail = "; ".join(verification.findings) or outcome.final_text
                text = (
                    f"Plan adımı duraklatıldı: {step.step_id}. {recovery.reason} {detail}"
                )
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
            guidance = recovery.guidance
            deps.publisher.publish(
                ExecutionRetryScheduled(
                    step_id=step.step_id,
                    action=recovery.action.value,
                    attempt=running.attempts + 1,
                    reason=recovery.reason,
                )
            )
            recovering = True
            step = replace(running, status=StepStatus.PENDING)
            current = _replace_step(current, step)

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
    _save_checkpoint(current, deps)
    deps.publisher.publish(
        ExecutionCompleted(plan_id=current.plan_id, total_steps=len(current.steps))
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
