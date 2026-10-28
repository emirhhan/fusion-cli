"""`RunStore`'un SQLite uygulaması: kalıcı kabul, olay günlüğü ve çökme kurtarması.

- Kabul ve ilk olay aynı `BEGIN IMMEDIATE` transaction'ındadır.
- Aynı (tenant, workspace, cihaz, anahtar) + aynı özet tek makbuz; farklı özet çatışma.
- Her görev, onu kabul eden deponun sahiplik kilidini (`SubmissionOwner`) taşır.
  Açılışta sahibi ölmüş görevler dürüstçe kapatılır: yürütmeye geçmiş olan
  `needs_reconciliation`, hiç başlamamış olan `cancelled` olur. Hiçbiri tekrar
  çalıştırılmaz: kalıcı günlük dış dünyadaki yan etkiyle tek transaction değildir.
- Girdi anlık görüntüsü değişmez ve sahiplik denetimlidir. ŞİFRELENMEZ; dosya
  yalnız sahibine açıktır (0600). Sır değerleri buraya yazılmamalıdır.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing, contextmanager
from pathlib import Path

from ..core.access_policy import Action, ResourceRef, authorize
from ..core.execution_context import ExecutionContext
from ..core.protocols import Clock
from ..core.task_protocol import (
    DISPATCHED_STATUSES,
    SCHEMA_VERSION,
    SCOPE_CANCEL,
    SCOPE_READ,
    SCOPE_RUN,
    SETTLED_STATUSES,
    IdempotencyConflictError,
    InputSnapshotRef,
    OperationReceipt,
    OperationRequest,
    RunAccessDeniedError,
    RunEvent,
    RunNotFoundError,
    RunSnapshot,
    RunStatus,
    args_digest,
)
from .submission_owner import SubmissionOwner

_DEFAULT_MAX_EVENTS = 5_000
_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, workspace TEXT NOT NULL,
    owner_user TEXT NOT NULL, device TEXT NOT NULL, idem_key TEXT NOT NULL,
    args_digest TEXT NOT NULL, tool TEXT NOT NULL, summary TEXT NOT NULL,
    project TEXT NOT NULL, chat_id TEXT NOT NULL, input_id TEXT NOT NULL,
    status TEXT NOT NULL, error TEXT NOT NULL, owner_epoch TEXT NOT NULL,
    created_at REAL NOT NULL, next_seq INTEGER NOT NULL, first_seq INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS runs_idem
    ON runs(tenant, workspace, device, idem_key) WHERE idem_key != '';
CREATE TABLE IF NOT EXISTS run_events (
    run_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL, at REAL NOT NULL,
    payload TEXT NOT NULL, PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS run_inputs (
    input_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, workspace TEXT NOT NULL,
    schema_version INTEGER NOT NULL, sha256 TEXT NOT NULL, body TEXT NOT NULL
);
"""
_COLUMNS = (
    "run_id,tenant,workspace,owner_user,device,status,summary,project,chat_id,"
    "created_at,next_seq,first_seq,error,owner_epoch,idem_key,args_digest"
)


class SqliteRunStore:
    def __init__(
        self,
        path: Path,
        *,
        clock: Clock,
        token_bytes: Callable[[int], bytes] = os.urandom,
        max_events: int = _DEFAULT_MAX_EVENTS,
    ) -> None:
        self._path = path
        self._clock = clock
        self._token_bytes = token_bytes
        self._max_events = max_events
        self._owner = SubmissionOwner(path.parent / "run-owners")
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as connection:
            connection.executescript(_SCHEMA)
        path.chmod(0o600)
        self._recover_abandoned()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self._path, timeout=10)) as connection, connection:
            connection.row_factory = sqlite3.Row
            yield connection

    def close(self) -> None:
        self._owner.close()

    # --- kabul -------------------------------------------------------------- #

    def accept(self, context: ExecutionContext, request: OperationRequest) -> OperationReceipt:
        if not context.has_scope(SCOPE_RUN):
            raise RunAccessDeniedError("Görev başlatma kapsamı yok.")
        with self._transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if request.idempotency_key:
                existing = connection.execute(
                    f"SELECT {_COLUMNS} FROM runs WHERE tenant=? AND workspace=? AND device=? "
                    "AND idem_key=?",
                    (
                        context.tenant_id,
                        context.workspace_id,
                        context.device_id,
                        request.idempotency_key,
                    ),
                ).fetchone()
                if existing is not None:
                    if existing["args_digest"] != request.args_digest:
                        raise IdempotencyConflictError("Aynı anahtar farklı içerikle gönderildi.")
                    return OperationReceipt(
                        existing["run_id"], RunStatus(existing["status"]), duplicate=True
                    )
            run_id = "run_" + self._token_bytes(9).hex()
            connection.execute(
                f"INSERT INTO runs ({_COLUMNS},tool,input_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,1,1,'',?,?,?,?,?)",
                (
                    run_id,
                    context.tenant_id,
                    context.workspace_id,
                    context.user_id,
                    context.device_id,
                    RunStatus.QUEUED.value,
                    request.summary,
                    request.project,
                    request.chat_id,
                    self._clock.now(),
                    self._owner.epoch(),
                    request.idempotency_key,
                    request.args_digest,
                    request.tool_name,
                    request.input_ref.snapshot_id if request.input_ref else "",
                ),
            )
            self._insert_event(connection, run_id, "accepted", {})
        return OperationReceipt(run_id, RunStatus.QUEUED)

    # --- durum -------------------------------------------------------------- #

    def mark_dispatching(self, context: ExecutionContext, run_id: str) -> RunSnapshot:
        """Yürütmeden önce kalıcı yaz: çökme sonrası bu görev asla yeniden çalıştırılmaz."""
        return self._transition(context, run_id, RunStatus.DISPATCHING, "dispatching")

    def set_status(
        self, context: ExecutionContext, run_id: str, status: RunStatus, *, error_code: str = ""
    ) -> RunSnapshot:
        return self._transition(context, run_id, status, None, error_code=error_code)

    def request_cancel(self, context: ExecutionContext, run_id: str) -> RunSnapshot:
        """Kuyruktaki iş hemen iptal; yürütülen iş önce `cancelling` olur."""
        with self._transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._owned_row(connection, context, run_id, Action.CANCEL, SCOPE_CANCEL)
            status = RunStatus(row["status"])
            if status is RunStatus.QUEUED:
                self._update(connection, run_id, RunStatus.CANCELLED, "cancelled", "cancelled")
            elif status in DISPATCHED_STATUSES and status is not RunStatus.CANCELLING:
                self._update(connection, run_id, RunStatus.CANCELLING, "", "cancelling")
            return self._snapshot_row(self._require(connection, run_id))

    def finish_cancel(
        self, context: ExecutionContext, run_id: str, *, stopped: bool
    ) -> RunSnapshot:
        """Duruş kanıtı varsa `cancelled`; yoksa sonucu bilinmez, uzlaştırma gerekir."""
        target = RunStatus.CANCELLED if stopped else RunStatus.NEEDS_RECONCILIATION
        kind = "cancelled" if stopped else "needs_reconciliation"
        return self._transition(context, run_id, target, kind, error_code="" if stopped else kind)

    def _transition(
        self,
        context: ExecutionContext,
        run_id: str,
        status: RunStatus,
        event_kind: str | None,
        *,
        error_code: str = "",
    ) -> RunSnapshot:
        with self._transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._owned_row(connection, context, run_id, Action.EXECUTE, None)
            if RunStatus(row["status"]) not in SETTLED_STATUSES:
                self._update(connection, run_id, status, error_code, event_kind)
            return self._snapshot_row(self._require(connection, run_id))

    def _update(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        status: RunStatus,
        error_code: str,
        event_kind: str | None,
    ) -> None:
        connection.execute(
            "UPDATE runs SET status=?, error=? WHERE run_id=?", (status.value, error_code, run_id)
        )
        if event_kind is not None:
            self._insert_event(connection, run_id, event_kind, {})

    # --- olaylar ------------------------------------------------------------ #

    def append_event(
        self, context: ExecutionContext, run_id: str, kind: str, payload: Mapping[str, object]
    ) -> RunEvent:
        with self._transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._owned_row(connection, context, run_id, Action.WRITE, None)
            return self._insert_event(connection, run_id, kind, payload)

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        kind: str,
        payload: Mapping[str, object],
    ) -> RunEvent:
        seq = int(
            connection.execute("SELECT next_seq FROM runs WHERE run_id=?", (run_id,)).fetchone()[0]
        )
        at = self._clock.now()
        connection.execute(
            "INSERT INTO run_events VALUES (?,?,?,?,?)",
            (run_id, seq, kind, at, json.dumps(dict(payload), ensure_ascii=False)),
        )
        oldest = seq - self._max_events + 1
        connection.execute(
            "UPDATE runs SET next_seq=?, first_seq=MAX(first_seq, ?) WHERE run_id=?",
            (seq + 1, oldest, run_id),
        )
        connection.execute("DELETE FROM run_events WHERE run_id=? AND seq<?", (run_id, oldest))
        return RunEvent(SCHEMA_VERSION, f"{run_id}:{seq}", run_id, seq, kind, at, dict(payload))

    def events_after(
        self, context: ExecutionContext, run_id: str, seq: int
    ) -> tuple[RunEvent, ...]:
        with self._transaction() as connection:
            if self._visible_row(connection, context, run_id) is None:
                return ()
            rows = connection.execute(
                "SELECT seq,kind,at,payload FROM run_events WHERE run_id=? AND seq>? ORDER BY seq",
                (run_id, seq),
            ).fetchall()
        return tuple(
            RunEvent(
                SCHEMA_VERSION,
                f"{run_id}:{row['seq']}",
                run_id,
                int(row["seq"]),
                row["kind"],
                float(row["at"]),
                json.loads(row["payload"]),
            )
            for row in rows
        )

    # --- okuma -------------------------------------------------------------- #

    def snapshot(self, context: ExecutionContext, run_id: str) -> RunSnapshot | None:
        with self._transaction() as connection:
            row = self._visible_row(connection, context, run_id)
        return self._snapshot_row(row) if row is not None else None

    def list_runs(self, context: ExecutionContext) -> tuple[RunSnapshot, ...]:
        if not context.has_scope(SCOPE_READ):
            raise RunAccessDeniedError("Görevleri okuma kapsamı yok.")
        with self._transaction() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM runs WHERE tenant=? AND workspace=? AND owner_user=? "
                "ORDER BY created_at DESC, rowid DESC",
                (context.tenant_id, context.workspace_id, context.user_id),
            ).fetchall()
        return tuple(self._snapshot_row(row) for row in rows)

    # --- girdi anlık görüntüsü --------------------------------------------- #

    def save_input(
        self, context: ExecutionContext, payload: Mapping[str, object]
    ) -> InputSnapshotRef:
        body = json.dumps(dict(payload), sort_keys=True, ensure_ascii=False)
        ref = InputSnapshotRef(
            "in_" + self._token_bytes(9).hex(), SCHEMA_VERSION, args_digest(payload)
        )
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO run_inputs VALUES (?,?,?,?,?,?)",
                (
                    ref.snapshot_id,
                    context.tenant_id,
                    context.workspace_id,
                    ref.schema_version,
                    ref.sha256,
                    body,
                ),
            )
        return ref

    def load_input(
        self, context: ExecutionContext, ref: InputSnapshotRef
    ) -> dict[str, object] | None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT body,sha256 FROM run_inputs WHERE input_id=? AND tenant=? AND workspace=?",
                (ref.snapshot_id, context.tenant_id, context.workspace_id),
            ).fetchone()
        if row is None or row["sha256"] != ref.sha256:
            return None
        value: dict[str, object] = json.loads(row["body"])
        return value if args_digest(value) == ref.sha256 else None

    # --- yetki ve satırlar -------------------------------------------------- #

    def _read(self, connection: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
        row: sqlite3.Row | None = connection.execute(
            f"SELECT {_COLUMNS} FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
        return row

    def _require(self, connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = self._read(connection, run_id)
        if row is None:
            raise RunNotFoundError(run_id)
        return row

    def _visible_row(
        self, connection: sqlite3.Connection, context: ExecutionContext, run_id: str
    ) -> sqlite3.Row | None:
        """Okunabilir satır; başka tenant'ın görevi yokmuş gibi davranır."""
        row = self._read(connection, run_id)
        if row is None:
            return None
        decision = authorize(context, _resource(row), Action.READ, required_scope=SCOPE_READ)
        return row if decision.allowed else None

    def _owned_row(
        self,
        connection: sqlite3.Connection,
        context: ExecutionContext,
        run_id: str,
        action: Action,
        scope: str | None,
    ) -> sqlite3.Row:
        row = self._read(connection, run_id)
        if row is None:
            raise RunNotFoundError(run_id)
        decision = authorize(context, _resource(row), action)
        if not decision.allowed:
            raise RunNotFoundError(run_id)
        if scope is not None and not context.has_scope(scope):
            raise RunAccessDeniedError(f"Kapsam yok: {scope}")
        return row

    def _snapshot_row(self, row: sqlite3.Row) -> RunSnapshot:
        return RunSnapshot(
            run_id=row["run_id"],
            tenant_id=row["tenant"],
            workspace_id=row["workspace"],
            owner_user_id=row["owner_user"],
            device_id=row["device"],
            status=RunStatus(row["status"]),
            summary=row["summary"],
            project=row["project"],
            chat_id=row["chat_id"],
            created_at=float(row["created_at"]),
            last_seq=int(row["next_seq"]) - 1,
            first_seq=int(row["first_seq"]),
            error_code=row["error"],
        )

    # --- kurtarma ----------------------------------------------------------- #

    def _recover_abandoned(self) -> None:
        with self._transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT run_id,status,owner_epoch FROM runs WHERE status NOT IN (?,?,?,?)",
                tuple(status.value for status in SETTLED_STATUSES),
            ).fetchall()
            for row in rows:
                if self._owner.is_alive(str(row["owner_epoch"])):
                    continue
                if RunStatus(row["status"]) is RunStatus.QUEUED:
                    # Hiç başlamamış iş yan etki üretmedi; tekrar çalıştırılmaz, iptal sayılır.
                    self._update(
                        connection,
                        row["run_id"],
                        RunStatus.CANCELLED,
                        "host_restarted",
                        "cancelled",
                    )
                else:
                    self._update(
                        connection,
                        row["run_id"],
                        RunStatus.NEEDS_RECONCILIATION,
                        "host_restarted",
                        "needs_reconciliation",
                    )


def _resource(row: sqlite3.Row) -> ResourceRef:
    return ResourceRef("run", row["run_id"], row["tenant"], row["workspace"], row["owner_user"])
