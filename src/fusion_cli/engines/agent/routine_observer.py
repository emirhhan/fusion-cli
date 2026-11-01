"""Gerçek plan yürütmesinin taze önkoşul ve final ölçümlerini biriktir."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.checkpoint import StepCheckpointEvidence
from ...core.evidence import EvidenceStatus
from ...core.execution_plan import ExecutionPlan, PlanStep, StepStatus
from ...core.lesson_runtime import LessonUse
from ...core.memory import RoutineObservation, RoutineSpec
from ...core.task_protocol import args_digest
from ...core.verification import VerificationResult
from ..routine_source import routine_spec
from .lesson_attribution import LessonTurnState
from .plan_checkpoint import _digest, artifact_changed
from .step_verification import evaluate_file_check

if TYPE_CHECKING:
    from .loop import AgentDeps


@dataclass(frozen=True, slots=True)
class RoutineStart:
    """Yürütmeden önce gerçekten ölçülen kaynak ve önkoşullar."""

    routine: RoutineSpec
    attempts: tuple[tuple[str, int], ...]
    evidence_refs: tuple[str, ...]


async def begin_routine(plan: ExecutionPlan, deps: AgentDeps) -> RoutineStart | None:
    """Eksik tanım/kimlik veya başarısız önkoşulda öneri gözlemi açma."""
    if plan.routine is None:
        return None
    if not deps.config.runtime.verified_skill_proposals or not deps.attempt_id:
        return None
    spec = await asyncio.to_thread(routine_spec, plan, deps.tool_context.root)
    if spec is None:
        return None
    refs = []
    for step in plan.steps:
        for check in step.verification_checks:
            if check.criterion_id not in spec.preconditions:
                continue
            result = await asyncio.to_thread(evaluate_file_check, check, deps.tool_context.root)
            digest = await asyncio.to_thread(_digest, deps.tool_context.root, check.target)
            if not result.applicable or result.status is not EvidenceStatus.PASSED or not digest:
                return None
            refs.append(
                args_digest(
                    {
                        "attempt": deps.attempt_id,
                        "phase": "before",
                        "criterion": check.criterion_id,
                        "source": digest,
                    }
                )
            )
    return RoutineStart(
        spec, tuple((step.step_id, step.attempts) for step in plan.steps), tuple(refs)
    )


async def stage_routine(
    start: RoutineStart | None,
    plan: ExecutionPlan,
    deps: AgentDeps,
    *,
    acceptance: VerificationResult,
    evidence: tuple[StepCheckpointEvidence, ...],
) -> None:
    """Final kapıdan sonra, kök Stop kapanışından önce kanıtı sıraya al."""
    if start is None or not acceptance.ok or acceptance.failure_evidence or not deps.attempt_id:
        return
    spec = await asyncio.to_thread(routine_spec, plan, deps.tool_context.root)
    if spec != start.routine:
        return
    before = dict(start.attempts)
    if any(
        step.status is not StepStatus.COMPLETED or step.attempts <= before[step.step_id]
        for step in plan.steps
    ):
        return
    refs = list(start.evidence_refs)
    for step in plan.steps:
        saved = next((item for item in evidence if item.step_id == step.step_id), None)
        current_refs = await _step_refs(step, saved, deps)
        if not current_refs:
            return
        refs.extend(current_refs)
    if deps.lesson_state is None:
        deps.lesson_state = LessonTurnState()
    observation = RoutineObservation(
        deps.attempt_id, True, True, tuple(refs), deps.lesson_context.policy.source_split
    )
    deps.lesson_state.routines.append((start.routine, observation))
    deps.lesson_state.routine_proofs[start.routine.source_digest] = RoutineProof(plan, evidence)
    await _bind_lessons(start.routine, deps, evidence)


async def _bind_lessons(
    spec: RoutineSpec, deps: AgentDeps, evidence: tuple[StepCheckpointEvidence, ...]
) -> None:
    """Depoda doğrulanmış aynı kaynak bağı olmayan prose kullanılmış sayılmaz."""
    if deps.skill_proposals is None or deps.lesson_state is None:
        return
    from ...memory.skill_proposals import SkillProposalError

    try:
        proposals = await deps.skill_proposals.list(
            source_split=deps.lesson_context.policy.source_split
        )
    except (SkillProposalError, OSError):
        logging.getLogger(__name__).warning("Rutin ders bağı okunamadı.", exc_info=True)
        return
    if not any(item.routine == spec for item in proposals):
        return
    for lesson in deps.lesson_state.offered.values():
        if spec.source_digest not in lesson.evidence_refs:
            continue
        deps.lesson_state.uses[lesson.id] = LessonUse(
            lesson.id,
            spec.routine_id,
            spec.source_digest,
            spec.checks,
            tuple(use.call_id for saved in evidence for use in saved.tool_uses if use.call_id),
        )


@dataclass(frozen=True, slots=True)
class RoutineProof:
    """Stop sonrası kapanışta bayat dosya kanıtını tekrar sınamak için mevcut snapshot."""

    plan: ExecutionPlan
    evidence: tuple[StepCheckpointEvidence, ...]


async def _step_refs(
    step: PlanStep,
    saved: StepCheckpointEvidence | None,
    deps: AgentDeps,
) -> tuple[str, ...]:
    """Aynı adım/hedef/beklenti ve güncel artifact için ölçüm referansları."""
    if (
        saved is None
        or not any(use.ok and use.call_id for use in saved.tool_uses)
        or await artifact_changed(saved, deps.tool_context.root)
    ):
        return ()
    refs = []
    for check in step.verification_checks:
        current = await asyncio.to_thread(evaluate_file_check, check, deps.tool_context.root)
        matched = [
            item
            for item in saved.criteria
            if item.criterion_id == check.criterion_id
            and item.kind == check.kind
            and item.step_id == step.step_id
            and item.check_target == check.target
            and item.check_expected == check.expected
        ]
        if (
            not matched
            or any(
                item.status is not EvidenceStatus.PASSED or not item.applicable for item in matched
            )
            or current.status is not EvidenceStatus.PASSED
        ):
            return ()
        digest = await asyncio.to_thread(_digest, deps.tool_context.root, check.target)
        if not digest:
            return ()
        refs.append(
            args_digest(
                {
                    "attempt": deps.attempt_id,
                    "phase": "after",
                    "criterion": check.criterion_id,
                    "source": digest,
                    "calls": [use.call_id for use in saved.tool_uses if use.call_id],
                }
            )
        )
    return tuple(refs)


async def refresh_routines(deps: AgentDeps) -> None:
    """Stop devamında değişen dosyalar eski başarılı gözlemi geçersiz kılar."""
    state = deps.lesson_state
    if state is None:
        return
    valid = []
    for spec, observation in state.routines:
        proof = state.routine_proofs.get(spec.source_digest)
        if (
            proof is None
            or await asyncio.to_thread(routine_spec, proof.plan, deps.tool_context.root) != spec
        ):
            continue
        fresh = True
        for step in proof.plan.steps:
            saved = next((item for item in proof.evidence if item.step_id == step.step_id), None)
            if not await _step_refs(step, saved, deps):
                fresh = False
                break
        if fresh:
            valid.append((spec, observation))
    state.routines = valid
