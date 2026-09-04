"""Kök görevi hızlı veya profesyonel yürütme yoluna yönlendir."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...core.execution_mode import ExecutionMode
from .classify import TaskClassification
from .execution_policy import ExecutionPolicy


class ExecutionRoute(Enum):
    """Bir kök görevin başlangıç yürütme yolu."""

    FAST = "fast"
    FAST_PROMOTABLE = "fast_promotable"
    WORKFLOW = "workflow"


@dataclass(frozen=True, slots=True)
class ExecutionRouteDecision:
    """Seçilen rota ve kullanıcıya açıklanabilir deterministik gerekçeler."""

    route: ExecutionRoute
    reasons: tuple[str, ...]


def choose_execution_route(
    task: str,
    classification: TaskClassification,
    policy: ExecutionPolicy,
    mode: ExecutionMode,
) -> ExecutionRouteDecision:
    """Görev kanıtlarından başlangıç rotasını seç.

    ``task`` gelecek kapsam sinyalleri için sözleşmede tutulur. İlk sürüm kararı
    mevcut sınıflandırma ve etki politikasının kanıtlarına dayandırır.
    """
    del task
    if mode is ExecutionMode.OFF:
        return ExecutionRouteDecision(ExecutionRoute.FAST, ("workflow_mode=off",))
    if mode is ExecutionMode.ALWAYS:
        return ExecutionRouteDecision(ExecutionRoute.WORKFLOW, ("workflow_mode=always",))
    if policy.required_effect is not None:
        return ExecutionRouteDecision(
            ExecutionRoute.WORKFLOW,
            (f"doğrulanması gereken dış etki: {policy.required_effect}",),
        )
    if policy.complex_task:
        return ExecutionRouteDecision(
            ExecutionRoute.WORKFLOW,
            (f"karmaşık görev türü: {classification.primary.value}",),
        )
    if not policy.offer_tools and classification.confidence > 0:
        return ExecutionRouteDecision(
            ExecutionRoute.FAST,
            ("araç gerektirmeyen basit görev",),
        )
    if classification.confidence <= 0:
        return ExecutionRouteDecision(
            ExecutionRoute.FAST_PROMOTABLE,
            ("görev kapsamı çalışma sırasında netleşecek",),
        )
    return ExecutionRouteDecision(
        ExecutionRoute.FAST_PROMOTABLE,
        ("araç kullanan görev çalışma sırasında büyüyebilir",),
    )
