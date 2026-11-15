"""Gerçek sağlayıcı olaylarından bütün rollerin görev bütçesini ölçer."""

from __future__ import annotations

from evals.execution import ModelCallIdentity
from fusion_cli.core.errors import EvalError
from fusion_cli.core.events import (
    Event,
    EventPublisher,
    ExecutionRetryScheduled,
    ModelCallAbandoned,
    ModelCallFinished,
    ModelCallStarted,
)
from fusion_cli.core.types import is_permanent_error


class TaskBudgetExhaustedError(EvalError):
    """Sağlayıcı çağrısı başlamadan ölçülmüş görev tavanı doldu."""


class CountingPublisher:
    """Model çağrısını ve kurtarma turunu event akışından say, downstream'e ilet.

    `retries` eskiden yürütücüde SABİT 0 yazıyordu; ölçüm "hiç kurtarma yapılmadı"
    sonucunu koddan üretiyordu ve `first_attempt_success` her görevi ilk denemede
    başarılı gösteriyordu. Sayı artık olay akışından gelir.
    """

    def __init__(self, downstream: EventPublisher, max_calls: int | None = None) -> None:
        self._downstream = downstream
        self._max_calls = max_calls
        self.model_calls = 0
        self.retries = 0
        self.calls: list[ModelCallIdentity] = []
        self.events: list[Event] = []
        self._seen_call_ids: set[str] = set()

    def publish(self, event: Event) -> None:
        if (
            isinstance(event, ModelCallStarted)
            and self._max_calls is not None
            and event.call_id not in self._seen_call_ids
            and self.model_calls >= self._max_calls
        ):
            raise TaskBudgetExhaustedError(
                "Görev çağrı bütçesi doldu; yeni sağlayıcı çağrısı yapılmadı."
            )
        self.events.append(event)
        if isinstance(event, (ModelCallStarted, ModelCallFinished, ModelCallAbandoned)):
            if event.call_id:
                if event.call_id not in self._seen_call_ids:
                    self.model_calls += 1
                    self._seen_call_ids.add(event.call_id)
            elif not isinstance(event, ModelCallStarted):
                self.model_calls += 1
        if isinstance(event, ModelCallFinished):
            self._record_identity(call_identity(event))
        elif isinstance(event, ModelCallAbandoned):
            outcome = "timeout" if _has_timeout(event.reason) else "abandoned"
            self._record_identity(
                ModelCallIdentity(
                    event.call_id, event.role, event.model or None, None, outcome=outcome
                )
            )
        elif isinstance(event, ExecutionRetryScheduled):
            self.retries += 1
        self._downstream.publish(event)

    def _record_identity(self, identity: ModelCallIdentity) -> None:
        if identity.call_id:
            for index, previous in enumerate(self.calls):
                if previous.call_id == identity.call_id:
                    if identity.outcome not in {"abandoned", "timeout"}:
                        self.calls[index] = identity
                    return
        self.calls.append(identity)


def call_identity(event: ModelCallFinished) -> ModelCallIdentity:
    """Task3 korelasyon kimliğini taşı; taşıma kimliğini served_by sanma."""
    result = event.result
    outcome = "ok"
    if not result.ok:
        if result.is_rate_limited:
            outcome = "rate_limited"
        elif _has_timeout(result.error or ""):
            outcome = "timeout"
        elif is_permanent_error(result.error):
            outcome = "provider_unavailable"
        else:
            outcome = "provider_error"
    return ModelCallIdentity(
        event.call_id,
        event.role,
        event.requested_model or None,
        result.served_by or None,
        result.usage.prompt_tokens if result.usage.prompt_measured else None,
        result.usage.completion_tokens if result.usage.completion_measured else None,
        outcome,
        result.usage.cost_usd if result.usage.cost_known else None,
    )


def _has_timeout(detail: str) -> bool:
    return any(marker in detail.casefold() for marker in ("timeout", "zaman aşım"))
