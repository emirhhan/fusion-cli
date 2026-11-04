"""Bounded public UI tool history; these records never enter model history."""

from __future__ import annotations

import json
import math
import re
import shlex
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
from ..core.redaction import contains_sensitive, redact
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


MAX_COMMAND_TOKENS = 1024
_MAX_NESTED_SHELLS = 3
_RAW_CREDENTIAL_FILE = re.compile(
    r"(?i)(?:\.env(?:\b|[._-])|\.(?:netrc|curlrc|npmrc|pypirc|git-credentials)\b|"
    r"\b(?:id_rsa|id_ed25519|id_ecdsa|id_dsa|application_default_credentials\.json)\b|"
    r"\.(?:pem|key|p12|pfx)\b)"
)
_ENV_SOURCE = re.compile(
    r"(?i)\b(?:os\s*\.\s*(?:environ|getenv)|"
    r"process\s*\.\s*env|deno\s*\.\s*env)\b|\$ENV\b"
)
_CREDENTIAL_VALUE = re.compile(
    r"(?i)(?:\$\{?[A-Z0-9_]{0,128}(?:TOKEN|SECRET|PASSWORD|PASSWD|COOKIE|CREDENTIAL|API_KEY|ACCESS_KEY|PRIVATE_KEY)[A-Z0-9_]{0,128}|"
    r"\b[A-Z0-9_-]{0,128}(?:TOKEN|SECRET|PASSWORD|PASSWD|COOKIE|CREDENTIAL|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|AUTHORIZATION)[A-Z0-9_-]{0,128}\s*[:=])"
)
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish", "pwsh", "powershell", "cmd"})
_CURL_CREDENTIAL_OPTIONS = (
    "--user",
    "--proxy-user",
    "--netrc",
    "--netrc-file",
    "--netrc-optional",
    "--config",
    "--cookie",
    "--oauth2-bearer",
    "--aws-sigv4",
    "--key",
    "--cert",
    "--pass",
)
# Stop at an option which consumes the remainder as its value, such as -opublic.txt.
_CURL_VALUE_OPTIONS = frozenset("AbcCdDeEFHIKmNoPQrTtwxXyYz")


def _shell_tokens(command: str) -> list[str] | None:
    """Lex punctuation and quotes, without expanding or executing any shell syntax."""
    if len(command) > MAX_CAPTURE_CHARS:
        return None
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens: list[str] = []
    try:
        for token in lexer:
            if len(tokens) >= MAX_COMMAND_TOKENS or len(token) > 16000:
                return None
            tokens.append(token)
    except ValueError:
        return None
    return tokens


def _command_sensitive(command: str, depth: int = 0) -> bool:
    if len(command) > MAX_CAPTURE_CHARS:
        return True
    if (
        contains_sensitive(command)
        or _RAW_CREDENTIAL_FILE.search(command)
        or _ENV_SOURCE.search(command)
        or _CREDENTIAL_VALUE.search(command)
    ):
        return True
    tokens = _shell_tokens(command)
    if tokens is None:
        return True  # Malformed or over-budget commands have no safe history preview.
    if any(_credential_path(token) for token in tokens):
        return True
    for index, token in enumerate(tokens):
        name = token.replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")
        rest: list[str] = []
        for value in tokens[index + 1 :]:
            if value and all(char in ";|&()<>" for char in value):
                break
            rest.append(value)
        if name == "printenv" or (name == "set" and not rest):
            return True
        if name == "export" and (not rest or "-p" in rest):
            return True
        if name == "env":
            remaining = iter(rest)
            found_command = False
            for value in remaining:
                if value in {"-u", "--unset", "-C", "--chdir", "-a", "--argv0"}:
                    next(remaining, None)
                elif value in {"-S", "--split-string"}:
                    return True
                elif not value.startswith("-") and "=" not in value:
                    found_command = True
                    break
            if not found_command:
                return True
        if name in _SHELLS:
            for offset, value in enumerate(rest):
                command_option = (
                    value.startswith("-") and not value.startswith("--") and "c" in value[1:]
                ) or value.casefold() in {"--command", "-command", "/c"}
                if command_option:
                    if offset + 1 >= len(rest) or depth >= _MAX_NESTED_SHELLS:
                        return True
                    script = rest[offset + 1]
                    if "$" in script or "`" in script or _command_sensitive(script, depth + 1):
                        return True
        if name != "curl":
            continue
        for value in rest:
            if "$" in value or "`" in value:
                return True
            if value.startswith("--"):
                option = value.split("=", 1)[0].casefold()
                if len(option) >= 3 and any(
                    credential.startswith(option) for credential in _CURL_CREDENTIAL_OPTIONS
                ):
                    return True
            elif value.startswith("-"):
                for option in value[1:]:
                    if option in {"u", "U", "n", "K", "b", "E"}:
                        return True
                    if option in _CURL_VALUE_OPTIONS:
                        break
    return False


def _credential_path(path: str) -> bool:
    name = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].strip("\"'").casefold()
    return (
        name
        in {
            ".env",
            ".envrc",
            ".netrc",
            ".curlrc",
            ".npmrc",
            ".pypirc",
            ".git-credentials",
            "credentials",
            "credentials.json",
            "secrets.json",
            "secrets.toml",
            "application_default_credentials.json",
        }
        or name.startswith((".env.", "credentials."))
        or (
            name.startswith(("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"))
            and not name.endswith(".pub")
        )
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def _credential_target(args: dict[str, object]) -> tuple[bool, bool]:
    """Return (sensitive content, sensitive command), without evaluating arguments."""
    pending: list[object] = [args]
    sensitive_file = False
    for _ in range(64):
        if not pending:
            return sensitive_file, False
        value = pending.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"path", "yol", "file_path", "file", "filename"} and isinstance(
                    item, str
                ):
                    if _credential_path(item):
                        sensitive_file = True
                elif key in {"command", "komut"} and isinstance(item, str):
                    if _command_sensitive(item):
                        return True, True
                elif isinstance(item, dict | list):
                    pending.append(item)
        elif isinstance(value, list):
            pending.extend(value[:64])
            if len(value) > 64:
                return True, True
    if pending:
        return True, True  # Uninspectably complex arguments fail closed for all content.
    return sensitive_file, False


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
    hidden: list[str] = []
    sensitive_target, sensitive_command = _credential_target(args)
    safe_args: dict[str, object] = {}
    if sensitive_command:
        hidden.append("args")
        for key in ("command", "komut"):
            if key in args:
                safe_args[key] = "[Hassas komut geçmişten gizlendi.]"
    budget = 8000
    for key, value in args.items():
        if sensitive_command:
            break
        if key not in _ARG_KEYS:
            continue
        if isinstance(value, str):
            if sensitive_target and key not in {"path", "yol", "file_path"}:
                safe_args[key] = "[Hassas ayrıntı geçmişten gizlendi.]"
                hidden.append(f"args.{key}")
                continue
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
            if sensitive_target:
                payload[field] = (
                    "[Hassas içerik geçmişe kaydedilmedi.]" if field == "output" else None
                )
                hidden.append(field)
                continue
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
            value
            for value in prior[:16]
            if isinstance(value, str)
            and value in {"output", "diff", "args", *(f"args.{key}" for key in _ARG_KEYS)}
        )
    if truncated:
        payload["history_truncated"] = list(dict.fromkeys(truncated))[:16]
    prior_hidden = raw.get("history_redacted")
    if isinstance(prior_hidden, list):
        hidden.extend(
            value
            for value in prior_hidden[:16]
            if isinstance(value, str)
            and value in {"output", "diff", "args", *(f"args.{key}" for key in _ARG_KEYS)}
        )
    if hidden:
        payload["history_redacted"] = list(dict.fromkeys(hidden))[:16]
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


def _bounded_row(row: dict[str, object], session_id: str) -> tuple[dict[str, object] | None, bool]:
    if row.get("rol") == "olay":
        raw = row.get("olay")
        payload = public_tool_payload(raw, session_id=session_id)
        if payload is None:
            return None, False
        # Preserve the legacy RAM presenter shape when identity was unavailable.
        if isinstance(raw, dict) and "session_id" not in raw:
            payload.pop("session_id", None)
        projected = {**row, "olay": payload}
        return projected, bool(payload.get("history_truncated"))
    text = row.get("metin")
    if row.get("rol") not in {"kullanici", "asistan"} or not isinstance(text, str):
        return None, False
    safe = redact(text)
    projected = {**row, "metin": _clip(safe, 16000)}
    truncated = len(safe) > 16000
    # Findings are an optional structured card, never an exemption from the row budget.
    if len(json.dumps(projected, ensure_ascii=False)) > MAX_ROW_BYTES:
        projected.pop("bulgular", None)
        truncated = True
    return projected, truncated


def project_visible_history(
    store: TranscriptStore, messages: Sequence[Message]
) -> VisibleTranscript:
    """The same finite projection applies to legacy RAM and imported history."""
    rows: list[dict[str, object]] = []
    sizes: list[int] = []
    total = 0
    truncated = len(messages) > MAX_ROWS
    for row in visible_history(messages[-MAX_ROWS:]):
        projected, limited = _bounded_row(row, store.session_id)
        truncated |= limited
        if projected is None:
            continue
        size = len(json.dumps(projected, ensure_ascii=False))
        rows.append(projected)
        sizes.append(size)
        total += size
        while len(rows) > MAX_ROWS or total > MAX_TOTAL_CHARS:
            rows.pop(0)
            total -= sizes.pop(0)
            truncated = True
    return VisibleTranscript(rows, False, truncated)


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
        return project_visible_history(store, fallback)
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
        if not isinstance(event, str):
            continue
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
            # Apply the common row projection below, including truncation metadata.
        else:
            continue  # No token streams, raw legacy tools, or other private events.
        projected, limited = _bounded_row(row, store.session_id)
        truncated |= limited
        if projected is None:
            continue
        row = projected
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
    if durable:
        return VisibleTranscript(rows, True, truncated)
    fallback_view = project_visible_history(store, fallback)
    return VisibleTranscript(fallback_view.rows, False, truncated or fallback_view.truncated)
