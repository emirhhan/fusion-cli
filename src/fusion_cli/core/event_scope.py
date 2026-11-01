"""Bir turun bütün model ve araç olaylarında ortak korelasyonu taşı."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

from .events import Event, EventPublisher, ToolCallRepaired, ToolExecuted, ToolStarted


def new_trace_id() -> str:
    """Üretimde çakışmaz, testte enjekte edilebilir kimlik üret."""
    return uuid4().hex


class TurnPublisher:
    """Mevcut kimlikleri koru; eksik turn/event alanlarını sahipli scope ile doldur."""

    def __init__(
        self,
        inner: EventPublisher,
        *,
        session_id: str | None,
        attempt_id: str | None = None,
        id_factory: Callable[[], str] = new_trace_id,
        should_assign_event_ids: bool = True,
    ) -> None:
        self._should_assign_event_ids = should_assign_event_ids
        self._inner = inner
        self._session_id = session_id
        self._attempt_id = attempt_id or id_factory()
        self._id_factory = id_factory

    @property
    def turn_id(self) -> str:
        """Yayıncının mevcut tur kimliğini yeni kimlik üretmeden paylaş."""
        return self._attempt_id

    def publish(self, event: Event) -> None:
        """Alt ajan ve sağlayıcı olayları aynı turu paylaşır; call_id aynen kalır."""
        event = replace(
            event,
            event_id=event.event_id
            or (self._id_factory() if self._should_assign_event_ids else None),
            session_id=event.session_id or self._session_id,
            turn_id=event.turn_id or self._attempt_id,
            schema_version=event.schema_version or 1,
        )
        if isinstance(event, (ToolStarted, ToolExecuted, ToolCallRepaired)):
            event = replace(event, attempt_id=event.attempt_id or event.turn_id)
        self._inner.publish(event)
