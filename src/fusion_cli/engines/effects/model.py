"""Gerçek dünya etkileri için deterministik sözleşme ve workflow durumu.

Bir LLM'nin doğal dilde "yaptım" demesi kanıt değildir. Bu modül, operasyonun
başarılı sayılabilmesi için gereken post-condition'ları yapılandırılmış veri olarak
tanımlar. Workflow runner yalnızca bu koşullar doğrulandığında ``COMPLETED`` olur.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class EffectKind(Enum):
    """Fusion'ın gerçek yan etki üretebilen operasyon sınıfları."""

    GIT_PUSH = "git_push"
    GIT_COMMIT = "git_commit"
    WORKSPACE_MUTATION = "workspace_mutation"
    SHELL_ACTION = "shell_action"
    WEB_LOOKUP = "web_lookup"
    WORKSPACE_READ = "workspace_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    PACKAGE_INSTALL = "package_install"
    DEPLOYMENT = "deployment"
    SERVICE_RESTART = "service_restart"
    DATABASE_MIGRATION = "database_migration"
    GITHUB_RELEASE = "github_release"


class WorkflowStatus(Enum):
    """Kalıcı workflow yaşam döngüsü."""

    PENDING = "pending"
    REPOSITORY_INSPECTED = "repository_inspected"
    AWAITING_TARGET_CONFIRMATION = "awaiting_target_confirmation"
    TARGET_CONFIRMED = "target_confirmed"
    STAGED = "staged"
    NOTHING_TO_STAGE = "nothing_to_stage"
    COMMITTED = "committed"
    NOTHING_TO_COMMIT = "nothing_to_commit"
    PUSHED = "pushed"
    AWAITING_FORCE_CONFIRMATION = "awaiting_force_confirmation"
    REMOTE_VERIFIED = "remote_verified"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}


@dataclass(frozen=True, slots=True)
class EffectContract:
    """Bir operasyonun tamamlanma sözleşmesi.

    ``required_evidence`` yalnızca açıklama değildir; handler bu anahtarların
    tamamını üretmeden başarı sonucu veremez.
    """

    kind: EffectKind
    required_evidence: tuple[str, ...]
    confirmation_policy: str
    deterministic_handler: str | None = None
    rollback_policy: str = "best_effort"


@dataclass(frozen=True, slots=True)
class Evidence:
    """Gerçek araç çıktısından türetilen tek bir kanıt."""

    key: str
    value: str
    source: str
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(slots=True)
class WorkflowRecord:
    """Diskte saklanan, yeniden başlatılabilir workflow kaydı."""

    workflow_id: str
    kind: str
    root: str
    task: str
    status: str = WorkflowStatus.PENDING.value
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    data: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None

    def set_status(self, status: WorkflowStatus) -> None:
        self.status = status.value
        self.updated_at = datetime.now(UTC).isoformat()

    def add_evidence(self, item: Evidence) -> None:
        self.evidence.append(asdict(item))
        self.updated_at = datetime.now(UTC).isoformat()

    def has_evidence(self, key: str) -> bool:
        return any(item.get("key") == key for item in self.evidence)

    def as_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "WorkflowRecord":
        return cls(
            workflow_id=str(raw["workflow_id"]),
            kind=str(raw["kind"]),
            root=str(raw["root"]),
            task=str(raw.get("task", "")),
            status=str(raw.get("status", WorkflowStatus.PENDING.value)),
            created_at=str(raw.get("created_at", datetime.now(UTC).isoformat())),
            updated_at=str(raw.get("updated_at", datetime.now(UTC).isoformat())),
            data=dict(raw.get("data") or {}),
            evidence=[dict(item) for item in (raw.get("evidence") or [])],
            error=raw.get("error"),
        )


@dataclass(frozen=True, slots=True)
class EffectRunResult:
    """Deterministik handler'ın agent döngüsüne döndürdüğü sonuç."""

    final_text: str
    ok: bool
    tool_calls_made: int = 0
    mutating_tool_calls_made: int = 0
    failed_tool_calls: int = 0
    workflow_id: str | None = None
    kind: str | None = None
    status: str | None = None
    title: str = "Workflow sonucu"
    details: dict[str, object] = field(default_factory=dict)


def missing_evidence(record: WorkflowRecord, contract: EffectContract) -> tuple[str, ...]:
    """Sözleşmenin eksik post-condition kanıtlarını kararlı sırada döndür."""

    return tuple(
        key for key in contract.required_evidence if not record.has_evidence(key)
    )


CONTRACTS: dict[EffectKind, EffectContract] = {
    EffectKind.GIT_PUSH: EffectContract(
        kind=EffectKind.GIT_PUSH,
        required_evidence=(
            "repository_inspected",
            "target_confirmed",
            "push_exit_zero",
            "local_head",
            "remote_head",
            "remote_verified",
        ),
        confirmation_policy="target_and_force",
        deterministic_handler="git_push",
        rollback_policy="git_recoverable_except_remote_history",
    ),
    EffectKind.GIT_COMMIT: EffectContract(
        kind=EffectKind.GIT_COMMIT,
        required_evidence=("repository_inspected", "commit_created"),
        confirmation_policy="mutating_tool_policy",
    ),
    EffectKind.WORKSPACE_MUTATION: EffectContract(
        kind=EffectKind.WORKSPACE_MUTATION,
        required_evidence=("mutating_tool_success", "postcondition_verified"),
        confirmation_policy="mutating_tool_policy",
    ),
    EffectKind.SHELL_ACTION: EffectContract(
        kind=EffectKind.SHELL_ACTION,
        required_evidence=("shell_exit_zero", "postcondition_verified"),
        confirmation_policy="mutating_tool_policy",
    ),
    EffectKind.WEB_LOOKUP: EffectContract(
        kind=EffectKind.WEB_LOOKUP,
        required_evidence=("web_tool_success",),
        confirmation_policy="none",
    ),
    EffectKind.WORKSPACE_READ: EffectContract(
        kind=EffectKind.WORKSPACE_READ,
        required_evidence=("read_tool_success",),
        confirmation_policy="none",
    ),
}


def root_key(root: Path) -> str:
    """Workflow eşleştirmesi için çözülmüş kök yolu."""

    return str(root.expanduser().resolve())
