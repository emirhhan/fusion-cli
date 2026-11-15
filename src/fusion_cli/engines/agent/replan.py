"""Başarısız plan dalını yenilerken doğrulanmış bağımsız işi korur."""

from __future__ import annotations

import hashlib
import json
import re
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


#: Hedef metinleri bu benzerlik eşiğinden yakınsa "kelime değiştirerek yeniden yazılmış
#: aynı plan"dır (A3-15).
_NEAR_DUPLICATE_JACCARD = 0.9
_WORD = re.compile(r"\w+", re.UNICODE)


def _fold(text: str) -> str:
    """Türkçe büyük/küçük harf (I/ı, İ/i) farkını eşitleyerek küçült."""
    return text.replace("I", "ı").replace("İ", "i").lower()


def _jaccard(left: str, right: str) -> float:
    a = set(_WORD.findall(_fold(left)))
    b = set(_WORD.findall(_fold(right)))
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _checks(step: PlanStep) -> tuple[tuple[str, str, str], ...]:
    return tuple((c.kind.value, c.target, c.expected) for c in step.verification_checks)


def _near_duplicate(old: tuple[PlanStep, ...], new: tuple[PlanStep, ...]) -> bool:
    """Aynı etkiler ve kontroller, neredeyse aynı hedef metni: kör tekrar.

    Ölçüldü (30 Ekim, A3-15): `_shape` hedef metnini de özetlediği için model
    hedefi yalnız birkaç kelime değiştirip yeniden yazınca "farklı" sayılıyor ve
    kör tekrar kabul ediliyordu.
    """
    return len(old) == len(new) and all(
        a.expected_effects == b.expected_effects
        and _checks(a) == _checks(b)
        and _jaccard(a.goal, b.goal) >= _NEAR_DUPLICATE_JACCARD
        for a, b in zip(old, new, strict=True)
    )


def _file_effects(steps: tuple[PlanStep, ...]) -> set[str]:
    return {
        effect.removeprefix("file:").strip().removeprefix("./")
        for step in steps
        for effect in step.expected_effects
        if effect.startswith("file:")
    }


def merge_replanned_plan(
    current: ExecutionPlan,
    candidate: ExecutionPlan,
    failed_step_id: str,
    fingerprint: str,
) -> ExecutionPlan | None:
    """Etkilenen dalı aday planla değiştir; bağımsız teslimatları sakla."""
    affected = dependent_ids(current, {failed_step_id})
    preserved = tuple(step for step in current.steps if step.step_id not in affected)
    preserved_ids = {step.step_id for step in preserved}
    replacements = tuple(step for step in candidate.steps if step.step_id not in preserved_ids)
    old = tuple(s for s in current.steps if s.step_id in affected)
    if (
        not replacements
        or _shape(old) == _shape(replacements)
        or _near_duplicate(old, replacements)
    ):
        return None
    # Etkilenen dalın BAĞIMLI adımlarının dosya teslimatları yeni dalda hâlâ
    # bulunmalı (A3-15). Başarısız adımın kendi hedefi serbestçe değişebilir (yanlış
    # yola yönelmiş olabilir); ama ona bağlı adımların teslimatını sessizce düşüren
    # aday, kullanıcının istediği işi kaybeder.
    dependents = tuple(s for s in old if s.step_id != failed_step_id)
    if not _file_effects(dependents) <= _file_effects(replacements):
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
