"""Kapanışta geç host sözleşmesini ve değişmez paket kiti gerçek kapıya bağlar."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...core.evidence import CriterionEvidence, EvidenceStatus
from ...core.execution_plan import VerificationCheckKind
from ...core.remotion_contract import KitContractSnapshot, KitContractState
from ...core.verification import VerificationResult
from ...tools.remotion_contract_check import check_packaged as _check_packaged
from ...tools.remotion_contract_check import project_root as _project_root
from ...tools.remotion_observe import RenderedFrame, RenderRequest, observe_frame
from .remotion_bridge import FrameTransport, RemotionRuntimeVerifier


class DeferredRemotionVerifier:
    """Genel projede no-op; yalnız açık araç/plan kaydı bu kapıyı etkinleştirir."""

    def __init__(
        self, root: Path, state: KitContractState, *, transport: FrameTransport = observe_frame
    ) -> None:
        self._root, self._state, self._transport = root, state, transport
        self._runtime: RemotionRuntimeVerifier | None = None
        self._cached_contract: KitContractSnapshot | None = None
        self._sessions: set[str] = set()

    async def verify(self) -> VerificationResult:
        snapshot = self._state.snapshot()
        contract = snapshot.registered
        if contract is None:
            if not self._state.is_required:
                return VerificationResult(ok=True)
            return _result(
                EvidenceStatus.UNVERIFIED,
                "Açık Fusion kit planı var; scaffold_remotion host kaydı eksik.",
            )
        try:
            root = await asyncio.to_thread(_project_root, self._root, contract.project_dir)
            await asyncio.to_thread(_check_packaged, root, contract)
        except OSError:
            return _result(EvidenceStatus.UNVERIFIED, "Paket kit kaynakları okunamadı.")
        except ValueError as error:
            return _result(EvidenceStatus.FAILED, str(error))
        if self._runtime is None or self._cached_contract != snapshot:
            self._runtime = RemotionRuntimeVerifier(root, contract.plan, transport=self._observe)
            self._cached_contract = snapshot
        measured = await self._runtime.verify()
        try:
            await asyncio.to_thread(_check_packaged, root, contract)
        except (OSError, ValueError):
            # Eski başarılı kareleri yeni/bozuk kit üzerinde başarı gibi taşımıyoruz.
            return _result(
                EvidenceStatus.FAILED, "Gözlem sırasında paket kit değişti; kare kanıtı geçersiz."
            )
        if self._state.snapshot() != snapshot:
            return _result(
                EvidenceStatus.UNVERIFIED,
                "Gözlem sırasında host sahne revizyonu değişti; taze kare kanıtı gerekli.",
            )
        return measured

    async def _observe(self, request: RenderRequest) -> RenderedFrame:
        """Plan değişmesi önceki gerçek oturum receipt'ini yeniden taze yapmaz."""
        frame = await self._transport(request)
        if frame.session_id in self._sessions:
            raise ValueError("Önceki revizyonun kare oturumu yeniden kullanılamaz.")
        self._sessions.add(frame.session_id)
        return frame


def _result(status: EvidenceStatus, detail: str) -> VerificationResult:
    evidence = CriterionEvidence(
        criterion_id="remotion_kit:host_contract",
        kind=VerificationCheckKind.TOOL,
        status=status,
        summary=detail,
        command="remotion_host_contract",
        output=detail,
        behavioral=False,
    )
    return VerificationResult(ok=False, summary=detail, findings=(detail,), evidence=(evidence,))
