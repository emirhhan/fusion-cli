"""Kalıcı alt ajan kimliği ve devam için doğrulanmış sınırlar."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .types import Message


@dataclass(frozen=True, slots=True)
class AgentRunState:
    """Yalnız yetki alanı ve geçmişin doğruluğu; sır veya yapılandırma taşımaz."""

    agent_id: str
    parent_session: str
    root: str
    agent_type: str
    complete_history: bool
    name: str = ""
    tool_names: tuple[str, ...] | None = None
    denied_tools: tuple[str, ...] = ()
    write_scope: tuple[str, ...] = ()
    status: str = "completed"
    read_only: bool = False
    background: bool = False
    parent_turn: str = ""


class AgentTranscriptCapture(Protocol):
    """Üretici sınırlarından tam bilinen mesajları aynı günlüğe taşı."""

    complete_history: bool
    messages: tuple[Message, ...]

    async def begin(self, messages: Sequence[Message]) -> None: ...
    async def capture(self, messages: Sequence[Message]) -> None: ...
    def reset(self, messages: Sequence[Message]) -> None: ...
