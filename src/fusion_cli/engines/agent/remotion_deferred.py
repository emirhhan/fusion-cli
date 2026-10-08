"""Kapanışta geç host sözleşmesini ve değişmez paket kiti gerçek kapıya bağlar."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from ...core.evidence import CriterionEvidence, EvidenceStatus
from ...core.execution_plan import VerificationCheckKind
from ...core.remotion_contract import KitContractState, RegisteredKitContract
from ...core.verification import VerificationResult
from ...tools.remotion_observe import observe_frame
from ...tools.remotion_scaffold import check_kit_shadow
from .remotion_bridge import FrameTransport, RemotionRuntimeVerifier


class DeferredRemotionVerifier:
    """Genel projede no-op; yalnız açık araç/plan kaydı bu kapıyı etkinleştirir."""

    def __init__(
        self, root: Path, state: KitContractState, *, transport: FrameTransport = observe_frame
    ) -> None:
        self._root, self._state, self._transport = root, state, transport
        self._runtime: RemotionRuntimeVerifier | None = None

    async def verify(self) -> VerificationResult:
        contract = self._state.registered
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
        if self._runtime is None:
            self._runtime = RemotionRuntimeVerifier(root, contract.plan, transport=self._transport)
        measured = await self._runtime.verify()
        try:
            await asyncio.to_thread(_check_packaged, root, contract)
        except (OSError, ValueError):
            # Eski başarılı kareleri yeni/bozuk kit üzerinde başarı gibi taşımıyoruz.
            return _result(
                EvidenceStatus.FAILED, "Gözlem sırasında paket kit değişti; kare kanıtı geçersiz."
            )
        return measured


def _project_root(root: Path, value: str) -> Path:
    original = Path(value)
    resolved = (root / original).resolve()
    if (
        original.is_absolute()
        or ".." in original.parts
        or "\\" in value
        or not resolved.is_relative_to(root.resolve())
        or any(part.startswith(".env") for path in (original, resolved) for part in path.parts)
    ):
        raise ValueError("Kit projesi sır içermeyen host kökü kapsamında olmalı.")
    return resolved


def _check_packaged(root: Path, contract: RegisteredKitContract) -> None:
    check_kit_shadow(root)
    if not contract.packaged_sources:
        raise ValueError("Host paket kit hash kaydı eksik.")
    expected = {source.path for source in contract.packaged_sources} | {"src/kit/theme.ts"}
    kit = _project_root(root, "src/kit")
    for path in kit.rglob("*"):
        if path.is_file() and str(path.relative_to(root)) not in expected:
            raise ValueError("Paket kitte gölgeleyici/tanımsız kaynak var.")
    for source in contract.packaged_sources:
        path = _project_root(root, source.path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source.digest:
            raise ValueError("Paket kit kaynakları değişti/eksik; özgün kit gerekli.")


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
