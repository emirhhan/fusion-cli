"""Açık kare planını gerçek host taşıması ve mevcut kit kanıtına bağlar."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from ...core.remotion_contract import KitFramePlan as KitFramePlan
from ...core.remotion_contract import KitVerificationPlan as KitVerificationPlan
from ...core.verification import VerificationResult
from ...tools.remotion_observe import RenderedFrame, RenderRequest, observe_frame
from .remotion_contract_verify import (
    ContractRequest,
    RemotionContractVerifier,
    RuntimeObservation,
    SourceFingerprint,
)

FrameTransport = Callable[[RenderRequest], Awaitable[RenderedFrame]]
_LOG = logging.getLogger(__name__)


class _TransportObservation:
    def __init__(self, frame: RenderedFrame) -> None:
        self._frame = frame

    async def observe(self, request: ContractRequest) -> RuntimeObservation:
        frame, runtime = self._frame, self._frame.runtime
        if runtime is None:
            raise ValueError("Gerçek runtime kaydı yok.")
        # Audit ihlali render'ı durdurabilir; böyle bir kayıt FAIL kanıtıdır.
        executed = runtime.runtime_executed and (frame.rendered or bool(runtime.findings))
        return RuntimeObservation(
            runtime.composition,
            runtime.frame,
            runtime.active_scenes,
            runtime.session,
            frame.session_id,
            request.artifact,
            tuple(SourceFingerprint(item.path, item.digest) for item in frame.source_before),
            tuple(SourceFingerprint(item.path, item.digest) for item in frame.source_after),
            executed,
            runtime.timeline_seen,
            runtime.feature_ready,
            runtime.audit_settled,
            runtime.findings,
            runtime.active_scene_kinds,
        )


class RemotionRuntimeVerifier:
    """Yalnız çağıranın açık örnek planını sıralı ölçer; tam video iddiası yapmaz."""

    def __init__(
        self,
        root: Path,
        plan: KitVerificationPlan,
        *,
        transport: FrameTransport = observe_frame,
        new_artifact_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._root, self._plan, self._transport = root, plan, transport
        self._new_artifact_id = new_artifact_id
        self._sessions: set[str] = set()

    async def verify(self) -> VerificationResult:
        try:
            await asyncio.to_thread(_validate_plan, self._root, self._plan)
        except ValueError:
            return await _invalid_plan().verify()
        results = []
        for sample in self._plan.samples:
            results.append(await self._verify_sample(sample))
        return VerificationResult(
            ok=all(result.ok for result in results),
            summary="; ".join(result.summary for result in results),
            findings=tuple(finding for result in results for finding in result.findings),
            evidence=tuple(item for result in results for item in result.evidence),
        )

    async def _verify_sample(self, sample: KitFramePlan) -> VerificationResult:
        plan = self._plan
        artifact_id = self._new_artifact_id()
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", artifact_id):
            return await _invalid_plan(sample, plan.composition_id).verify()
        base = Path(sample.artifact)
        artifact = str(base.with_name(f"{base.stem}-{artifact_id}{base.suffix}"))
        request = RenderRequest(
            self._root,
            plan.entry,
            plan.composition_id,
            sample.frame,
            artifact,
            plan.sources,
            plan.timeout_s,
        )
        try:
            frame = await self._transport(request)
        except Exception:  # Enjekte edilen dış taşıma sınırı; iptal BaseException olarak yayılır.
            _LOG.warning("Remotion runtime taşıması doğrulanamadı", exc_info=True)
            return await _invalid_plan(sample, plan.composition_id).verify()
        if frame.session_id in self._sessions:
            return await _invalid_plan(sample, plan.composition_id).verify()
        self._sessions.add(frame.session_id)
        contract = ContractRequest(
            True,
            plan.composition_id,
            sample.frame,
            sample.scene_id,
            frame.session_id,
            artifact,
            tuple(SourceFingerprint(item.path, item.digest) for item in frame.source_before),
            sample.requires_feature,
        )
        return await RemotionContractVerifier(contract, _TransportObservation(frame)).verify()


def _validate_plan(root: Path, plan: KitVerificationPlan) -> None:
    if not plan.samples or not plan.sources or not plan.composition_id or plan.timeout_s <= 0:
        raise ValueError("Kit örnek planı eksik.")
    artifacts = [sample.artifact for sample in plan.samples]
    if len(set(artifacts)) != len(artifacts):
        raise ValueError("Her kare yeni artefakt yolu gerektirir.")
    for sample in plan.samples:
        if (
            type(sample.frame) is not int
            or sample.frame < 0
            or not sample.scene_id
            or not Path(sample.artifact).name
        ):
            raise ValueError("Kare ve sahne planı geçersiz.")
    for value in (plan.entry, *plan.sources, *artifacts):
        original = Path(value)
        resolved = (root / original).resolve()
        if (
            not value
            or original.is_absolute()
            or ".." in original.parts
            or "\\" in value
            or not resolved.is_relative_to(root.resolve())
            or any(part.startswith(".env") for path in (original, resolved) for part in path.parts)
        ):
            raise ValueError("Kit kaynak ve artefaktları sır içermeyen proje kapsamı olmalı.")


def _invalid_plan(
    sample: KitFramePlan | None = None, composition: str = ""
) -> RemotionContractVerifier:
    request = ContractRequest(
        True,
        composition,
        sample.frame if sample else 0,
        sample.scene_id if sample else "",
        "",
        sample.artifact if sample else "",
        (),
    )
    empty = RenderedFrame("", False, None, (), (), "Plan veya taşıma doğrulanamadı.")
    return RemotionContractVerifier(request, _TransportObservation(empty))
