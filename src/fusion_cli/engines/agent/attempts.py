"""Paralel deneme adayları arasından KANITLA seçim.

Test-time scaling'in ölçülmüş biçimi şudur: aynı işi birkaç kez dene, sonra
kazananı yürütme kanıtıyla seç. Agentless'ın seçim aşaması da reprodüksiyon testi,
regresyon ve oy kullanır; model beyanı ("düzelttim") ölçüt değildir.

Seçim kuralları sırayla:

1. Başarısız (`FAILED`) kanıt üreten aday elenir — bir koşulu bozduğu KANITLI.
2. Kalanlar arasında en çok `PASSED` kanıtı olan kazanır.
3. Eşitlikte daha az model çağrısı harcayan kazanır: aynı kanıt daha ucuza.
4. Hiçbir aday doğrulanmış kanıt üretmediyse KAZANAN YOKTUR. Yanlış adayı
   uygulamak, hiç denememekten kötüdür.

Saf ve test edilebilirdir: dosya, ağ, süreç bilmez.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from ...core.events import (
    Event,
    EventPublisher,
    ModelCallAbandoned,
    ModelCallFinished,
    ModelCallStarted,
)
from ...core.evidence import CriterionEvidence, EvidenceStatus
from ...core.types import ModelSpec, is_permanent_error


@dataclass(frozen=True, slots=True)
class Attempt:
    """Bir denemenin sonucu ve ürettiği kanıt."""

    name: str
    ok: bool = True
    criteria: tuple[CriterionEvidence, ...] = field(default_factory=tuple)
    model_calls: int = 0

    @property
    def passed(self) -> int:
        return sum(1 for item in self.criteria if item.status is EvidenceStatus.PASSED)

    @property
    def failed(self) -> int:
        return sum(1 for item in self.criteria if item.status is EvidenceStatus.FAILED)


def choose_attempt(attempts: Sequence[Attempt]) -> Attempt | None:
    """Kanıta göre kazananı seç; kanıt yoksa `None`."""
    uygun = [item for item in attempts if item.ok and item.passed and not item.failed]
    if not uygun:
        return None
    return min(uygun, key=lambda item: (-item.passed, item.model_calls, item.name))


@dataclass(frozen=True, slots=True)
class AttemptExperiment:
    """Aynı model ve toplam çağrı tavanı olan iki önceden belirli deney kolu."""

    arm: Literal["candidates", "serial"]
    total_calls: int
    first_slot_calls: int
    requested_spec: ModelSpec
    task_id: str
    repeat: int = 1

    def __post_init__(self) -> None:
        if self.arm not in {"candidates", "serial"}:
            raise ValueError("Geçersiz deney kolu.")
        if not 0 < self.first_slot_calls < self.total_calls or self.repeat < 1:
            raise ValueError("İki aday için pozitif, sabit çağrı payları gerekli.")
        if not self.requested_spec.strict or self.requested_spec.fallback:
            raise ValueError("Deney tek strict model ve boş yedek zinciri gerektirir.")

    @property
    def slot_limits(self) -> tuple[int, int]:
        """İlk adayın kullanmadığı hak ikinci adaya aktarılmaz."""
        return self.first_slot_calls, self.total_calls - self.first_slot_calls


@dataclass(slots=True)
class InvocationBudget:
    """Dış provider invocation hakkını çağrıdan önce tüketen ortak sayaç."""

    limit: int
    used: int = 0
    parent: InvocationBudget | None = None
    requested_spec: ModelSpec | None = None

    @property
    def remaining(self) -> int:
        return (
            min(max(0, self.limit - self.used), self.parent.remaining)
            if self.parent
            else max(0, self.limit - self.used)
        )

    def claim(self, spec: ModelSpec | None = None) -> bool:
        """Sonuçsuz/iptal edilmiş çağrı da harcanmış hak olarak kalır."""
        if self.remaining == 0 or (self.requested_spec is not None and spec != self.requested_spec):
            return False
        if self.parent is not None and not self.parent.claim(spec):
            return False
        self.used += 1
        return True


class CandidatePublisher:
    """Kök turn kimliğini koru; tüm aday olaylarını ve gerçek çağrı kimliklerini bağla."""

    def __init__(self, inner: EventPublisher, candidate_id: str) -> None:
        self.inner = inner
        self.candidate_id = candidate_id
        self.call_ids: list[str] = []

    def publish(self, event: Event) -> None:
        if (
            isinstance(event, ModelCallStarted)
            and event.call_id
            and event.call_id not in self.call_ids
        ):
            self.call_ids.append(event.call_id)
        self.inner.publish(replace(event, candidate_id=self.candidate_id))


class ExperimentPublisher:
    """Gerçek yaşam döngüsü sayısını ve son sağlayıcı belirsizliğini izle."""

    def __init__(self, inner: EventPublisher) -> None:
        self.inner = inner
        self.call_ids: set[str] = set()
        self.is_unavailable = False

    def publish(self, event: Event) -> None:
        if (
            isinstance(event, (ModelCallStarted, ModelCallFinished, ModelCallAbandoned))
            and event.call_id
        ):
            self.call_ids.add(event.call_id)
        if isinstance(event, ModelCallFinished):
            self.is_unavailable = not event.result.ok and (
                event.result.is_rate_limited or is_permanent_error(event.result.error)
            )
        elif isinstance(event, ModelCallAbandoned):
            self.is_unavailable = True
        self.inner.publish(event)
