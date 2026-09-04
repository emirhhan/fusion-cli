"""Hızlı agent turunu çalışma kanıtıyla profesyonel akışa yükselt."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionSignals:
    """Bir görevin tek güvenli tura sığmadığını gösteren sayaç ve bayraklar."""

    pending_todos: int = 0
    touched_components: int = 0
    tool_families: int = 0
    has_dependency: bool = False
    needs_repair: bool = False
    needs_verification: bool = False
    budget_pressure: bool = False


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """Workflow'a geçiş kararı ve gözlenebilir gerekçeleri."""

    should_promote: bool
    reasons: tuple[str, ...] = ()


def should_promote(signals: ExecutionSignals) -> PromotionDecision:
    """Hızlı yolun büyüyen işi workflow'a bırakması gerekip gerekmediğini seç."""
    reasons: list[str] = []
    if signals.pending_todos >= 3:
        reasons.append("üç veya daha fazla bekleyen iş")
    if signals.touched_components >= 2:
        reasons.append("birden fazla bileşen")
    if signals.tool_families >= 2:
        reasons.append("birden fazla araç ailesi")
    if signals.has_dependency:
        reasons.append("araç çıktısına bağlı sonraki iş")
    if signals.needs_repair:
        reasons.append("teşhis ve onarım gerektiren hata")
    if signals.needs_verification:
        reasons.append("ayrı doğrulama gereksinimi")
    if signals.budget_pressure:
        reasons.append("hızlı yol bütçesi yetersiz")
    return PromotionDecision(should_promote=bool(reasons), reasons=tuple(reasons))
