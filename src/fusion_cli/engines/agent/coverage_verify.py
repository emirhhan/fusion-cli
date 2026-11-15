"""Otomatik komut kapısının kapsamadığı ekosistemleri kullanıcıya bildir (A4-66)."""

from __future__ import annotations

from pathlib import Path

from ...core.verification import VerificationResult
from .domain_adapters.registry import DomainRegistry
from .verify_discovery import uncovered_ecosystems


class EcosystemCoverageVerifier:
    """Kapı kökte tek ekosistemi doğrular; geri kalanı SESSİZCE denetimsiz kalmasın.

    Hiçbir komut çalıştırmaz ve hiçbir zaman engellemez: yalnız `warnings` üretir.
    """

    def __init__(self, root: Path, *, domains: DomainRegistry | None = None) -> None:
        self._root = root
        self._domains = domains

    async def verify(self) -> VerificationResult:
        kapsam_disi = uncovered_ecosystems(self._root, domains=self._domains)
        if not kapsam_disi:
            return VerificationResult(ok=True)
        return VerificationResult(
            ok=True,
            warnings=(
                "Otomatik doğrulama kapsamı dışında: "
                + ", ".join(kapsam_disi)
                + ". Bu alanlardaki değişiklikler derleme/tip/test kapısından geçmedi; "
                "gerekiyorsa ilgili komutu elle çalıştır.",
            ),
        )
