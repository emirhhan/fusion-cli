"""Headless karar yükünü gerçek kullanıcı etkileşiminden ayrı taşıyan metrikler."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InteractionMetrics:
    """Sayaçlar headless politika istekleridir; insan ölçümü yapılmadıysa None kalır."""

    approval_requests: int = 0
    repeated_requests: int = 0
    mode: str = "headless_policy"
    unnecessary_requests: int | None = None
    human_approval_requests: int | None = None
    human_response_seconds: float | None = None
    user_interventions: int | None = None
    pending_recovery_verified: bool | None = None
    restart_persistence_verified: bool | None = None


def merge_interactions(samples: tuple[InteractionMetrics | None, ...]) -> InteractionMetrics | None:
    """Ölçülmeyen tekrar varsa toplam da bilinmez; gerçek kullanıcı alanları türetilmez."""
    if not samples or any(sample is None for sample in samples):
        return None
    return InteractionMetrics(
        approval_requests=sum(sample.approval_requests for sample in samples if sample),
        repeated_requests=sum(sample.repeated_requests for sample in samples if sample),
    )
