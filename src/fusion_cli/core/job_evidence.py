"""Arka plan teslim kanıtı; çıkış kodu görsel kalite iddiası değildir."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .repair_ledger import SourceFingerprint


class JobPhase(Enum):
    """Başlatma ve bekleme tamamlanmış çalıştırmadan ayrıdır."""

    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class ArtifactReceipt:
    """Önce/sonra hash yalnız çıktı yenilenmesini gösterir; görüntü kalitesini değil."""

    path: str
    before_hash: str | None
    after_hash: str | None

    @property
    def is_refreshed(self) -> bool:
        return self.after_hash is not None and self.after_hash != self.before_hash


@dataclass(frozen=True, slots=True)
class JobCompletion:
    """Gerçek iş kimliği, komutu, çıkışı ve sınırlandırılmış teslim kapsamı."""

    job_id: str
    command: str
    phase: JobPhase
    exit_code: int | None = None
    sources_before: tuple[SourceFingerprint, ...] = ()
    sources_after: tuple[SourceFingerprint, ...] = ()
    outputs: tuple[ArtifactReceipt, ...] = ()
