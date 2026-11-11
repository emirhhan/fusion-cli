"""Sanitized timing from a frozen case's private trace and timestamped stdio."""

from __future__ import annotations

import json
from collections.abc import Collection, Iterator, Mapping
from pathlib import Path
from typing import Any

from fusion_cli.core.types import is_rate_limit_error

_MAX_LINE = 16 * 1024 * 1024
_MAX_ROWS = 10_000
_MAX_ELAPSED_MS = 2**31 - 1
_TERMINAL = ("call_end", "call_error", "call_cancelled")
_WAIT_START = ("rate_wait", "provider_retry_wait")
_MCP_PHASES = (
    "catalog_preparation",
    "selected_connection_wait",
    "selected_schema_discovery",
    "runtime_publication",
    "explicit_reference_expansion",
)
_TOOLS = (
    "read_file",
    "write_file",
    "edit_file",
    "multi_edit",
    "list_dir",
    "glob",
    "grep_search",
    "run_shell",
)
_OUTCOMES = ("ok", "failed", "blocked", "denied")


class _TimingLimitExceededError(ValueError):
    pass


def private_trace_dir(home: Path, env: Mapping[str, str]) -> Path | None:
    """Read only the existing trace location under the runner-owned home."""
    if any(env.get(name) for name in ("FUSION_MEMORY_DIR", "XDG_DATA_HOME", "FUSION_ACCOUNT")):
        return None
    return home / ".local/share/fusion-cli/memory/traces"


def trace_files(directory: Path | None) -> set[Path]:
    try:
        if directory is not None and not any(
            path.is_symlink() for path in (directory, *directory.parents)
        ):
            return {
                path
                for path in directory.glob("*.jsonl")
                if path.is_file() and not path.is_symlink()
            }
    except OSError:
        pass
    return set()


def _rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("rb") as stream:
        for _ in range(_MAX_ROWS):
            line = stream.readline(_MAX_LINE + 1)
            if not line:
                return
            if len(line) > _MAX_LINE:
                raise _TimingLimitExceededError
            try:
                item = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if isinstance(item, dict):
                yield item
        if stream.read(1):
            raise _TimingLimitExceededError


def _ms(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= _MAX_ELAPSED_MS else None


def _clock_ms(value: object) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 10**12:
        return round(value * 1000)
    return None


def _id(value: object) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= 256 else None


def _tool_category(name: str) -> str:
    if name.startswith("mcp__"):
        return "mcp"
    return name if name in _TOOLS else "other"


class _ProviderTiming:
    def __init__(self) -> None:
        self.calls: set[str] = set()
        self.terminals: dict[str, int] = {}
        self.pending: dict[str, tuple[str, int, int | None, str]] = {}
        self.waits: list[dict[str, object]] = []

    def add(self, row: dict[str, Any]) -> None:
        call = _id(row.get("call_id"))
        elapsed = _ms(row.get("elapsed_ms"))
        phase = row.get("phase")
        if call is None or elapsed is None or call in self.terminals:
            return
        if phase == "call_enter":
            self.calls.add(call)
        if call not in self.calls:
            return
        if phase in _WAIT_START:
            kind = "rate_pacing" if phase == "rate_wait" else "provider_retry"
            if phase == "provider_retry_wait" and row.get("wait_reason") == "rate_limit":
                kind = "rate_limited_retry"
            self.pending[call] = (kind, elapsed, _ms(row.get("wait_ms")), f"{phase}_end")
        elif phase in _TERMINAL:
            self.terminals[call] = elapsed
            self._finish_wait(call, elapsed, complete=False)
        elif call in self.pending and phase == self.pending[call][3]:
            self._finish_wait(call, elapsed, complete=True)

    def _finish_wait(self, call: str, elapsed: int, *, complete: bool) -> None:
        pending = self.pending.pop(call, None)
        if pending is not None:
            kind, start, requested, _ = pending
            if elapsed >= start:
                self.waits.append(
                    {
                        "kind": kind,
                        "requested_ms": requested,
                        "observed_ms": elapsed - start,
                        "complete": complete,
                    }
                )

    def summary(self) -> dict[str, object]:
        return {
            "started": len(self.calls),
            "terminal": len(self.terminals),
            "terminal_elapsed_ms": sum(self.terminals.values()),
            "waits": self.waits,
            "unmeasured_waits": len(self.pending),
        }


def _wire_timing(events: Path) -> tuple[set[str], dict[str, int], list[dict[str, object]]]:
    turns: set[str] = set()
    model = dict.fromkeys(
        ("started", "finished", "abandoned", "reported_latency_ms", "finished_rate_limited"), 0
    )
    starts: dict[str, tuple[str, int]] = {}
    tools: list[dict[str, object]] = []
    for row in _rows(events):
        event = row.get("veri")
        if row.get("tip") != "olay" or not isinstance(event, dict):
            continue
        if (turn := _id(event.get("turn_id"))) is not None:
            turns.add(turn)
        kind = event.get("olay")
        if kind == "ModelCallStarted":
            model["started"] += 1
        elif kind == "ModelCallAbandoned":
            model["abandoned"] += 1
        elif kind == "ModelCallFinished":
            model["finished"] += 1
            result = event.get("result")
            if isinstance(result, dict):
                model["reported_latency_ms"] += _ms(result.get("latency_ms")) or 0
                error = result.get("error")
                if (
                    result.get("ok") is False
                    and isinstance(error, str)
                    and is_rate_limit_error(error[:4096])
                ):
                    model["finished_rate_limited"] += 1
        elif kind in ("ToolStarted", "ToolExecuted"):
            call = _id(event.get("call_id"))
            stamp = _clock_ms(row.get("ts"))
            name = event.get("name")
            if call is None or stamp is None or not isinstance(name, str):
                continue
            if kind == "ToolStarted":
                starts[call] = name, stamp
            else:
                start = starts.pop(call, None)
                outcome = event.get("outcome")
                if (
                    start is not None
                    and start[0] == name
                    and stamp >= start[1]
                    and outcome in _OUTCOMES
                ):
                    tools.append(
                        {
                            "tool": _tool_category(name),
                            "outcome": outcome,
                            "wire_elapsed_ms": stamp - start[1],
                        }
                    )
    return turns, model, tools


def _trace_timing(
    candidates: Collection[Path], turn: str
) -> tuple[str, _ProviderTiming, list[dict[str, object]]]:
    matched = False
    provider = _ProviderTiming()
    mcp_phases: list[dict[str, object]] = []
    for candidate in sorted(candidates):
        seen = False
        for row in _rows(candidate):
            if row.get("turn_id") != turn:
                continue
            if matched:
                return "ambiguous", _ProviderTiming(), []
            seen = True
            if row.get("event") == "ProviderCallDiagnostic":
                provider.add(row)
            if row.get("event") == "McpDiscoveryDiagnostic":
                stage, outcome, elapsed = (
                    row.get("stage"),
                    row.get("outcome"),
                    _ms(row.get("elapsed_ms")),
                )
                if (
                    stage in _MCP_PHASES
                    and outcome in ("ready", "error", "cancelled")
                    and elapsed is not None
                ):
                    mcp_phases.append({"phase": stage, "outcome": outcome, "elapsed_ms": elapsed})
        matched |= seen
    return "matched" if matched else "missing", provider, mcp_phases


def case_timing(events: Path, traces: Path | None, before: Collection[Path]) -> dict[str, object]:
    """Return diagnostic metadata only. The acceptance verifier never uses it."""
    try:
        turns, models, tools = _wire_timing(events)
        if len(turns) != 1:
            return {"schema": 1, "private_trace": "unbound"}
        status, provider, mcp_phases = _trace_timing(trace_files(traces) - set(before), turns.pop())
    except (OSError, _TimingLimitExceededError):
        return {"schema": 1, "private_trace": "unavailable"}
    return {
        "schema": 1,
        "private_trace": status,
        "model": models,
        "provider": provider.summary(),
        "tools": tools,
        "mcp_phases": mcp_phases,
    }
