"""Özgün tur segmentleri için dosya sisteminden bağımsız okuma sözleşmesi."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from .redaction import contains_sensitive
from .types import Message, ToolCall

ORIGINAL_TRACE_ROLES = frozenset({"system", "user", "assistant", "tool"})
ORIGINAL_TRACE_MAX_CHARS = 60_000
ORIGINAL_TRACE_MAX_SEGMENTS = 128
_TRACE_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


@dataclass(frozen=True, slots=True)
class OriginalTraceScope:
    """Çağıranın doğruladığı sahip, tur ve sıralı segment kapsamı."""

    owner_id: str
    turn_id: str
    segment_ids: tuple[str, ...]
    max_chars: int = ORIGINAL_TRACE_MAX_CHARS

    def is_valid(self) -> bool:
        """Dizin geçişini, yinelenen kimliği ve sınırsız okumayı reddet."""
        identities = (self.owner_id, self.turn_id, *self.segment_ids)
        return (
            all(
                isinstance(identity, str)
                and identity not in {".", ".."}
                and _TRACE_ID.fullmatch(identity) is not None
                and not contains_sensitive(identity)
                for identity in identities
            )
            and 0 < len(self.segment_ids) <= ORIGINAL_TRACE_MAX_SEGMENTS
            and len(set(self.segment_ids)) == len(self.segment_ids)
            and isinstance(self.max_chars, int)
            and not isinstance(self.max_chars, bool)
            and 0 < self.max_chars <= ORIGINAL_TRACE_MAX_CHARS
        )


@dataclass(frozen=True, slots=True)
class OriginalTraceRead:
    """Okuma sonucu; yalnız eksiksiz, maskelenmiş özgün kayıt özete kaynak olabilir."""

    scope: OriginalTraceScope
    status: Literal[
        "redacted_original", "missing", "invalid_scope", "incomplete", "truncated", "unavailable"
    ]
    messages: tuple[Message, ...] = ()

    def is_usable(self) -> bool:
        """Sıralı, tamamlanmış araç grupları ve sınırlı içerik gerektir."""
        if (
            self.status != "redacted_original"
            or not self.scope.is_valid()
            or not self.messages
            or not _has_complete_batches(self.messages)
        ):
            return False
        size = sum(
            len(message.content) + sum(len(call.arguments) for call in message.tool_calls)
            for message in self.messages
        )
        return size <= self.scope.max_chars


def _has_complete_batches(messages: tuple[Message, ...]) -> bool:
    """Açık çağrı kümesini sırayla tüket; grubun kendi sonuç sırası serbesttir."""
    pending: set[str] = set()
    seen: set[str] = set()
    for message in messages:
        if (
            not isinstance(message.role, str)
            or message.role not in ORIGINAL_TRACE_ROLES
            or not isinstance(message.content, str)
            or message.harness_note
        ):
            return False
        if message.role == "tool":
            if (
                message.tool_calls
                or not isinstance(message.tool_call_id, str)
                or message.tool_call_id not in pending
            ):
                return False
            pending.remove(message.tool_call_id)
            continue
        if pending or message.tool_call_id is not None:
            return False
        if not message.tool_calls:
            continue
        if message.role != "assistant" or any(
            not _is_valid_call(call) for call in message.tool_calls
        ):
            return False
        identities = [call.id for call in message.tool_calls]
        if len(set(identities)) != len(identities) or seen.intersection(identities):
            return False
        pending.update(identities)
        seen.update(identities)
    return not pending


def _is_valid_call(call: ToolCall) -> bool:
    """Dataclass dışarıdan kurulduğunda da kimlik türünü uydurma."""
    return (
        isinstance(call, ToolCall)
        and isinstance(call.id, str)
        and bool(call.id)
        and isinstance(call.name, str)
        and bool(call.name)
        and isinstance(call.arguments, str)
    )


class OriginalTraceReader(Protocol):
    """Doğrulanmış ve sınırlı kapsamdaki özgün segmentleri oku."""

    async def read_original(self, scope: OriginalTraceScope) -> OriginalTraceRead: ...


@runtime_checkable
class OriginalTraceJournal(OriginalTraceReader, Protocol):
    """Aynı günlük sahibinin özgün segment üretici/okuyucu yüzeyi."""

    @property
    def original_owner_id(self) -> str: ...

    async def append_original(
        self, scope: OriginalTraceScope, messages: Sequence[Message]
    ) -> bool: ...
