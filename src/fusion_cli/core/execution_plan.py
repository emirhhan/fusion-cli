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


class PlanPhase(StrEnum):
    """Plan adımının bilgi toplama mı, değişiklik üretme mi yaptığını belirtir."""

    DISCOVERY = "discovery"
    EXECUTION = "execution"


class VerificationCheckKind(StrEnum):
    """Güvenli ve makinece uygulanabilir kontrol türleri."""

    FILE_EXISTS = "file_exists"
    FILE_CONTAINS = "file_contains"
    COMMAND = "command"
    TOOL = "tool"
    #: Hatayı gösteren test: ÖNCE kırmızı, SONRA yeşil olmalı.
    #:
    #: Yalnız "şimdi geçiyor" demek, testin hatayı hiç yakalamadığı durumu gizler
    #: (fail-to-fail) ve yanlış başarının en yaygın kaynağıdır.
    REPRODUCTION = "reproduction"


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    """Bir başarı koşulunu güvenli ve tipli bir gözleme bağlar."""

    criterion_id: str
    kind: VerificationCheckKind
    target: str
    expected: str = ""


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
    verification_checks: tuple[VerificationCheck, ...] = ()
    phase: PlanPhase = PlanPhase.EXECUTION
    revision: int = 0
    last_progress_fingerprint: str = ""


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


#: Dosya durumunu ölçen kontrol türleri.
_FILE_CHECKS = frozenset({VerificationCheckKind.FILE_EXISTS, VerificationCheckKind.FILE_CONTAINS})


def _declared_files(step: PlanStep) -> tuple[str, ...]:
    """Adımın ÜRETMEYİ vaat ettiği dosya yolları."""
    return tuple(
        effect.removeprefix("file:").strip()
        for effect in step.expected_effects
        if effect.startswith("file:")
    )


def _target_conflicts(step: PlanStep, check: VerificationCheck) -> tuple[str, ...]:
    """Adımın vaat ettiği yol ile ölçülen yol çelişiyor mu.

    Ölçüldü (7 Eylül canlı Godot koşusu, `game-manager-eksiklerini-tamamla`):
    beklenen etki bir yolu, kontrol başka bir yolu gösteriyordu. Adım hangisini
    üretirse üretsin öteki düşüyordu ve hiçbir deneme bunu düzeltemezdi.

    Vaat HİÇ yoksa çelişki de yok: mevcut bir dosyayı düzenleyen adım `file:`
    etkisi bildirmek zorunda değildir. Çelişki yalnız İKİ farklı yol iddia
    edildiğinde doğar ve düzeltmesi planlayıcıya aittir.
    """
    if check.kind not in _FILE_CHECKS:
        return ()
    declared = _declared_files(step)
    if not declared or check.target.strip() in declared:
        return ()
    return (
        f"Plan adımı '{step.step_id}' iki farklı dosya yolu iddia ediyor: "
        f"beklenen etki {', '.join(declared)}, kontrol hedefi {check.target}. "
        "İkisi aynı yolu göstermeli.",
    )


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
            errors.append(f"Plan adımı '{step.step_id}' doğrulanabilir başarı koşulu içermiyor.")
        if step.phase is PlanPhase.DISCOVERY and _declared_files(step):
            errors.append(
                f"Keşif adımı '{step.step_id}' henüz bilinmeyen bir dosyayı üretmeyi vaat edemez; "
                "önce gerçek yolu bulmalı, dosya üretimini yürütme adımına bırakmalıdır."
            )
        criteria = set(step.success_criteria)
        for check in step.verification_checks:
            if check.criterion_id not in criteria:
                errors.append(
                    f"Plan adımı '{step.step_id}' bilinmeyen başarı koşuluna "
                    f"kontrol bağlıyor: {check.criterion_id}"
                )
            if not check.target.strip():
                errors.append(f"Plan adımı '{step.step_id}' boş doğrulama hedefi içeriyor.")
            errors.extend(_target_conflicts(step, check))
            if (
                check.kind
                in {
                    VerificationCheckKind.FILE_CONTAINS,
                    VerificationCheckKind.TOOL,
                }
                and not check.expected
            ):
                errors.append(
                    f"Plan adımı '{step.step_id}' doğrulama kontrolünde "
                    "beklenen değeri belirtmiyor."
                )

    for step in plan.steps:
        for dependency in step.depends_on:
            if dependency not in known_ids:
                errors.append(
                    f"Plan adımı '{step.step_id}' bilinmeyen bağımlılık içeriyor: {dependency}"
                )

    if not errors:
        cycle = _find_cycle(plan.steps)
        if cycle is not None:
            errors.append(f"Plan bağımlılık döngüsü içeriyor: {' → '.join(cycle)}")

    return PlanValidation(ok=not errors, errors=tuple(errors))


def ready_steps(plan: ExecutionPlan) -> tuple[PlanStep, ...]:
    """Bütün bağımlılıkları tamamlanmış bekleyen adımları plan sırasında döndür."""
    completed = {step.step_id for step in plan.steps if step.status is StepStatus.COMPLETED}
    return tuple(
        step
        for step in plan.steps
        if step.status is StepStatus.PENDING and set(step.depends_on) <= completed
    )
