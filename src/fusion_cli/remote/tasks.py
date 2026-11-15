"""Uzak görevlerin tel görünümü: kalıcı `RunStore` üzerinde bağlam denetimli adaptör.

Görevler artık bellekte değil, `memory.run_store` içinde durur: masaüstü yeniden
başladığında telefon son makbuz ve olay imlecinden devam eder; yarıda kalan iş
tekrar çalıştırılmaz, `needs_reconciliation` olarak görünür (WP07).

Her okuma ve iptal ÇAĞIRAN CİHAZIN bağlamıyla yapılır (WP02): başka hesabın
görevi "bulunamadı" görünür. Yürütücünün kendi yazımları (durum, olay) görevi
açan bağlamla yapılır; bu bağlam kabul anında saklanır.

Tel durum adları PWA ile uyumlu kalır (`done`, `waiting_approval`); kanonik
durumlar `core.task_protocol.RunStatus`'tadır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..accounts.workspaces import PERSONAL_WORKSPACE, bind_context, device_identity
from ..core.execution_context import ExecutionContext
from ..core.run_store import RunStore
from ..core.task_protocol import (
    OperationRequest,
    RunEvent,
    RunNotFoundError,
    RunSnapshot,
    RunStatus,
)
from .devices import Device
from .redaction import redact_payload

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_WAITING_APPROVAL = "waiting_approval"
STATE_PAUSED = "paused"
STATE_CANCELLING = "cancelling"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"
STATE_NEEDS_RECONCILIATION = "needs_reconciliation"
TERMINAL_STATES = frozenset({STATE_DONE, STATE_FAILED, STATE_CANCELLED, STATE_NEEDS_RECONCILIATION})

_WIRE_STATE = {
    RunStatus.QUEUED: STATE_QUEUED,
    RunStatus.DISPATCHING: STATE_RUNNING,
    RunStatus.RUNNING: STATE_RUNNING,
    RunStatus.WAITING_USER: STATE_WAITING_APPROVAL,
    RunStatus.PAUSED: STATE_PAUSED,
    RunStatus.CANCELLING: STATE_CANCELLING,
    RunStatus.SUCCEEDED: STATE_DONE,
    RunStatus.FAILED: STATE_FAILED,
    RunStatus.CANCELLED: STATE_CANCELLED,
    RunStatus.NEEDS_RECONCILIATION: STATE_NEEDS_RECONCILIATION,
}
_RUN_STATUS = {
    STATE_RUNNING: RunStatus.RUNNING,
    STATE_WAITING_APPROVAL: RunStatus.WAITING_USER,
    STATE_PAUSED: RunStatus.PAUSED,
    STATE_DONE: RunStatus.SUCCEEDED,
    STATE_FAILED: RunStatus.FAILED,
    STATE_CANCELLED: RunStatus.CANCELLED,
}


def device_context(device: Device) -> ExecutionContext:
    """Cihazın eşleştiği hesabın kişisel çalışma alanında, eşleşme kapsamlarıyla."""
    identity = device_identity(device.account_id, device.device_id, device.scopes)
    return bind_context(identity, PERSONAL_WORKSPACE)


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """Bir göreve ait değiştirilemez olay."""

    seq: int
    kind: str
    at: float
    payload: dict[str, Any] = field(default_factory=dict)

    def view(self) -> dict[str, Any]:
        return {"seq": self.seq, "kind": self.kind, "at": self.at, "payload": self.payload}


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Tek görevin tel görünümü; `run_id` tüm yüzeylerde aynı kimliktir."""

    run_id: str
    prompt_summary: str
    owner_device: str
    created_at: float
    project: str = ""
    chat_id: str = ""
    state: str = STATE_QUEUED
    last_seq: int = 0
    first_seq: int = 1

    def view(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "state": self.state,
            "project": self.project,
            "chatId": self.chat_id,
            "summary": self.prompt_summary,
            "createdAt": self.created_at,
            "lastSeq": self.last_seq,
            "firstSeq": self.first_seq,
        }


def _record(snapshot: RunSnapshot) -> TaskRecord:
    return TaskRecord(
        run_id=snapshot.run_id,
        prompt_summary=snapshot.summary,
        owner_device=snapshot.device_id,
        created_at=snapshot.created_at,
        project=snapshot.project,
        chat_id=snapshot.chat_id,
        state=_WIRE_STATE[snapshot.status],
        last_seq=snapshot.last_seq,
        first_seq=snapshot.first_seq,
    )


def _event(event: RunEvent) -> TaskEvent:
    return TaskEvent(event.seq, event.kind, event.at, dict(event.payload))


class TaskStore:
    """Uzak RPC'nin görev yüzü; kalıcılık ve yetki `RunStore`'dadır."""

    def __init__(self, runs: RunStore) -> None:
        self._runs = runs
        #: Yürütücü yazımları için görevi açan bağlam. Yeniden başlatılan süreçte
        #: boştur ve bu doğrudur: eski görev için yürütücü yoktur, yazım da olmaz.
        self._owners: dict[str, ExecutionContext] = {}

    def create(
        self,
        context: ExecutionContext,
        prompt_summary: str,
        *,
        args_digest: str,
        project: str = "",
        idempotency_key: str = "",
        chat_id: str = "",
    ) -> tuple[TaskRecord, bool]:
        """(kayıt, yeni_mi). Aynı anahtar+aynı içerik yeni görev açmaz; farklı içerik çatışır."""
        receipt = self._runs.accept(
            context,
            OperationRequest(
                idempotency_key=idempotency_key,
                tool_name="agent.run",
                args_digest=args_digest,
                summary=prompt_summary,
                project=project,
                chat_id=chat_id,
            ),
        )
        if not receipt.duplicate:
            self._owners[receipt.run_id] = context.with_run(receipt.run_id)
        record = self.get(context, receipt.run_id)
        if record is None:
            raise RunNotFoundError(receipt.run_id)
        return record, not receipt.duplicate

    def get(self, context: ExecutionContext, run_id: str) -> TaskRecord | None:
        snapshot = self._runs.snapshot(context, run_id)
        return _record(snapshot) if snapshot is not None else None

    def list_tasks(self, context: ExecutionContext) -> list[TaskRecord]:
        return [_record(snapshot) for snapshot in self._runs.list_runs(context)]

    def events_after(
        self, context: ExecutionContext, run_id: str, after_seq: int
    ) -> list[TaskEvent]:
        return [_event(event) for event in self._runs.events_after(context, run_id, after_seq)]

    def request_cancel(self, context: ExecutionContext, run_id: str) -> TaskRecord:
        return _record(self._runs.request_cancel(context, run_id))

    # --- yürütücü yazımları (görevi açan bağlamla) -------------------------- #

    def owned(self, run_id: str) -> TaskRecord | None:
        owner = self._owners.get(run_id)
        return self.get(owner, run_id) if owner is not None else None

    def mark_dispatching(self, run_id: str) -> None:
        owner = self._owners.get(run_id)
        if owner is not None:
            self._runs.mark_dispatching(owner, run_id)

    def set_state(self, run_id: str, state: str) -> None:
        owner = self._owners.get(run_id)
        status = _RUN_STATUS.get(state)
        if owner is not None and status is not None:
            self._runs.set_status(owner, run_id, status)

    def finish_cancel(self, run_id: str, *, stopped: bool) -> None:
        owner = self._owners.get(run_id)
        if owner is not None:
            self._runs.finish_cancel(owner, run_id, stopped=stopped)

    def append(self, run_id: str, kind: str, payload: dict[str, Any]) -> TaskEvent | None:
        """Olayı gizleyerek ekle; sahibi bilinmeyen görev için yazım yapılmaz."""
        owner = self._owners.get(run_id)
        if owner is None:
            return None
        return _event(self._runs.append_event(owner, run_id, kind, redact_payload(payload)))
