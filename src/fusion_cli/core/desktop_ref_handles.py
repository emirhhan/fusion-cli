"""Bounded, in-memory presentation aliases for native AX references.

Aliases convey no authority. Resolution restores the exact native token before
policy, approval, recovery or execution; the native helper still validates it.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tools import ToolArgs, ToolContext

Scope = tuple[object, str, str, int]
INVALID_REF = "Öğe başvurusu geçersiz veya süresi dolmuş; hedef pencereyi yeniden incele."


@dataclass(frozen=True, slots=True)
class _Entry:
    scope: Scope
    pid: int
    window: int
    ref: str
    expires: float


class DesktopRefHandles:
    """Owned by DesktopView, never shared through a process-global cache."""

    def __init__(
        self,
        *,
        max_entries: int = 2000,
        max_bytes: int = 4_000_000,
        ttl_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._entries: dict[str, _Entry] = {}
        self._inspections: dict[tuple[Scope, int, int], tuple[object, float]] = {}
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._inspections.clear()

    def _prune(self) -> None:
        now = self._clock()
        self._entries = {key: entry for key, entry in self._entries.items() if entry.expires > now}
        self._inspections = {
            key: inspection for key, inspection in self._inspections.items() if inspection[1] > now
        }

    @property
    def entry_count(self) -> int:
        with self._lock:
            self._prune()
            return len(self._entries)

    def begin_inspection(self, scope: Scope, pid: int, window: int) -> object:
        """Revoke old refs before dispatch and issue a bounded latest-request ticket."""
        with self._lock:
            self._prune()
            key = (scope, pid, window)
            if key not in self._inspections and len(self._inspections) >= self._max_entries:
                raise ValueError(INVALID_REF)
            self._entries = {
                key: entry
                for key, entry in self._entries.items()
                if (entry.scope, entry.pid, entry.window) != (scope, pid, window)
            }
            ticket = object()
            self._inspections[key] = (ticket, self._clock() + self._ttl)
            return ticket

    def observe(
        self,
        scope: Scope,
        pid: int,
        window: int,
        refs: Sequence[str],
        *,
        ticket: object | None = None,
    ) -> list[str]:
        with self._lock:
            self._prune()
            if ticket is not None:
                inspection = self._inspections.get((scope, pid, window))
                if inspection is None or inspection[0] is not ticket:
                    raise ValueError(INVALID_REF)
                del self._inspections[(scope, pid, window)]
            retained = {
                key: entry
                for key, entry in self._entries.items()
                if (entry.scope, entry.pid, entry.window) != (scope, pid, window)
            }
            size = sum(len(entry.ref.encode("utf-8")) for entry in retained.values())
            size += sum(len(ref.encode("utf-8")) for ref in refs)
            if len(retained) + len(refs) > self._max_entries or size > self._max_bytes:
                self._entries = retained
                raise ValueError(INVALID_REF)
            aliases = []
            expires = self._clock() + self._ttl
            for ref in refs:
                alias = "dref_" + secrets.token_hex(10)
                while alias in retained:
                    alias = "dref_" + secrets.token_hex(10)
                retained[alias] = _Entry(scope, pid, window, ref, expires)
                aliases.append(alias)
            self._entries = retained
            return aliases

    def resolve(self, alias: str, scope: Scope, pid: int, window: int) -> str:
        with self._lock:
            self._prune()
            entry = self._entries.get(alias)
            if entry is None or (entry.scope, entry.pid, entry.window) != (scope, pid, window):
                raise ValueError(INVALID_REF)
            return entry.ref


def context_scope(context: ToolContext) -> Scope:
    return (
        context.desktop_ref_owner,
        context.job_scope,
        context.desktop.observation_turn_id,
        id(context.desktop.turn),
    )


def canonical_arguments(tool_name: str, args: ToolArgs, context: ToolContext) -> ToolArgs:
    """Unknown aliases fail closed; legacy full native references pass unchanged."""
    ref = args.get("ref")
    if (
        tool_name != "desktop_background_action"
        or not isinstance(ref, str)
        or not ref.startswith("dref_")
    ):
        return args
    # Match the action boundary's strict integer coercion (including rejection of bool).
    from ..tools.args import coerce_int

    pid, window = coerce_int(args.get("pid")), coerce_int(args.get("window_id"))
    if pid is None or window is None or pid <= 0 or window <= 0:
        raise ValueError(INVALID_REF)
    canonical = context.desktop.ref_handles.resolve(ref, context_scope(context), pid, window)
    return {**args, "ref": canonical}
