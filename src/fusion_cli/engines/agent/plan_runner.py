"""Planı kanıtlı alt turlarla yürüt, finalde bozulan güvenli dalı onar."""

from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.browser_session import BrowserSession
from ...core.changeset import ChangeSet
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
    PlanPhase,
    PlanStatus,
    PlanStep,
    RetrySafety,
    StepStatus,
    VerificationCheckKind,
    ready_steps,
    validate_plan,
)
from ...core.failure import RecoveryAction
from ...core.rollback import StepRollback
from ...core.tools import PendingWrite, TodoList, ToolContext
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
from .plan_context import step_deps, step_prompt, workflow_budget, workspace_block
from .plan_generation import RunAgent, generate_plan
from .progress import progress_fingerprint
from .promotion import PromotionContext
from .recovery import choose_recovery, classify_failure
from .replan import merge_replanned_plan
from .step_verification import StepVerificationResult, verify_plan_acceptance, verify_step

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome


def _step_context(context: ToolContext, root: Path | None = None) -> ToolContext:
    """Bir alt turun değişken araç durumunu diğer adımlardan ayır."""
    return replace(
        context,
        root=root or context.root,
        todos=TodoList(),
        touched=set(),
        fully_read=set(),
        read_revisions={},
        pending=PendingWrite(),
        browser=BrowserSession(),
        changes=ChangeSet(),
        available_tools=set(context.available_tools),
    )


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
    #: İzole adayların tamamında gerçekten harcanan çağrılar. Yalnız kazanan
    #: `outcomes` listesine girer; kaybedenlerin maliyeti yine de kaybolmamalıdır.
    attempt_model_calls: int = 0
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

    def forget_rolled_back(self, paths: tuple[Path, ...]) -> None:
        """Geri alınan yazmaları tekrar kaydından da düş.

        Geri alma diski ESKİ hâline döndürür; o hâlde aynı düzenlemeyi yeniden
        istemek tekrar DEĞİLDİR, tek çıkış yoludur. İki kapı birbirini kilitliyordu:
        doğrulaması düşen adımın doğru düzenlemesi geri alınıyor, model aynı
        düzenlemeyi yineleyince tekrar kapısı "bunu zaten yaptın" diyordu.
        """
        if not paths:
            return
        butce = getattr(self.deps, "budget", None)
        if butce is not None:
            butce.forget_calls_touching(paths)

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
            + self.attempt_model_calls
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
    ) -> tuple[PlanStep, AgentOutcome, AgentDeps] | None:
        """Çağrıdan önce zarfı sınırla; yürütme başlamadan checkpoint al."""
        envelope = BudgetEnvelope.RECOVERY if recovery else BudgetEnvelope.PER_STEP
        remaining = self.remaining(envelope, step.step_id)
        if remaining <= 0:
            return None
        running = replace(step, status=StepStatus.RUNNING, attempts=step.attempts + 1)
        self.current = replace_step(self.current, running)
        self.save()
        turn_deps = replace(self.deps, tool_context=_step_context(self.deps.tool_context))
        deps = step_deps(turn_deps, running, remaining, observe=observe)
        prompt = step_prompt(
            self.task,
            running,
            self.evidence,
            workspace=workspace_block(self.deps.tool_context),
        )
        if guidance:
            prompt += f"\n\nKURTARMA YÖNERGESİ:\n{guidance}"
        allowed = deps.execution.allowed_tool_names if deps.execution else frozenset()
        try:
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
        except BaseException:
            deps.tool_context.changes.restore()
            raise
        finally:
            if deps.tool_context.browser.is_open:
                await deps.tool_context.browser.close()
        self.outcomes.append(outcome)
        self.condensations += outcome.condensations
        if not self.charge(envelope, outcome.model_calls_made, step.step_id):
            deps.tool_context.changes.restore()
            self.current = replace_step(self.current, replace(running, status=StepStatus.BLOCKED))
            return None
        return running, outcome, deps

    async def verify(
        self, step: PlanStep, outcome: AgentOutcome, *, observe: bool, deps: AgentDeps | None = None
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
        active_deps = deps or self.deps
        result = await verify_step(checked_step, outcome, active_deps, self.baseline)
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
                step, outcome, result, active_deps.tool_context.root
            )
            self.save()
        return result

    def _attempt_slots(self, step: PlanStep) -> int:
        """Bu adım için kaç aday koşturulacak.

        Paralel deneme OPT-IN'dir: zarf sıfırsa davranış birebir eskisi gibidir.
        Yinelenemez yan etkisi olan adımda (NEVER) aday çoğaltılmaz — aynı dış
        etkiyi iki kez üretmek, kazanan seçmekten daha pahalıdır.
        """
        if step.retry_safety is RetrySafety.NEVER or self.deps.tool_context.extra_roots:
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
                kalan = self.remaining(BudgetEnvelope.ATTEMPTS)
                if kalan <= 0:
                    break
                alan = stack.enter_context(
                    isolate(self.deps.tool_context.root, name=f"{step.step_id}-{sira}")
                )
                aday_baglam = _step_context(self.deps.tool_context, alan.root)
                aday_deps = replace(self.deps, tool_context=aday_baglam)
                running = replace(step, status=StepStatus.RUNNING, attempts=step.attempts + 1)
                try:
                    outcome = await self.agent(
                        step_prompt(
                            self.task,
                            running,
                            self.evidence,
                            workspace=workspace_block(aday_baglam),
                        ),
                        step_deps(
                            aday_deps,
                            running,
                            kalan,
                            observe=False,
                        ),
                        depth=1,
                        self_review=False,
                        verify=False,
                        internal=True,
                    )
                finally:
                    if aday_baglam.browser.is_open:
                        await aday_baglam.browser.close()
                self.attempt_model_calls += outcome.model_calls_made
                if not self.charge(BudgetEnvelope.ATTEMPTS, outcome.model_calls_made):
                    break
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
            terfi_kaydi = ChangeSet()
            degisenler = secilen[1].apply(changes=terfi_kaydi)
            uygulanan = {self.deps.tool_context.root / goreli for goreli in degisenler}
            self.deps.tool_context.touched.update(uygulanan)
            tamam = replace(step, status=StepStatus.COMPLETED, attempts=step.attempts + 1)
            checked = await verify_step(tamam, secilen[2], self.deps, self.baseline)
            if not checked.ok:
                terfi_kaydi.restore()
                self.deps.tool_context.touched.difference_update(uygulanan)
                return None
            self.deps.tool_context.changes.absorb(terfi_kaydi)
            # Model çağrıları yukarıda bütün adaylar için ayrıca sayıldı. Kazananın
            # araç ve mutasyon kanıtlarını korurken çağrısını iki kez sayma.
            self.outcomes.append(replace(secilen[2], model_calls_made=0))
        self.current = replace_step(self.current, tamam)
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
        unavailable: set[str] = set()
        if step.phase is PlanPhase.DISCOVERY:
            scoped = step_deps(self.deps, step, remaining=1, observe=True)
            allowed = scoped.execution.allowed_tool_names if scoped.execution else frozenset()
            for check in step.verification_checks:
                if check.kind in {
                    VerificationCheckKind.COMMAND,
                    VerificationCheckKind.REPRODUCTION,
                }:
                    unavailable.add("run_shell")
                elif check.kind is VerificationCheckKind.TOOL and check.target not in (
                    allowed or ()
                ):
                    unavailable.add(check.target)
        if unavailable:
            # Keşifte kabuk kapalıdır. Modeli bildiğimiz aynı engele tekrar
            # gönderme; eski checkpoint'lerde de sözleşmeyi önce onar.
            from .loop import AgentOutcome

            finding = (
                f"Keşif adımında {', '.join(sorted(unavailable))} kapalı fakat başarı koşulu "
                "bu araçları zorunlu tutuyor. Gerekiyorsa bu kontrolü execution evresindeki "
                "bir adıma taşı; keşfi salt-okunur araç kanıtıyla sınırla."
            )
            verification = StepVerificationResult(ok=False, findings=(finding,))
            outcome = AgentOutcome(final_text=finding, messages=[], ok=False)
            reason = "Adımın araç kapsamı ile doğrulama koşulu çelişiyor."
            if step.revision == 0:
                repaired, reason = await self.replan_failed_step(
                    step, outcome, verification, "discovery-command-conflict"
                )
                if repaired:
                    return None
            return self.pause(_pause_text(step.step_id, reason, verification, outcome))
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
            running, outcome, turn_deps = executed
            geri_alma = StepRollback(turn_deps.tool_context.changes)
            try:
                verification = await self.verify(running, outcome, observe=observe, deps=turn_deps)
            except BaseException:
                self.forget_rolled_back(geri_alma.discard())
                raise
            if verification.ok:
                self.deps.tool_context.changes.absorb(turn_deps.tool_context.changes)
                self.deps.tool_context.touched.update(turn_deps.tool_context.touched)
                return None
            # Düşen deneme diske yarım durum bırakmamalı: sonraki deneme kendi
            # hatasıyla değil öncekinin enkazıyla uğraşıyordu (ölçüldü, Godot koşusu).
            #
            # Geri alınan yazmalar tekrar kaydından da düşmelidir: aksi halde model
            # AYNI doğru düzenlemeyi tekrar denediğinde "bunu zaten yaptın" cevabını
            # alır ve adım hiç ilerleyemez (ölçüldü, 7 Eylül 42 görevlik set).
            self.forget_rolled_back(geri_alma.discard())
            fingerprint = progress_fingerprint(running, outcome, verification)
            repeated = bool(running.last_progress_fingerprint) and (
                fingerprint == running.last_progress_fingerprint
            )
            recovery = choose_recovery(
                classify_failure(outcome, verification),
                running,
                running.attempts,
                previous_guidance=guidance,
            )
            should_replan = (
                not observe
                and running.retry_safety is not RetrySafety.NEVER
                and running.revision == 0
                and (repeated or recovery.action is RecoveryAction.PAUSE)
            )
            if should_replan:
                replanned, reason = await self.replan_failed_step(
                    running, outcome, verification, fingerprint
                )
                if replanned:
                    return None
                self.current = replace_step(
                    self.current,
                    replace(
                        running,
                        status=StepStatus.BLOCKED,
                        last_progress_fingerprint=fingerprint,
                    ),
                )
                return self.pause(_pause_text(step.step_id, reason, verification, outcome))
            if recovery.action is RecoveryAction.PAUSE or observe:
                self.current = replace_step(
                    self.current,
                    replace(
                        running,
                        status=StepStatus.BLOCKED,
                        last_progress_fingerprint=fingerprint,
                    ),
                )
                return self.pause(_pause_text(step.step_id, recovery.reason, verification, outcome))
            self.deps.publisher.publish(
                ExecutionRetryScheduled(
                    step_id=step.step_id,
                    action=recovery.action.value,
                    reason=recovery.reason,
                    attempt=running.attempts + 1,
                )
            )
            guidance = recovery.guidance
            step = replace(running, last_progress_fingerprint=fingerprint)
            self.current = replace_step(self.current, step)
            self.save()
            recovering = True
            observe = recovery.action is RecoveryAction.OBSERVE

    async def replan_failed_step(
        self,
        step: PlanStep,
        outcome: AgentOutcome,
        verification: StepVerificationResult,
        fingerprint: str,
    ) -> tuple[bool, str]:
        """Aynı duvara çarpan dalı yalnız bir kez yeniden üret."""
        remaining = self.remaining(BudgetEnvelope.RECOVERY, step.step_id)
        if remaining <= 0:
            return False, "Yeniden planlama için ayrılan kurtarma bütçesi tükendi."
        completed = (
            ", ".join(
                item.step_id for item in self.current.steps if item.status is StepStatus.COMPLETED
            )
            or "yok"
        )
        findings = "; ".join(verification.findings) or "doğrulama kanıtı üretilemedi"
        task = (
            f"{self.task}\n\n"
            "YENİDEN PLANLAMA GÖREVİ:\n"
            f"Başarısız adım: {step.step_id} — {step.goal}\n"
            f"Doğrulama bulguları: {findings[:2000]}\n"
            f"Adımın son açıklaması: {outcome.final_text[:1200]}\n"
            f"Korunacak tamamlanmış adım kimlikleri: {completed}\n"
            "Mevcut plan (kalan teslimatlar da korunmalıdır):\n"
            f"{json.dumps(asdict(self.current), ensure_ascii=False)}\n"
            "Hata onarımı ana görevin kapsamını küçültmez. Hikaye, arayüz, test veya "
            "başka bir kalan teslimatı silme; etkilenen dalın hedeflerini yeni adımlarda koru.\n"
            "Aynı hatalı varsayımı tekrar etme. Kanıtlanmış doğru hedefleri koru; "
            "sorun evre veya araç kapsamıysa yalnız bu çelişkiyi gider. "
            "Önce gerçek yolu keşfeden "
            "bir adım gerekiyorsa ekle. Tamamlanmış adımları aynı kimlikle plana koy; "
            "onların işini yeniden isteme. Başarısız adımı ve ona bağlı dalı yeni kanıta "
            "göre değiştir. Eksiksiz ve geçerli bir yürütme planı döndür."
        )
        generated = await generate_plan(task, self.deps, self.agent, remaining, None)
        self.planning_calls += generated.calls
        if not self.charge(BudgetEnvelope.RECOVERY, generated.calls, step.step_id):
            return False, "Yeniden planlama kurtarma bütçesini aştı."
        if generated.plan is None:
            return False, f"Yeniden plan üretilemedi: {generated.error}"
        merged = merge_replanned_plan(self.current, generated.plan, step.step_id, fingerprint)
        if merged is None:
            return (
                False,
                "Yeniden plan aynı başarısız hedefi tekrarladı veya geçersiz bir dal üretti.",
            )
        affected = dependent_ids(self.current, {step.step_id})
        self.evidence = {key: value for key, value in self.evidence.items() if key not in affected}
        self.current = merged
        self.save()
        return True, ""

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
    execution_task = task
    if checkpoint is not None and task != checkpoint.plan.task:
        execution_task = (
            f"ASIL KULLANICI GÖREVİ:\n{checkpoint.plan.task}\n\n"
            f"KULLANICININ SON YÖNLENDİRMESİ:\n{task}"
        )
    run = _PlanRun(
        execution_task,
        deps,
        run_agent,
        current or ExecutionPlan("", task, ()),
        limits,
        BudgetLedger(limits),
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
        # Modelin görev özetini kullanıcı isteğinin yerine kalıcılaştırma.
        current = replace(generated.plan, task=task)
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


def _pause_text(
    step_id: str,
    reason: str,
    verification: StepVerificationResult,
    outcome: AgentOutcome,
) -> str:
    """Duraklatma mesajını kur: NEDEN duraklatıldığı + NE OLDUĞU birlikte.

    Ölçüldü (6 Eylül canlı koşusu, `erisilemeyen-kaynagi-uydurma`): adım
    doğrulamadan geçemedi ("beklenen çalışma alanı değişikliği gözlenmedi") ve
    duraklatma mesajı modelin açıklamasının YERİNE geçti. Kullanıcı yalnızca
    "adım duraklatıldı" gördü; adresin var olmadığını hiç öğrenemedi. Oysa
    modelin açıklaması tam da eksik olan bilgiydi.

    Bulgu ile açıklama farklı sorulara cevap verir ve biri diğerinin yerine
    geçemez: bulgu kapının neden kapandığını, açıklama işin neden yapılamadığını
    söyler.
    """
    bulgular = "; ".join(verification.findings)
    parcalar = [f"Plan adımı duraklatıldı: {step_id}.", reason]
    if bulgular:
        parcalar.append(bulgular)
    anlatim = outcome.final_text.strip()
    if anlatim and anlatim not in bulgular:
        parcalar.append(anlatim)
    return " ".join(parca for parca in parcalar if parca)
