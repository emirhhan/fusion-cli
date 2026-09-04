"""Doğrulanabilir yürütme planının çekirdek veri modeli."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlanStatus(StrEnum):
    """Bir yürütme planının yaşam döngüsü durumu."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"


class StepStatus(StrEnum):
    """Tek bir plan adımının yürütme durumu."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class RetrySafety(StrEnum):
    """Başarısız bir adımın hangi koşulda yeniden çalıştırılabileceği."""

    SAFE = "safe"
    OBSERVE_FIRST = "observe_first"
    NEVER = "never"


@dataclass(frozen=True)
class PlanStep:
    """Araç sınırları ve başarı kanıtı tanımlanmış atomik iş adımı."""

    step_id: str
    goal: str
    depends_on: tuple[str, ...]
    expected_effects: tuple[str, ...]
    allowed_tool_families: tuple[str, ...]
    success_criteria: tuple[str, ...]
    verification_hint: str
    retry_safety: RetrySafety
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0


@dataclass(frozen=True)
class ExecutionPlan:
    """Bağımlılık grafiği biçimindeki sürümlü yürütme planı."""

    plan_id: str
    task: str
    steps: tuple[PlanStep, ...]
    status: PlanStatus = PlanStatus.PENDING
    schema_version: int = 1


@dataclass(frozen=True)
class PlanValidation:
    """Plan doğrulamasının makinece tüketilebilir sonucu."""

    ok: bool
    errors: tuple[str, ...]


def _find_cycle(steps: tuple[PlanStep, ...]) -> tuple[str, ...] | None:
    """Bağımlılık grafiğindeki ilk döngüyü plan sırasına göre bul."""
    graph = {step.step_id: step.depends_on for step in steps}
    visited: set[str] = set()
    active: list[str] = []

    def visit(step_id: str) -> tuple[str, ...] | None:
        if step_id in active:
            start = active.index(step_id)
            return (*active[start:], step_id)
        if step_id in visited:
            return None
        active.append(step_id)
        for dependency in graph.get(step_id, ()):
            if dependency in graph:
                cycle = visit(dependency)
                if cycle is not None:
                    return cycle
        active.pop()
        visited.add(step_id)
        return None

    for step in steps:
        cycle = visit(step.step_id)
        if cycle is not None:
            return cycle
    return None


def validate_plan(plan: ExecutionPlan) -> PlanValidation:
    """Planın temel alanlarını ve yönsüz olmayan bağımlılık grafiğini doğrula."""
    errors: list[str] = []
    known_ids: set[str] = set()

    for step in plan.steps:
        if step.step_id in known_ids:
            errors.append(f"Plan adımı kimliği yineleniyor: {step.step_id}")
        known_ids.add(step.step_id)
        if not step.goal.strip():
            errors.append(f"Plan adımı '{step.step_id}' boş hedef içeriyor.")
        if not step.success_criteria or any(not item.strip() for item in step.success_criteria):
            errors.append(
                f"Plan adımı '{step.step_id}' doğrulanabilir başarı koşulu içermiyor."
            )

    for step in plan.steps:
        for dependency in step.depends_on:
            if dependency not in known_ids:
                errors.append(
                    f"Plan adımı '{step.step_id}' bilinmeyen bağımlılık içeriyor: "
                    f"{dependency}"
                )

    if not errors:
        cycle = _find_cycle(plan.steps)
        if cycle is not None:
            errors.append(f"Plan bağımlılık döngüsü içeriyor: {' → '.join(cycle)}")

    return PlanValidation(ok=not errors, errors=tuple(errors))


def ready_steps(plan: ExecutionPlan) -> tuple[PlanStep, ...]:
    """Bütün bağımlılıkları tamamlanmış bekleyen adımları plan sırasında döndür."""
    completed = {
        step.step_id for step in plan.steps if step.status is StepStatus.COMPLETED
    }
    return tuple(
        step
        for step in plan.steps
        if step.status is StepStatus.PENDING and set(step.depends_on) <= completed
    )
