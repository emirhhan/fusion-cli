"""Kalıcı görev deposunun sözleşmesi (WP07). Her yöntem bağlamın yetkisini denetler.

Başka bir tenant'ın ya da workspace'in görevi "bulunamadı" ile aynı görünür:
var olup olmadığı da sızmaz.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from .execution_context import ExecutionContext
from .task_protocol import (
    InputSnapshotRef,
    OperationReceipt,
    OperationRequest,
    RunEvent,
    RunSnapshot,
    RunStatus,
)


class RunStore(Protocol):
    def accept(self, context: ExecutionContext, request: OperationRequest) -> OperationReceipt: ...

    def mark_dispatching(self, context: ExecutionContext, run_id: str) -> RunSnapshot: ...

    def set_status(
        self, context: ExecutionContext, run_id: str, status: RunStatus, *, error_code: str = ""
    ) -> RunSnapshot: ...

    def append_event(
        self, context: ExecutionContext, run_id: str, kind: str, payload: Mapping[str, object]
    ) -> RunEvent: ...

    def snapshot(self, context: ExecutionContext, run_id: str) -> RunSnapshot | None: ...

    def list_runs(self, context: ExecutionContext) -> tuple[RunSnapshot, ...]: ...

    def events_after(
        self, context: ExecutionContext, run_id: str, seq: int
    ) -> tuple[RunEvent, ...]: ...

    def request_cancel(self, context: ExecutionContext, run_id: str) -> RunSnapshot: ...

    def finish_cancel(
        self, context: ExecutionContext, run_id: str, *, stopped: bool
    ) -> RunSnapshot: ...

    def save_input(
        self, context: ExecutionContext, payload: Mapping[str, object]
    ) -> InputSnapshotRef: ...

    def load_input(
        self, context: ExecutionContext, ref: InputSnapshotRef
    ) -> dict[str, object] | None: ...

    def close(self) -> None: ...
