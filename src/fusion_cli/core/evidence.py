"""Başarı koşullarını gözlenebilir kanıta bağlayan çekirdek türler."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .execution_plan import VerificationCheckKind


class EvidenceStatus(StrEnum):
    """Tek bir başarı koşulunun doğrulanma durumu."""

    PASSED = "passed"
    FAILED = "failed"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class CriterionEvidence:
    """Bir plan koşulu için üretilen sınırlı ve tipli kanıt."""

    criterion_id: str
    kind: VerificationCheckKind
    status: EvidenceStatus
    summary: str
    artifact: str = ""
    command: str = ""
    output: str = ""
