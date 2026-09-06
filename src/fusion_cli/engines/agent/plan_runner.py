"""Planı kanıtlı alt turlarla yürüt, finalde bozulan güvenli dalı onar."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from ...core.checkpoint import StepCheckpointEvidence, WorkflowBudgetUsage, WorkflowCheckpoint
from ...core.clock import SystemClock
from ...core.events import (
    ExecutionCheckpointSaved,
    ExecutionCompleted,
    ExecutionPaused,
    ExecutionPlanCreated,
    ExecutionRetryScheduled,
    ExecutionStepStarted,
    ExecutionStepVerified,
)
from ...core.evidence import EvidenceStatus
from ...core.execution_plan import (
    ExecutionPlan,
    PlanStatus,
    PlanStep,
    RetrySafety,
    StepStatus,
    ready_steps,
    validate_plan,
)
from ...core.failure import RecoveryAction
from ...core.rollback import StepRollback
from ...core.types import Message
from ...core.verification import VerificationResult
from ...core.workspace import IsolatedWorkspace, isolate
from ..workflow.model import BudgetEnvelope, BudgetLedger, WorkflowBudget
from .attempts import Attempt, choose_attempt
from .plan_checkpoint import (
    artifact_changed,
    capture_evidence,
    dependent_ids,
    invalidate,
    replace_step,
    resume_plan,
    stale_step_ids,
)
from .plan_context import step_deps, step_prompt, workflow_budget
from .plan_generation import RunAgent, generate_plan
from .promotion import PromotionContext
from .recovery import choose_recovery, classify_failure
from .step_verification import StepVerificationResult, verify_plan_acceptance, verify_step

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome


@dataclass
class _PlanRun:
    """Bir plan çalıştırmasının tek durum ve sayaç otoritesi."""

    task: str
    deps: AgentDeps
    agent: RunAgent
    current: ExecutionPlan
    limits: WorkflowBudget
    ledger: BudgetLedger
    evidence: dict[str, StepCheckpointEvidence] = field(default_factory=dict)
    outcomes: list[AgentOutcome] = field(default_factory=list)
    spent: dict[tuple[BudgetEnvelope, str], int] = field(default_factory=dict)
    baseline: tuple[str, ...] = ()
    #: Bu planda kaç kez bağlam özetlendi; devam eden tur bunu bilmelidir.
    condensations: int = 0
    planning_calls: int = 0
    final_calls: int = 0
    repair_ids: set[str] = field(default_factory=set)

    def charge(self, envelope: BudgetEnvelope, calls: int, scope: str = "") -> bool:
        """Reddedilen harcama bile gerçekte yapıldı; checkpoint'te kaybolmaz."""
        key = (
            envelope,
            scope if envelope in {BudgetEnvelope.PER_STEP, BudgetEnvelope.RECOVERY} else "",
        )
        self.spent[key] = self.spent.get(key, 0) + calls
        return self.ledger.charge(envelope, calls, scope=scope).allowed

    def remaining(self, envelope: BudgetEnvelope, scope: str = "") -> int:
        return max(0, self.limits.limit_for(envelope) - self.ledger.used(envelope, scope=scope))

    def progress(self) -> None:
        """Doğrulama kapısı çalıştı: idle saatini tazele.

        Idle sınırı DURAN BİR MODELİ yakalamak içindir; Fusion'ın kendi kapısını
        beklemek hareketsizlik değildir. Ölçüldü (Godot koşusu): tur, her biri
        120 saniyelik iki `godot --headless` kapısı yüzünden `inactivity` ile
        öldü. Mutlak tur süresi (`total_timeout_s`) DEĞİŞMEZ.
        """
        budget = getattr(self.deps, "budget", None)
        if budget is not None:
            budget.record_progress()

    def save(self) -> None:
        """Her geçişte gerçek kanıtları ve tüketilmiş zarfları sakla."""
        deps = self.deps
        if deps.checkpoint_store is None or not deps.conversation_id:
            return
        completed = tuple(
            step.step_id for step in self.current.steps if step.status is StepStatus.COMPLETED
        )
        clock = getattr(getattr(deps, "budget", None), "clock", None) or SystemClock()
        deps.checkpoint_store.save(
            WorkflowCheckpoint(
                self.current,
                str(deps.tool_context.root.resolve()),
                deps.conversation_id,
                completed,
                clock.now(),
                tuple(self.evidence.values()),
                tuple(
                    WorkflowBudgetUsage(envelope.value, scope, calls)
                    for (envelope, scope), calls in self.spent.items()
                ),
                self.condensations,
            )
        )
        deps.publisher.publish(
            ExecutionCheckpointSaved(
                plan_id=self.current.plan_id,
                completed_steps=len(completed),
            )
        )

    def outcome(self, text: str, *, ok: bool, budget_stopped: bool = False) -> AgentOutcome:
        """Tüm çıkış yollarında gerçek alt tur sayaçlarını topla."""
        from .loop import AgentOutcome

        return AgentOutcome(
            final_text=text,
            messages=[Message("assistant", text)],
            ok=ok,
            tool_calls_made=sum(item.tool_calls_made for item in self.outcomes),
            model_calls_made=self.planning_calls
            + sum(item.model_calls_made for item in self.outcomes),
            planning_calls_made=self.planning_calls,
            final_verification_calls=self.final_calls,
            mutating_tool_calls_made=sum(item.mutating_tool_calls_made for item in self.outcomes),
            failed_tool_calls=sum(item.failed_tool_calls for item in self.outcomes),
            already_done_calls=sum(item.already_done_calls for item in self.outcomes),
            tool_uses=tuple(use for item in self.outcomes for use in item.tool_uses),
            hit_step_limit=any(item.hit_step_limit for item in self.outcomes),
            budget_stopped=budget_stopped,
        )

    def pause(self, text: str, *, budget: bool = False) -> AgentOutcome:
        self.current = replace(self.current, status=PlanStatus.PAUSED)
        self.save()
        self.deps.publisher.publish(ExecutionPaused(plan_id=self.current.plan_id, reason=text))
        return self.outcome(text, ok=False, budget_stopped=budget)

    async def execute(
        self, step: PlanStep, guidance: str, *, recovery: bool, observe: bool
    ) -> tuple[PlanStep, AgentOutcome] | None:
        """Çağrıdan önce zarfı sınırla; yürütme başlamadan checkpoint al."""
        envelope = BudgetEnvelope.RECOVERY if recovery else BudgetEnvelope.PER_STEP
        remaining = self.remaining(envelope, step.step_id)
        if remaining <= 0:
            return None
        running = replace(step, status=StepStatus.RUNNING, attempts=step.attempts + 1)
        self.current = replace_step(self.current, running)
        self.save()
        deps = step_deps(self.deps, running, remaining, observe=observe)
        prompt = step_prompt(self.task, running, self.evidence)
        if guidance:
            prompt += f"\n\nKURTARMA YÖNERGESİ:\n{guidance}"
        allowed = deps.execution.allowed_tool_names if deps.execution else frozenset()
        outcome = await self.agent(
            prompt,
            deps,
            depth=1,
            self_review=False,
            verify=False,
            internal=True,
            plan_mode=observe,
            allowed_tools=set(allowed or ()),
        )
        self.outcomes.append(outcome)
        self.condensations += outcome.condensations
        if not self.charge(envelope, outcome.model_calls_made, step.step_id):
            self.current = replace_step(self.current, replace(running, status=StepStatus.BLOCKED))
            return None
        return running, outcome

    async def verify(
        self, step: PlanStep, outcome: AgentOutcome, *, observe: bool
    ) -> StepVerificationResult:
        """Gözlem turunda dış etkiyi yeniden istemeden gerçek koşulları doğrula."""
        checked_step = (
            replace(
                step,
                expected_effects=tuple(
                    effect for effect in step.expected_effects if effect.startswith("file:")
                ),
            )
            if observe
            else step
        )
        result = await verify_step(checked_step, outcome, self.deps, self.baseline)
        self.progress()
        if observe and result.unverified:
            result = replace(
                result,
                ok=False,
                findings=(*result.findings, "Dış durum salt-okunur kanıtla doğrulanamadı."),
            )
        self.deps.publisher.publish(
            ExecutionStepVerified(
                plan_id=self.current.plan_id,
                step_id=step.step_id,
                ok=result.ok,
                evidence=result.evidence,
                findings=result.findings,
            )
        )
        if result.ok:
            self.current = replace_step(self.current, replace(step, status=StepStatus.COMPLETED))
            self.evidence[step.step_id] = await capture_evidence(
                step, outcome, result, self.deps.tool_context.root
            )
            self.save()
        return result

    def _attempt_slots(self, step: PlanStep) -> int:
        """Bu adım için kaç aday koşturulacak.

        Paralel deneme OPT-IN'dir: zarf sıfırsa davranış birebir eskisi gibidir.
        Yinelenemez yan etkisi olan adımda (NEVER) aday çoğaltılmaz — aynı dış
        etkiyi iki kez üretmek, kazanan seçmekten daha pahalıdır.
        """
        if step.retry_safety is RetrySafety.NEVER:
            return 1
        kalan = self.remaining(BudgetEnvelope.ATTEMPTS)
        return 2 if kalan >= 2 else 1

    async def run_candidates(self, step: PlanStep, slots: int) -> AgentOutcome | None:
        """Adımı izole kopyalarda birkaç kez dene, kazananı KANITLA seç.

        Adaylar asıl projeyi görmez; yalnız kazananın değişikliği uygulanır. Hiçbir
        aday doğrulanmış kanıt üretemezse kazanan yoktur ve akış normal (tek turlu)
        yola düşer: yanlış adayı uygulamak, hiç denememekten kötüdür.
        """
        adaylar: list[tuple[Attempt, IsolatedWorkspace, AgentOutcome]] = []
        with ExitStack() as stack:
            for sira in range(slots):
                if not self.charge(BudgetEnvelope.ATTEMPTS, 1):
                    break
                alan = stack.enter_context(
                    isolate(self.deps.tool_context.root, name=f"{step.step_id}-{sira}")
                )
                aday_deps = replace(
                    self.deps, tool_context=replace(self.deps.tool_context, root=alan.root)
                )
                running = replace(step, status=StepStatus.RUNNING, attempts=step.attempts + 1)
                outcome = await self.agent(
                    step_prompt(self.task, running, self.evidence),
                    step_deps(
                        aday_deps,
                        running,
                        self.remaining(BudgetEnvelope.PER_STEP, step.step_id),
                        observe=False,
                    ),
                    depth=1,
                    self_review=False,
                    verify=False,
                    internal=True,
                )
                checked = await verify_step(running, outcome, aday_deps, self.baseline)
                adaylar.append(
                    (
                        Attempt(
                            name=f"{step.step_id}-{sira}",
                            ok=outcome.ok,
                            criteria=checked.criteria,
                            model_calls=outcome.model_calls_made,
                        ),
                        alan,
                        outcome,
                    )
                )
            kazanan = choose_attempt([aday for aday, _, _ in adaylar])
            if kazanan is None:
                return None
            secilen = next(item for item in adaylar if item[0].name == kazanan.name)
            secilen[1].apply()
            self.outcomes.append(secilen[2])
        tamam = replace(step, status=StepStatus.COMPLETED, attempts=step.attempts + 1)
        self.current = replace_step(self.current, tamam)
        checked = await verify_step(tamam, secilen[2], self.deps, self.baseline)
        self.evidence[step.step_id] = await capture_evidence(
            tamam, secilen[2], checked, self.deps.tool_context.root
        )
        self.save()
        return None

    async def run_step(self, step: PlanStep) -> AgentOutcome | None:
        """Tek adımı ve mevcut sınırlı kurtarma kararını yürüt."""
        self.deps.publisher.publish(
            ExecutionStepStarted(
                plan_id=self.current.plan_id,
                step_id=step.step_id,
                index=next(
                    index
                    for index, item in enumerate(self.current.steps, 1)
                    if item.step_id == step.step_id
                ),
                total_steps=len(self.current.steps),
                goal=step.goal,
            )
        )
        slots = self._attempt_slots(step)
        if slots > 1 and step.step_id not in self.repair_ids and not step.attempts:
            secildi = await self.run_candidates(step, slots)
            if (
                secildi is None
                and self.current.steps
                and any(
                    item.step_id == step.step_id and item.status is StepStatus.COMPLETED
                    for item in self.current.steps
                )
            ):
                return None
        recovering = step.step_id in self.repair_ids or step.attempts > 0
        observe = step.retry_safety is RetrySafety.OBSERVE_FIRST and recovering
        guidance = (
            "Final doğrulamasında bozulan koşulları onar."
            if step.step_id in self.repair_ids
            else ""
        )
        while True:
            executed = await self.execute(step, guidance, recovery=recovering, observe=observe)
            if executed is None:
                return self.pause(
                    f"Workflow bütçesi tükendi; '{step.step_id}' adımında duraklatıldı.",
                    budget=True,
                )
            running, outcome = executed
            verification = await self.verify(running, outcome, observe=observe)
            geri_alma = StepRollback(self.deps.tool_context.changes)
            if verification.ok:
                # Doğrulanan adımın çıktısı kalıcıdır; geri alma kaydı kapanır.
                geri_alma.keep()
                return None
            # Düşen deneme diske yarım durum bırakmamalı: sonraki deneme kendi
            # hatasıyla değil öncekinin enkazıyla uğraşıyordu (ölçüldü, Godot koşusu).
            geri_alma.discard()
            recovery = choose_recovery(
                classify_failure(outcome, verification), running, running.attempts
            )
            if recovery.action is RecoveryAction.PAUSE or observe:
                self.current = replace_step(
                    self.current, replace(running, status=StepStatus.BLOCKED)
                )
                return self.pause(
                    f"Plan adımı duraklatıldı: {step.step_id}. {recovery.reason} "
                    + ("; ".join(verification.findings) or outcome.final_text)
                )
            self.deps.publisher.publish(
                ExecutionRetryScheduled(
                    step_id=step.step_id,
                    action=recovery.action.value,
                    reason=recovery.reason,
                    attempt=running.attempts + 1,
                )
            )
            guidance, step, recovering = recovery.guidance, running, True
            observe = recovery.action is RecoveryAction.OBSERVE

    async def repair_final(self, acceptance: VerificationResult) -> bool:
        """Bulgunun ilişkili dalını aç; bağımsız tamamlanan adımları koru."""
        roots = await stale_step_ids(self.current, self.deps.tool_context.root)
        if not roots:
            roots = {
                step.step_id
                for step in self.current.steps
                if any(
                    evidence.criterion_id in step.success_criteria
                    and evidence.status is EvidenceStatus.FAILED
                    for evidence in acceptance.evidence
                )
            }
        if not roots:
            return False
        affected = dependent_ids(self.current, roots)
        self.current = invalidate(self.current, roots)
        self.evidence = {key: value for key, value in self.evidence.items() if key not in affected}
        self.repair_ids.update(affected)
        return all(
            step.retry_safety is not RetrySafety.NEVER
            and self.remaining(BudgetEnvelope.RECOVERY, step.step_id) > 0
            for step in self.current.steps
            if step.step_id in affected
        )

    async def finish(self, acceptance: VerificationResult) -> AgentOutcome:
        """Final geçmeden tamamlandı kaydetme; doğrulanmayan koşulları açıkça bildir."""
        warnings = list(acceptance.warnings)
        for saved in self.evidence.values():
            for criterion in saved.criteria:
                if criterion.status is not EvidenceStatus.PASSED:
                    warnings.append(
                        f"Başarı koşulu doğrulanamadı: {saved.step_id} / {criterion.criterion_id}."
                    )
        self.current = replace(self.current, status=PlanStatus.COMPLETED)
        self.save()
        self.deps.publisher.publish(
            ExecutionCompleted(
                plan_id=self.current.plan_id,
                total_steps=len(self.current.steps),
                warnings=tuple(warnings),
            )
        )
        text = self.outcomes[-1].final_text if self.outcomes else "Yürütme planı tamamlandı."
        if warnings:
            text += "\n\n" + "\n".join(f"UYARI: {warning}" for warning in warnings)
        return self.outcome(text, ok=True)

    async def run(self) -> AgentOutcome:
        """Adımları ve final onarımını aynı zarf yaşam döngüsü içinde yürüt."""
        while True:
            while ready := ready_steps(self.current):
                paused = await self.run_step(ready[0])
                if paused is not None:
                    return paused
            if any(step.status is not StepStatus.COMPLETED for step in self.current.steps):
                return self.pause(
                    "Planın tamamlanmamış adımları güvenli devam veya bağımlılık kanıtı bekliyor."
                )
            if not self.charge(BudgetEnvelope.FINAL, 1):
                # Bu kapı çalıştırılmadı; reddedilen ön tahsisi gerçek maliyetten çıkar.
                self.spent[(BudgetEnvelope.FINAL, "")] -= 1
                return self.pause(
                    "Workflow final doğrulama bütçesi tükendi; görev duraklatıldı.", budget=True
                )
            self.final_calls += 1
            evidence = tuple(
                [
                    criterion
                    for saved in self.evidence.values()
                    if not await artifact_changed(saved, self.deps.tool_context.root)
                    for criterion in saved.criteria
                ]
            )
            acceptance = await verify_plan_acceptance(self.current, self.deps, evidence=evidence)
            self.progress()
            if acceptance.ok:
                return await self.finish(acceptance)
            can_repair = await self.repair_final(acceptance)
            if not can_repair or self.remaining(BudgetEnvelope.FINAL) <= 0:
                detail = "; ".join(acceptance.findings) or acceptance.summary
                return self.pause(
                    f"Planın final doğrulaması başarısız oldu; duraklatıldı: {detail}"
                )
            self.save()


async def run_execution_plan(
    task: str,
    deps: AgentDeps,
    run_agent: RunAgent,
    *,
    plan: ExecutionPlan | None = None,
    promotion: PromotionContext | None = None,
) -> AgentOutcome:
    """Plan üretimi, kanıtlı devam ve final onarımı için ortak giriş noktası."""
    limits = workflow_budget(deps)
    checkpoint = None
    if plan is None and deps.checkpoint_store is not None and deps.conversation_id:
        checkpoint = deps.checkpoint_store.find_resumable(
            str(deps.tool_context.root.resolve()), deps.conversation_id
        )
    current = plan or (checkpoint.plan if checkpoint else None)
    run = _PlanRun(
        task, deps, run_agent, current or ExecutionPlan("", task, ()), limits, BudgetLedger(limits)
    )
    if current is None:
        generated = await generate_plan(task, deps, run_agent, limits.planning, promotion)
        run.planning_calls = generated.calls
        allowed = run.charge(BudgetEnvelope.PLANNING, generated.calls)
        if not allowed or generated.plan is None:
            return run.outcome(
                f"Plan üretilemedi: {generated.error or 'Planlama bütçesi tükendi.'}",
                ok=False,
                budget_stopped=not allowed or limits.planning == 0,
            )
        current = generated.plan
    validation = validate_plan(current)
    if not validation.ok:
        return run.outcome(f"Yürütme planı geçersiz: {' '.join(validation.errors)}", ok=False)
    deps.publisher.publish(
        ExecutionPlanCreated(plan_id=current.plan_id, total_steps=len(current.steps))
    )
    if checkpoint is not None:
        run.ledger.restore(checkpoint.budget_usage)
        run.spent = {
            (BudgetEnvelope(item.envelope), item.scope): item.calls
            for item in checkpoint.budget_usage
        }
        current, run.evidence = await resume_plan(checkpoint, deps)
    run.current = replace(current, status=PlanStatus.RUNNING)
    run.save()
    # Plan BAŞLAMADAN önceki kapı bulguları planın suçu değildir; yarım kurulmuş
    # projede kapı her adımda düşer ve hiçbir adım geçemez. Ölçüldü: sıfırdan
    # Godot projesi kuran plan "no main scene defined" ile her adımda düştü. Bir
    # kez çalışır (kapı pahalıdır); final kabul yine TAM temizlik ister.
    if deps.verifier is not None:
        baseline = await deps.verifier.verify()
        if not baseline.ok:
            run.baseline = baseline.findings or ((baseline.summary,) if baseline.summary else ())
    run.progress()
    return await run.run()
