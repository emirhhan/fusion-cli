"""Görev kabulü, makbuz ve olay sözleşmesi — bütün yüzeyler için tek tel biçimi (WP07).

Rapor §4: görev durumu ile tek bir aracın sonucu ayrıdır. Görev durumları
`RunStatus`, işlem sonuçları `OperationOutcome`'dur. `unknown` ve
`needs_reconciliation` "karşı uçta iş olmuş olabilir" demektir; otomatik olarak
başarı ya da hata sayılmaz.

Her olay `schema_version`, `event_id`, `run_id`, monoton `seq` ve sunucu zamanı
taşır. İstemci tekrar eden olayı atlar, sıra boşluğunda snapshot ister.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from .errors import FusionError

SCHEMA_VERSION = 1

#: Görev işlemleri için gereken kapsamlar (uzak `Scope` değerleriyle aynı metin).
SCOPE_RUN = "agent.run"
SCOPE_READ = "project.read"
SCOPE_CANCEL = "agent.cancel"


class RunStatus(StrEnum):
    QUEUED = "queued"
    #: Yürütmeye başlamadan HEMEN önce kalıcı yazılır; çökme sonrası tekrar yasağının dayanağı.
    DISPATCHING = "dispatching"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_RECONCILIATION = "needs_reconciliation"


#: Bir daha değişmeyen durumlar.
TERMINAL_STATUSES = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED})
#: Otomasyonun değiştiremediği durumlar: uzlaştırma kullanıcıya aittir.
SETTLED_STATUSES = TERMINAL_STATUSES | {RunStatus.NEEDS_RECONCILIATION}
#: Yürütmeye geçmiş (yan etki üretmiş olabilecek) durumlar.
DISPATCHED_STATUSES = frozenset(
    {
        RunStatus.DISPATCHING,
        RunStatus.RUNNING,
        RunStatus.WAITING_USER,
        RunStatus.PAUSED,
        RunStatus.CANCELLING,
    }
)


class OperationOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class IdempotencyConflictError(FusionError, ValueError):
    """Aynı idempotency anahtarı farklı içerikle yeniden gönderildi."""


class RunAccessDeniedError(FusionError, PermissionError):
    """Bağlamın bu görev işlemi için kapsamı yok."""


class RunNotFoundError(FusionError, LookupError):
    """Görev yok ya da bu bağlama ait değil (ikisi bilerek ayırt edilmez)."""


def args_digest(value: object) -> str:
    """Argümanların kanonik JSON özeti; anahtar sırası ve boşluk sonucu değiştirmez."""
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class InputSnapshotRef:
    """Değişmez girdi kaydına referans; karma tek başına girdiyi kurmaya yetmez."""

    snapshot_id: str
    schema_version: int
    sha256: str


@dataclass(frozen=True, slots=True)
class OperationRequest:
    idempotency_key: str
    tool_name: str
    args_digest: str
    summary: str = ""
    project: str = ""
    chat_id: str = ""
    input_ref: InputSnapshotRef | None = None


@dataclass(frozen=True, slots=True)
class OperationReceipt:
    run_id: str
    status: RunStatus
    #: Aynı anahtarla daha önce kabul edilmiş işin makbuzu mu?
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class RunEvent:
    schema_version: int
    event_id: str
    run_id: str
    seq: int
    kind: str
    at: float
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    run_id: str
    tenant_id: str
    workspace_id: str
    owner_user_id: str
    device_id: str
    status: RunStatus
    summary: str
    project: str
    chat_id: str
    created_at: float
    last_seq: int
    #: Saklama sınırı yüzünden atılan olaylardan sonraki ilk sıra; boşluk tespiti için.
    first_seq: int
    error_code: str = ""
