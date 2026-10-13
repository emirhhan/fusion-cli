"""Gönderimin kalıcı kabul ve deneme kimlikleri."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class SubmissionState(StrEnum):
    """Tekrar yürütmeyi belirleyen kalıcı durum."""

    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECOVERY_REQUIRED = "recoveryRequired"


@dataclass(frozen=True)
class SubmissionKey:
    """Profil, kök ve sohbet kapsamında tek gönderim."""

    profile_id: str
    root: str
    conversation_id: str
    request_id: str


@dataclass(frozen=True)
class SubmissionReceipt:
    """İçerik taşımayan kalıcı kabul kaydı."""

    key: SubmissionKey
    attempt_id: str
    state: SubmissionState
    error_code: str | None = None


@dataclass(frozen=True)
class SubmissionClaim:
    """Atomik kabulün yürütme sahipliği."""

    is_owner: bool
    receipt: SubmissionReceipt


class SubmissionRepository(Protocol):
    """Gönderim metadata deposunun motor sınırı."""

    async def lookup(self, key: SubmissionKey) -> SubmissionReceipt | None: ...
    async def claim(self, key: SubmissionKey) -> SubmissionClaim: ...
    async def finish(
        self, receipt: SubmissionReceipt, *, state: str, error_code: str | None = None
    ) -> SubmissionReceipt: ...

    async def retry(self, key: SubmissionKey) -> SubmissionClaim: ...
    async def close(self) -> None: ...
    async def delete_conversation(self, profile: str, root: str, conversation: str) -> None: ...
    async def move_prepared(
        self, profile: str, root: str, conversation: str, target: str
    ) -> bool: ...

    async def prepare_move(
        self, profile: str, root: str, conversation: str, target: str
    ) -> None: ...

    async def move_conversation(
        self, profile: str, root: str, conversation: str, target: str
    ) -> None: ...
