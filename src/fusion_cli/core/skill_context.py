"""Kabul edilen turun gerçekten taşıdığı beceri snapshot kimliği."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkillSelection:
    qualified_name: str
    revision: str
    next_offset: int | None = None
