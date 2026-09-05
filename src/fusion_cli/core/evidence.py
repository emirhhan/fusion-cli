"""Başarı koşullarını gözlenebilir kanıta bağlayan çekirdek türler."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
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


@dataclass(frozen=True, slots=True)
class ToolUse:
    """Turda denenen tek araç çağrısı."""

    name: str
    ok: bool = True
    mutating: bool = False
    arguments: Mapping[str, object] = field(default_factory=dict)
    output: str = ""
