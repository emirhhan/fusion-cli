"""Bounded public UI tool history; these records never enter model history."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import uuid4

from ..cli.repl import code_review_findings
from ..cli.repl.transcript_store import (
    TranscriptStore,
    _conversation_digest,
    _deleted_conversations,
)
from ..core.leak_filter import is_harness_note, strip_harness_leaks
from ..core.redaction import redact
from ..core.types import Message
from .history_view import _text_row, visible_history

TOOL_EVENT = "VisibleToolExecuted"
CLEAR_EVENT = "VisibleHistoryCleared"
LIMIT_EVENT = "VisibleHistoryLimited"
VERSION = 1
MAX_CAPTURE_CHARS = 2_000_000
MAX_FIELD = 4000
MAX_ROWS = 300
MAX_READ_BYTES = 8 * 1024 * 1024
MAX_ROW_BYTES = 128 * 1024
MAX_TOTAL_CHARS = 1_000_000
_ARG_KEYS = frozenset(
    {
        "command",
        "komut",
        "path",
        "yol",
        "url",
        "query",
        "pattern",
        "selector",
        "text",
        "app",
        "application",
        "name",
        "key",
        "title",
        "x",
        "y",
        "target",
        "action",
        "method",
        "file_path",
        "url_pattern",
    }
)
_OUTCOMES = frozenset({"ok", "failed", "unknown", "denied", "blocked"})


def _clip(value: str, limit: int = MAX_FIELD) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _version_matches(record: dict[str, object]) -> bool:
    value = record.get("visible_version")
    return type(value) is int and value == VERSION


def public_tool_payload(raw: object, *, session_id: str) -> dict[str, object] | None:
    """Allowlist scalars, redact before clipping, and validate identity on every read."""
    if not isinstance(raw, dict) or raw.get("olay") != "ToolExecuted" or raw.get("agent_id"):
        return None
    if raw.get("session_id") not in (None, session_id):
        return None
    name, outcome, output = raw.get("name"), raw.get("outcome"), raw.get("output")
    if not isinstance(name, str) or not name or len(name) > 256:
        return None
    if not isinstance(outcome, str) or outcome not in _OUTCOMES or not isinstance(output, str):
        return None
    args = raw.get("args")
    if not isinstance(args, dict):
        return None
    truncated: list[str] = []
    safe_args: dict[str, object] = {}
    budget = 8000
    for key, value in args.items():
        if key not in _ARG_KEYS:
            continue
        if isinstance(value, str):
            safe = redact(value)
            limit = min(MAX_FIELD, budget)
            if limit <= 0:
                truncated.append("args")
                break
            if len(safe) > limit:
                truncated.append(f"args.{key}")
            safe_args[key] = _clip(safe, limit)
            budget -= len(str(safe_args[key]))
        elif (
            value is None
            or isinstance(value, bool)
            or (isinstance(value, int) and abs(value) <= 2**53)
            or (isinstance(value, float) and math.isfinite(value))
        ):
            safe_args[key] = value
    payload: dict[str, object] = {
        "olay": "ToolExecuted",
        "name": redact(name),
        "args": safe_args,
        "outcome": outcome,
        "diff": None,
    }
    for field in ("output", "diff"):
        value = raw.get(field)
        if field == "diff" and outcome != "ok":
            continue
        if isinstance(value, str):
            safe = redact(value)
            if len(safe) > MAX_FIELD:
                truncated.append(field)
            payload[field] = _clip(safe)
    for key in ("event_id", "call_id", "attempt_id", "turn_id"):
        value = raw.get(key)
        if isinstance(value, str) and value and len(value) <= 256:
            payload[key] = redact(value)
    payload["session_id"] = session_id
    prior = raw.get("history_truncated")
    if isinstance(prior, list):
        truncated.extend(
            value for value in prior[:16] if isinstance(value, str) and len(value) < 80
        )
    if truncated:
        payload["history_truncated"] = list(dict.fromkeys(truncated))[:16]
    return payload


class VisibleToolRecorder:
    """Capture only the serialized public ToolExecuted envelope of one owned turn."""

    def __init__(
        self, store: TranscriptStore, *, active: Callable[[], bool], turn_id: str | None = None
    ) -> None:
        self._store, self._active = store, active
        self._turn_id = turn_id
        self._prefix = uuid4().hex
        self._seen: set[str] = set()
        self._count = 0
        self._limited = False

    def _mark_limit(self) -> None:
        if not self._limited:
            self._store.record_visible_limit()
            self._limited = True

    def record(self, line: str) -> None:
        if not self._active():
            return
        if len(line) > MAX_CAPTURE_CHARS:
            self._mark_limit()
            return
        try:
            envelope = json.loads(line)
        except (ValueError, RecursionError):
            return
        if not isinstance(envelope, dict) or envelope.get("tip") != "olay":
            return
        raw = envelope.get("veri")
        payload = public_tool_payload(raw, session_id=self._store.session_id)
        if payload is None:
            return
        if self._turn_id is not None and payload.get("turn_id") != self._turn_id:
            return
        identifier = str(payload.get("event_id") or f"{self._prefix}:{self._count}")
        if identifier in self._seen:
            return
        # A single turn cannot allocate unbounded identity bookkeeping.
        if self._count >= MAX_ROWS:
            self._mark_limit()
            return
        self._seen.add(identifier)
        self._count += 1
        if self._active():
            self._store.record_visible_tool(payload, identifier=identifier)


@dataclass(frozen=True)
class VisibleTranscript:
    rows: list[dict[str, object]]
    durable: bool
    truncated: bool = False


def load_visible_transcript(
    store: TranscriptStore, fallback: Sequence[Message]
) -> VisibleTranscript:
    """Read a bounded tail in append order, scoped to one project and conversation."""
    if _conversation_digest(store.session_id) in _deleted_conversations(store.events_path.parent):
        return VisibleTranscript([], True)
    try:
        with store.events_path.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - MAX_READ_BYTES))
            if size > MAX_READ_BYTES:
                stream.readline()  # Discard the partial leading JSONL record.
            data = stream.read(MAX_READ_BYTES)
    except OSError:
        return VisibleTranscript(visible_history(fallback), False)
    rows: list[dict[str, object]] = []
    sizes: list[int] = []
    total_chars = 0
    dropped_users = 0
    findings_turn = False
    durable, truncated = False, size > MAX_READ_BYTES
    for line in data.splitlines():
        if len(line) > MAX_ROW_BYTES:
            truncated = True
            continue
        try:
            record = json.loads(line)
        except (ValueError, UnicodeError, RecursionError):
            continue
        if not isinstance(record, dict) or record.get("session_id") != store.session_id:
            continue
        event = record.get("event")
        if event == CLEAR_EVENT and _version_matches(record):
            rows.clear()
            sizes.clear()
            total_chars = 0
            dropped_users = 0
            findings_turn = False
            truncated = False
            durable = True
            continue
        if event == LIMIT_EVENT and _version_matches(record):
            durable, truncated = True, True
            continue
        if event == "ConversationRewound":
            keep = record.get("keep_users")
            if isinstance(keep, int) and not isinstance(keep, bool) and keep >= 0:
                # A bounded tail can start after the absolute user counter. When
                # the file prefix is unavailable, discard uncertain pre-rewind rows.
                if size > MAX_READ_BYTES or keep < dropped_users:
                    rows.clear()
                    sizes.clear()
                    total_chars = 0
                    dropped_users = keep
                    continue
                users = dropped_users
                for index, row in enumerate(rows):
                    if row.get("rol") == "kullanici":
                        if users == keep:
                            del rows[index:]
                            total_chars -= sum(sizes[index:])
                            del sizes[index:]
                            break
                        users += 1
            continue
        if event == TOOL_EVENT:
            if not _version_matches(record):
                continue
            payload = public_tool_payload(record.get("payload"), session_id=store.session_id)
            identifier = record.get("visible_id")
            if (
                payload is None
                or not isinstance(identifier, str)
                or not identifier
                or len(identifier) > 256
                or (payload.get("event_id") is not None and payload["event_id"] != identifier)
            ):
                continue
            row = {"rol": "olay", "olay": payload, "id": identifier}
            durable = True
        elif event in {"UserMessage", "TurnAnswered"}:
            text = record.get("text")
            if (
                not isinstance(text, str)
                or not text.strip()
                or (event == "UserMessage" and is_harness_note(text))
            ):
                continue
            safe = strip_harness_leaks(redact(text))
            if not safe:
                continue
            if event == "UserMessage":
                findings_turn = code_review_findings.is_findings_turn(safe)
            identifier = record.get("message_id")
            row = _text_row(
                Message(
                    "user" if event == "UserMessage" else "assistant",
                    safe,
                    message_id=identifier
                    if isinstance(identifier, str) and 0 < len(identifier) <= 256
                    else None,
                ),
                findings_turn,
            )
            row["metin"] = _clip(str(row["metin"]), 16000)
        else:
            continue  # No token streams, raw legacy tools, or other private events.
        identifier = row.get("id")
        existing = next(
            (i for i, item in enumerate(rows) if identifier and item.get("id") == identifier), None
        )
        row_size = len(json.dumps(row, ensure_ascii=False))
        if existing is not None:
            total_chars -= sizes[existing]
            rows[existing], sizes[existing] = row, row_size
        else:
            rows.append(row)
            sizes.append(row_size)
        total_chars += row_size
        while len(rows) > MAX_ROWS or total_chars > MAX_TOTAL_CHARS:
            removed = rows.pop(0)
            if removed.get("rol") == "kullanici":
                dropped_users += 1
            total_chars -= sizes.pop(0)
            truncated = True
    return VisibleTranscript(rows if durable else visible_history(fallback), durable, truncated)
