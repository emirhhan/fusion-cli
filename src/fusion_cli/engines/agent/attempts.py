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
from dataclasses import dataclass, field

from ...core.evidence import CriterionEvidence, EvidenceStatus


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
