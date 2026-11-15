"""Başarı koşullarını gözlenebilir kanıta bağlayan çekirdek türler."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .job_evidence import JobCompletion
from .workspace_fingerprint import WorkspaceEffect

if TYPE_CHECKING:
    from .execution_plan import VerificationCheckKind


@dataclass(frozen=True, slots=True)
class EvidenceEnvironment:
    """Kanıtın komut, çalışma kökü, koşucu ve dosya özeti kimliği."""

    command: str
    cwd: str
    runtime: str
    dependency_digest: str
    config_digest: str


@runtime_checkable
class EvidenceEnvironmentSource(Protocol):
    """Kapının o anda ölçülebilen ortam kimliğini sağlar."""

    def evidence_environment(self) -> EvidenceEnvironment | None: ...


class EvidenceStatus(StrEnum):
    """Tek bir başarı koşulunun doğrulanma durumu."""

    PASSED = "passed"
    FAILED = "failed"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class CriterionEvidence:
    """Bir plan koşulu için üretilen sınırlı ve tipli kanıt."""

    criterion_id: str
    kind: VerificationCheckKind
    status: EvidenceStatus
    summary: str
    artifact: str = ""
    command: str = ""
    output: str = ""
    #: Kanıt işin ÇALIŞTIĞINI mı gösteriyor, yoksa yalnız biçimini mi (sözdizimi)?
    #:
    #: Ölçüldü (2 Ekim): `php -l` temiz geçince rapor "✓ Doğrulandı" diyordu; tema
    #: zorunlu `index.php`'si olmadığı için WordPress'te hiç açılmıyordu. Sözdizimi
    #: kanıtı tek başına "doğrulandı" saydırmaz.
    behavioral: bool = True
    source_digest: str = ""
    source_after_digest: str = ""
    environment: EvidenceEnvironment | None = None
    call_id: str = ""
    #: Kapsam dışı kontrol doğrulanmış başarı sayılmaz.
    applicable: bool = True
    step_id: str = ""
    #: Aynı kriterdeki kontrollerin mevcut hedef/beklenti referansı; yeni kimlik üretmez.
    check_target: str = ""
    check_expected: str = ""


@dataclass(frozen=True, slots=True)
class ToolUse:
    """Turda denenen tek araç çağrısı."""

    name: str
    ok: bool = True
    mutating: bool = False
    arguments: Mapping[str, object] = field(default_factory=dict)
    output: str = ""
    job_completion: JobCompletion | None = None
    #: `run_shell` için proje kökünde ÖLÇÜLEN etki (bkz. `core.workspace_fingerprint`).
    #: `None` = ölçülmedi: komut metnine bakan temkinli sınıflandırma geçerlidir.
    workspace_effect: WorkspaceEffect | None = None
    source_digest: str = ""
    source_after_digest: str = ""
    environment: EvidenceEnvironment | None = None
    call_id: str = ""


def summarize_criteria(evidence: Sequence[CriterionEvidence]) -> tuple[CriterionEvidence, ...]:
    """Kontrol ayrıntılarını tüketmeden istemci için kriterin en zayıf sonucunu seç."""
    latest: dict[tuple[str, str, VerificationCheckKind, str, str], CriterionEvidence] = {}
    unbound: list[CriterionEvidence] = []
    for item in evidence:
        target = item.check_target or item.command or item.artifact
        if not target:
            unbound.append(item)
            continue
        key = (item.step_id, item.criterion_id, item.kind, target, item.check_expected)
        latest[key] = item
    grouped: dict[tuple[str, str], list[CriterionEvidence]] = {
        (item.step_id, item.criterion_id): [] for item in evidence
    }
    for item in (*latest.values(), *unbound):
        grouped.setdefault((item.step_id, item.criterion_id), []).append(item)
    results: list[CriterionEvidence] = []
    for checked in grouped.values():
        failed = next((item for item in checked if item.status is EvidenceStatus.FAILED), None)
        unverified = next(
            (item for item in checked if item.status is EvidenceStatus.UNVERIFIED), None
        )
        results.append(failed or unverified or checked[-1])
    return tuple(results)
