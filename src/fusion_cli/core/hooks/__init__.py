"""Genel kanca sistemi (P-009): olay kataloğu, eşleştirici ve karar sözleşmesi."""

from __future__ import annotations

from .decision import merge_verdicts, verdict_from_run
from .events import (
    HookCommand,
    HookEvent,
    HookRun,
    HookSet,
    HookSkip,
    HookVerdict,
    parse_event,
)
from .matcher import matcher_matches

__all__ = [
    "HookCommand",
    "HookEvent",
    "HookRun",
    "HookSet",
    "HookSkip",
    "HookVerdict",
    "matcher_matches",
    "merge_verdicts",
    "parse_event",
    "verdict_from_run",
]
