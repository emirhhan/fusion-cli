"""Görev ve olay deposu: run_id, monoton sıra, idempotency, sınırlı bellek."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..core.protocols import Clock
from .constants import MAX_EVENTS_PER_TASK
from .redaction import redact_payload

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_WAITING_APPROVAL = "waiting_approval"
STATE_PAUSED = "paused"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"
TERMINAL_STATES = frozenset({STATE_DONE, STATE_FAILED, STATE_CANCELLED})


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """Bir göreve ait değiştirilemez olay."""

    seq: int
    kind: str
    at: float
    payload: dict[str, Any]

    def view(self) -> dict[str, Any]:
        return {"seq": self.seq, "kind": self.kind, "at": self.at, "payload": self.payload}


@dataclass(slots=True)
class TaskRecord:
    """Tek görev; `run_id` tüm yüzeylerde aynı kimliktir."""

    run_id: str
    prompt_summary: str
    owner_device: str
    created_at: float
    project: str = ""
    chat_id: str = ""
    state: str = STATE_QUEUED
    events: list[TaskEvent] = field(default_factory=list)
    next_seq: int = 1

    def view(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "state": self.state,
            "project": self.project,
            "chatId": self.chat_id,
            "summary": self.prompt_summary,
            "createdAt": self.created_at,
            "lastSeq": self.next_seq - 1,
        }


class TaskStore:
    """Görevleri bellekte tutar; aynı idempotency anahtarı aynı görevi döndürür."""

    def __init__(self, clock: Clock, *, token_bytes: Callable[[int], bytes] = os.urandom) -> None:
        self._clock = clock
        self._token_bytes = token_bytes
        self._tasks: dict[str, TaskRecord] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    def create(
        self,
        owner_device: str,
        prompt_summary: str,
        project: str = "",
        idempotency_key: str = "",
        chat_id: str = "",
    ) -> tuple[TaskRecord, bool]:
        """(kayıt, yeni_mi). Aynı cihaz+anahtar ikinci kez yeni görev açmaz."""
        if idempotency_key:
            known = self._idempotency.get((owner_device, idempotency_key))
            if known is not None and known in self._tasks:
                return self._tasks[known], False
        record = TaskRecord(
            run_id="run_" + self._token_bytes(9).hex(),
            prompt_summary=prompt_summary,
            owner_device=owner_device,
            created_at=self._clock.now(),
            project=project,
            chat_id=chat_id,
        )
        self._tasks[record.run_id] = record
        if idempotency_key:
            self._idempotency[(owner_device, idempotency_key)] = record.run_id
        return record, True

    def get(self, run_id: str) -> TaskRecord | None:
        return self._tasks.get(run_id)

    def list_tasks(self) -> list[TaskRecord]:
        return sorted(self._tasks.values(), key=lambda item: item.created_at, reverse=True)

    def set_state(self, run_id: str, state: str) -> None:
        record = self._tasks.get(run_id)
        if record is not None and record.state not in TERMINAL_STATES:
            record.state = state

    def append(self, run_id: str, kind: str, payload: dict[str, Any]) -> TaskEvent | None:
        """Olayı gizleyerek ekle; sınır aşılırsa en eskiyi at (sıra numarası korunur)."""
        record = self._tasks.get(run_id)
        if record is None:
            return None
        event = TaskEvent(
            seq=record.next_seq,
            kind=kind,
            at=self._clock.now(),
            payload=redact_payload(payload),
        )
        record.next_seq += 1
        record.events.append(event)
        if len(record.events) > MAX_EVENTS_PER_TASK:
            del record.events[0]
        return event

    def events_after(self, run_id: str, after_seq: int) -> list[TaskEvent]:
        record = self._tasks.get(run_id)
        if record is None:
            return []
        return [event for event in record.events if event.seq > after_seq]
