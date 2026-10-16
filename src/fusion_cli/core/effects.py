"""Dış işlem kabulünün ham argüman taşımayan kalıcılık sözleşmesi."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .tools import AuthorizationScope, Tool, ToolEffect
from .types import ToolCall


class EffectPhase(StrEnum):
    IN_FLIGHT = "in_flight"
    RESPONDED = "responded"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class ExternalEffectIntent:
    step_id: str
    attempt: int
    call_id: str
    tool_name: str
    effect: ToolEffect
    scope: AuthorizationScope | None
    phase: EffectPhase = EffectPhase.IN_FLIGHT


class EffectRecorder(Protocol):
    async def prepare(
        self, call: ToolCall, tool: Tool, effect: ToolEffect, scope: AuthorizationScope | None
    ) -> None: ...

    async def finish(self, call_id: str, ok: bool) -> None: ...
