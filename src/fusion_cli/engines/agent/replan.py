"""Başarısız plan dalını yenilerken doğrulanmış bağımsız işi korur."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from ...core.execution_plan import ExecutionPlan, PlanStatus, PlanStep, StepStatus, validate_plan
from .plan_checkpoint import dependent_ids


def _shape(steps: tuple[PlanStep, ...]) -> str:
    payload = [
        {
            "goal": step.goal,
            "depends_on": step.depends_on,
            "effects": step.expected_effects,
            "criteria": step.success_criteria,
            "checks": [
                (check.kind.value, check.target, check.expected)
                for check in step.verification_checks
            ],
            "phase": step.phase.value,
        }
        for step in steps
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def merge_replanned_plan(
    current: ExecutionPlan,
    candidate: ExecutionPlan,
    failed_step_id: str,
    fingerprint: str,
) -> ExecutionPlan | None:
    """Etkilenen dalı aday planla değiştir; bağımsız teslimatları sakla."""
    affected = dependent_ids(current, {failed_step_id})
    preserved = tuple(
        step
        for step in current.steps
        if step.step_id not in affected
    )
    preserved_ids = {step.step_id for step in preserved}
    replacements = tuple(step for step in candidate.steps if step.step_id not in preserved_ids)
    if not replacements or _shape(
        tuple(s for s in current.steps if s.step_id in affected)
    ) == _shape(replacements):
        return None
    known = preserved_ids | {step.step_id for step in replacements}
    if any(not set(step.depends_on) <= known for step in replacements):
        return None
    old_revision = max(
        (step.revision for step in current.steps if step.step_id in affected), default=0
    )
    revised = tuple(
        replace(
            step,
            status=StepStatus.PENDING,
            attempts=0,
            revision=old_revision + 1,
            last_progress_fingerprint=fingerprint,
        )
        for step in replacements
    )
    merged = ExecutionPlan(
        plan_id=current.plan_id,
        task=current.task,
        steps=(*preserved, *revised),
        status=PlanStatus.RUNNING,
        schema_version=max(current.schema_version, candidate.schema_version, 2),
    )
    return merged if validate_plan(merged).ok else None
