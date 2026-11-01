"""Dersin güvenilir çağrı bağlamı ve operasyonel kullanım bağı."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .memory import LessonRecallPolicy

HINT_LIMIT = 2
USAGE_UNKNOWN = "usage_unknown"
VERIFIED_OUTCOME = "verified_outcome"


class LessonDelivery(StrEnum):
    """Dersin modele sunulduğu gerçek sınır."""

    TOOL = "tool"
    HINT = "hint"
    TEACHER = "teacher"


@dataclass(frozen=True, slots=True)
class LessonRuntimeContext:
    """Model argümanlarından bağımsız, harness tarafından belirlenen kapsam."""

    policy: LessonRecallPolicy = field(default_factory=LessonRecallPolicy)


@dataclass(frozen=True, slots=True)
class LessonUse:
    """Gerçek yürütücünün aynı değişmez rutin kaynağına bağladığı tüketim."""

    lesson_id: str
    routine_id: str
    source_digest: str
    criterion_ids: tuple[str, ...]
    call_ids: tuple[str, ...]
