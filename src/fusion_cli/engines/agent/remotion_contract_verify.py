"""Opt-in kit sözleşmesini taşıma adaptörünün gerçek kare gözlemine bağlar.

Bu modül tarayıcı/render başlatmaz; enjekte edilmiş gözlemciye dayanır. Tek kare
kanıtı tam render veya bütün sahnelerin profesyonelliği kanıtı değildir.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Protocol

from ...core.evidence import CriterionEvidence, EvidenceStatus
from ...core.execution_plan import VerificationCheckKind
from ...core.repair_ledger import FailureEvidence
from ...core.repair_ledger import SourceFingerprint as RepairSource
from ...core.verification import VerificationResult

_LOG = logging.getLogger(__name__)
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class SourceFingerprint:
    """Taşımanın aynı proje kaynaklarını ölçtüğünü gösteren SHA-256 manifest kaydı."""

    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ContractRequest:
    """Çağıran tarafın açık sözleşmesi ve taze oturum için beklediği bağlam."""

    enabled: bool
    composition_id: str
    frame: int
    scene_id: str
    session_id: str
    artifact: str
    sources: tuple[SourceFingerprint, ...]
    requires_feature: bool = True


@dataclass(frozen=True, slots=True)
class RuntimeObservation:
    """Gözlem taşımasının DOM/audit oturumundan aldığı gerçek kare ölçümü."""

    composition_id: str
    frame: int
    active_scenes: tuple[str, ...]
    session_id: str
    observation_id: str
    artifact: str
    source_before: tuple[SourceFingerprint, ...]
    source_after: tuple[SourceFingerprint, ...]
    runtime_executed: bool
    timeline_seen: bool
    feature_ready: bool
    audit_settled: bool
    audit_findings: tuple[str, ...] = ()
    active_scene_kinds: tuple[str, ...] = ()


class RuntimeObserver(Protocol):
    """Taşıma katmanı: statik importtan gerçek DOM gözlemi uydurmaz."""

    async def observe(self, request: ContractRequest) -> RuntimeObservation: ...


class RemotionContractVerifier:
    """Yalnız açık kit sözleşmesini tek kare kapsamında doğrular."""

    def __init__(self, request: ContractRequest, observer: RuntimeObserver) -> None:
        self._request = request
        self._observer = observer
        self._consumed: set[str] = set()

    async def verify(self) -> VerificationResult:
        request = self._request
        if not request.enabled:
            return VerificationResult(ok=True)
        if not _valid_request(request):
            return _result(
                request, EvidenceStatus.UNVERIFIED, "Kit sözleşmesi veya kaynak manifesti geçersiz."
            )
        try:
            observation = await self._observer.observe(request)
        except Exception as error:  # dış gözlemci sınırı; iptal BaseException olarak yayılır
            _LOG.warning("Remotion kare gözlemi alınamadı", exc_info=True)
            return _result(
                request,
                EvidenceStatus.UNVERIFIED,
                f"Kare gözlemi alınamadı ({type(error).__name__}).",
            )
        problem = _context_problem(request, observation)
        if observation.observation_id in self._consumed:
            problem = "Aynı kare gözlemi yeniden kullanıldı; yeni oturum gözlemi gerekli."
        self._consumed.add(observation.observation_id)
        if problem:
            return _result(request, EvidenceStatus.UNVERIFIED, problem)
        if observation.audit_findings:
            result = _result(request, EvidenceStatus.FAILED, " ".join(observation.audit_findings))
            return replace(
                result,
                failure_evidence=(
                    FailureEvidence(
                        f"remotion_kit:{request.composition_id}",
                        "layout_audit",
                        observation.observation_id,
                        tuple(
                            RepairSource(source.path, source.sha256)
                            for source in observation.source_before
                        ),
                    ),
                ),
            )
        if not observation.audit_settled:
            return _result(
                request, EvidenceStatus.UNVERIFIED, "Kare audit ölçümü henüz tamamlanmadı."
            )
        if observation.active_scene_kinds not in (("feature",), ("custom",)):
            return _result(
                request, EvidenceStatus.UNVERIFIED, "Gerçek Timeline sahne türü gözlemlenmedi."
            )
        if request.requires_feature and observation.active_scene_kinds != ("feature",):
            return _result(
                request,
                EvidenceStatus.UNVERIFIED,
                "Custom sahnedeki marker FeatureScene çalışma kanıtı değildir.",
            )
        if request.requires_feature and not observation.feature_ready:
            return _result(
                request,
                EvidenceStatus.UNVERIFIED,
                "Gerçek FeatureScene kapasite işareti gözlemlenmedi.",
            )
        return _result(
            request, EvidenceStatus.PASSED, "Timeline ve istenen sahne gerçek karede gözlemlendi."
        )


def _valid_manifest(sources: tuple[SourceFingerprint, ...]) -> bool:
    paths = [source.path for source in sources]
    return (
        bool(sources)
        and len(paths) == len(set(paths))
        and all(
            source.path
            and not PurePosixPath(source.path).is_absolute()
            and ".." not in PurePosixPath(source.path).parts
            and "\\" not in source.path
            and _SHA256.fullmatch(source.sha256)
            for source in sources
        )
    )


def _valid_request(request: ContractRequest) -> bool:
    return bool(
        request.composition_id and request.scene_id and request.session_id and request.artifact
    ) and (type(request.frame) is int and request.frame >= 0 and _valid_manifest(request.sources))


def _context_problem(request: ContractRequest, observation: RuntimeObservation) -> str:
    if not observation.runtime_executed or not observation.timeline_seen:
        return "Statik/import işareti gerçek Timeline çalışma kanıtı değildir."
    if not observation.observation_id or (
        observation.composition_id != request.composition_id
        or observation.frame != request.frame
        or observation.session_id != request.session_id
        or observation.artifact != request.artifact
        or observation.active_scenes != (request.scene_id,)
    ):
        return "Kare/composition/sahne/oturum/artefakt gözlemi istenen bağlamla eşleşmiyor."
    if not _valid_manifest(observation.source_before) or not _valid_manifest(
        observation.source_after
    ):
        return "Gözlemin kaynak manifesti eksik veya geçersiz."
    expected = frozenset(request.sources)
    if (
        frozenset(observation.source_before) != expected
        or frozenset(observation.source_after) != expected
    ):
        return "Gözlem öncesi/sonrası kaynak hashleri beklenen kaynakla eşleşmiyor; kanıt eskidi."
    return ""


def _result(request: ContractRequest, status: EvidenceStatus, detail: str) -> VerificationResult:
    summary = f"Tek kare kit kanıtı ({request.composition_id}, kare {request.frame}): {detail} "
    summary += "Bu kanıt tam video render'ını veya diğer kareleri doğrulamaz."
    evidence = CriterionEvidence(
        criterion_id=f"remotion_kit:{request.composition_id}:{request.frame}:{request.scene_id}",
        kind=VerificationCheckKind.TOOL,
        status=status,
        summary=summary,
        artifact=request.artifact,
        command="remotion_runtime_observation",
        output=detail,
        behavioral=status is not EvidenceStatus.UNVERIFIED,
    )
    return VerificationResult(
        ok=status is EvidenceStatus.PASSED,
        summary=summary,
        findings=() if status is EvidenceStatus.PASSED else (detail,),
        evidence=(evidence,),
    )
