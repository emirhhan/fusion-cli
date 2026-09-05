"""Plan kanıtlarını dosya sürümleriyle bağla ve devamda yeniden ölç."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.checkpoint import ArtifactFingerprint, StepCheckpointEvidence, WorkflowCheckpoint
from ...core.evidence import EvidenceStatus
from ...core.execution_plan import (
    ExecutionPlan,
    PlanStep,
    RetrySafety,
    StepStatus,
    VerificationCheckKind,
)
from .step_verification import StepVerificationResult, evaluate_file_check, verify_step

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome


def replace_step(plan: ExecutionPlan, updated: PlanStep) -> ExecutionPlan:
    """Tek adımı değişmez plan içinde güncelle."""
    return replace(
        plan,
        steps=tuple(updated if step.step_id == updated.step_id else step for step in plan.steps),
    )


def dependent_ids(plan: ExecutionPlan, roots: set[str]) -> set[str]:
    """Geçersiz adımların tüm geçişli bağımlılarını bul."""
    invalid = set(roots)
    while True:
        extended = invalid | {step.step_id for step in plan.steps if set(step.depends_on) & invalid}
        if extended == invalid:
            return invalid
        invalid = extended


def invalidate(plan: ExecutionPlan, roots: set[str]) -> ExecutionPlan:
    """Bozulan dalı aç; yinelenemez geçmiş yan etkileri engelli bırak."""
    invalid = dependent_ids(plan, roots)
    return replace(
        plan,
        steps=tuple(
            replace(
                step,
                status=(
                    StepStatus.BLOCKED
                    if step.retry_safety is RetrySafety.NEVER and step.attempts
                    else StepStatus.PENDING
                ),
            )
            if step.step_id in invalid
            else step
            for step in plan.steps
        ),
    )


def _digest(root: Path, name: str) -> str:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        return ""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


async def capture_evidence(
    step: PlanStep,
    outcome: AgentOutcome,
    verification: StepVerificationResult,
    root: Path,
) -> StepCheckpointEvidence:
    """Yalnız gerçekten ölçülen kanıtı ve araç kaydını sakla."""
    paths = {
        effect.removeprefix("file:").strip()
        for effect in step.expected_effects
        if effect.startswith("file:")
    }
    paths.update(
        check.target
        for check in step.verification_checks
        if check.kind
        in {
            VerificationCheckKind.FILE_EXISTS,
            VerificationCheckKind.FILE_CONTAINS,
        }
    )
    artifacts = tuple(
        [
            ArtifactFingerprint(path, await asyncio.to_thread(_digest, root, path))
            for path in sorted(paths)
        ]
    )
    return StepCheckpointEvidence(
        step.step_id,
        verification.criteria,
        artifacts,
        outcome.tool_uses,
        outcome.tool_calls_made,
        outcome.mutating_tool_calls_made,
        outcome.already_done_calls,
    )


def recorded_outcome(evidence: StepCheckpointEvidence | None) -> AgentOutcome:
    """Önceki gerçek çağrıları taşı; eski checkpoint için sayaç uydurma."""
    from .loop import AgentOutcome

    return AgentOutcome(
        final_text="",
        messages=[],
        tool_uses=evidence.tool_uses if evidence else (),
        tool_calls_made=evidence.tool_calls if evidence else 0,
        mutating_tool_calls_made=evidence.mutation_calls if evidence else 0,
        already_done_calls=evidence.already_done_calls if evidence else 0,
    )


async def artifact_changed(evidence: StepCheckpointEvidence, root: Path) -> bool:
    """Kaydedilmiş dosyalardan biri farklı sürüme geçti mi."""
    for item in evidence.artifacts:
        if not item.digest or await asyncio.to_thread(_digest, root, item.path) != item.digest:
            return True
    return False


async def stale_step_ids(plan: ExecutionPlan, root: Path) -> set[str]:
    """Final bulgusunu metin eşleştirmeden tipli adım kontrolüne bağla."""
    stale = set()
    for step in plan.steps:
        for effect in step.expected_effects:
            if effect.startswith("file:") and not await asyncio.to_thread(
                _digest, root, effect.removeprefix("file:").strip()
            ):
                stale.add(step.step_id)
        for check in step.verification_checks:
            if check.kind in {
                VerificationCheckKind.FILE_EXISTS,
                VerificationCheckKind.FILE_CONTAINS,
            }:
                result = await asyncio.to_thread(evaluate_file_check, check, root)
                if result.status is not EvidenceStatus.PASSED:
                    stale.add(step.step_id)
    return stale


async def resume_plan(
    checkpoint: WorkflowCheckpoint,
    deps: AgentDeps,
) -> tuple[ExecutionPlan, dict[str, StepCheckpointEvidence]]:
    """Bütün tamamlanmış dalları gözle; kanıtsız dış etkiyi tekrar üretme.

    Duraklamanın anlamı "sonra devam"dır, "bir daha asla" değil: bütçe dolunca
    adım `BLOCKED`, tur ortasında kesilince `RUNNING` kalır ve hazır adım seçicisi
    yalnız `PENDING` adımlara bakar. Ölçüldü (Godot koşusu): yeniden açılmayan
    plan kendi checkpoint'inden ilerleyemedi. `COMPLETED` adımlara dokunulmaz;
    onların koşulu burada yeniden ölçülür.
    """
    plan = checkpoint.plan
    evidence = {item.step_id: item for item in checkpoint.step_evidence}
    for original in checkpoint.plan.steps:
        step = next(item for item in plan.steps if item.step_id == original.step_id)
        if step.status is not StepStatus.COMPLETED:
            if step.retry_safety is RetrySafety.NEVER and step.attempts:
                plan = replace_step(plan, replace(step, status=StepStatus.BLOCKED))
            elif step.status is not StepStatus.PENDING:
                plan = replace_step(plan, replace(step, status=StepStatus.PENDING))
            continue
        saved = evidence.get(step.step_id)
        changed = saved is not None and await artifact_changed(saved, deps.tool_context.root)
        checked = await verify_step(step, recorded_outcome(None if changed else saved), deps)
        if (
            changed
            or not checked.ok
            or (checked.unverified and step.retry_safety is not RetrySafety.SAFE)
        ):
            plan = invalidate(plan, {step.step_id})
        else:
            evidence[step.step_id] = await capture_evidence(
                step,
                recorded_outcome(saved),
                checked,
                deps.tool_context.root,
            )
    completed = {step.step_id for step in plan.steps if step.status is StepStatus.COMPLETED}
    return plan, {key: value for key, value in evidence.items() if key in completed}


def dependency_text(step: PlanStep, evidence: dict[str, StepCheckpointEvidence]) -> str:
    """Bağımlılıklara yalnız doğrulanmış koşullar aktarılır; agent beyanı taşınmaz."""
    lines = []
    for dependency in step.depends_on:
        saved = evidence.get(dependency)
        criteria = saved.criteria if saved else ()
        facts = [
            f"{item.criterion_id}: {item.summary}"
            for item in criteria
            if item.status is EvidenceStatus.PASSED
        ]
        # Tipli kontrolü olmayan eski/otomatik planlarda koşul kanıtı boş kalır.
        # Bu durumda bile ÖLÇÜLEN artifact aktarılır: agent beyanı değil, gerçekten
        # diskte bulunan dosyadır; aksi halde sonraki adım kendinden önceki işi
        # görmeden çalışır.
        if not facts:
            facts = [
                f"üretilen dosya: {item.path}"
                for item in (saved.artifacts if saved else ())
                if item.digest
            ]
        lines.append(f"- {dependency}: " + (" | ".join(facts) or "doğrulanmış koşul kanıtı yok"))
    return "\n".join(lines) or "- Yok"
