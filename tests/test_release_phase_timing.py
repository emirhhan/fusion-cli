"""Frozen timing comes from the matching case and contains only bounded metadata."""

from __future__ import annotations

import json


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_frozen_timing_binds_private_provider_phases_to_timestamped_case(tmp_path):
    from evals.release_phase_timing import case_timing, private_trace_dir, trace_files

    home = tmp_path / "home"
    traces = private_trace_dir(home, {})
    assert traces is not None
    stale = _write(
        traces / "previous.jsonl",
        [{"event": "ProviderCallDiagnostic", "turn_id": "case-a", "elapsed_ms": 999}],
    )
    before = trace_files(traces)
    assert before == {stale}
    event_file = _write(
        tmp_path / "case-a.jsonl",
        [
            {
                "tip": "olay",
                "ts": 100.0,
                "veri": {"olay": "ModelCallStarted", "turn_id": "case-a"},
            },
            {
                "tip": "olay",
                "ts": 100.8,
                "veri": {
                    "olay": "ModelCallFinished",
                    "turn_id": "case-a",
                    "result": {"ok": False, "latency_ms": 800, "error": "HTTP 429 SECRET"},
                },
            },
            {
                "tip": "olay",
                "ts": 101.0,
                "veri": {
                    "olay": "ToolStarted",
                    "turn_id": "case-a",
                    "call_id": "tool-a",
                    "name": "run_shell",
                    "args": {"command": "SECRET"},
                },
            },
            {
                "tip": "olay",
                "ts": 101.25,
                "veri": {
                    "olay": "ToolExecuted",
                    "turn_id": "case-a",
                    "call_id": "tool-a",
                    "name": "run_shell",
                    "outcome": "ok",
                    "output": "SECRET",
                },
            },
            {
                "tip": "olay",
                "ts": 101.3,
                "veri": {
                    "olay": "ToolStarted",
                    "turn_id": "case-a",
                    "call_id": "tool-b",
                    "name": "mcp__SECRET__tool",
                },
            },
            {
                "tip": "olay",
                "ts": 101.5,
                "veri": {
                    "olay": "ToolExecuted",
                    "turn_id": "case-a",
                    "call_id": "tool-b",
                    "name": "mcp__SECRET__tool",
                    "outcome": "ok",
                },
            },
        ],
    )
    provider = {"event": "ProviderCallDiagnostic", "turn_id": "case-a", "call_id": "SECRET"}
    _write(
        traces / "current.jsonl",
        [
            {**provider, "phase": "call_enter", "elapsed_ms": 0},
            {
                **provider,
                "phase": "provider_retry_wait",
                "elapsed_ms": 50,
                "wait_ms": 500,
                "wait_reason": "rate_limit",
            },
            {**provider, "phase": "provider_retry_wait_end", "elapsed_ms": 575},
            {
                **provider,
                "phase": "rate_wait",
                "elapsed_ms": 600,
                "wait_ms": 100,
            },
            {**provider, "phase": "rate_wait_end", "elapsed_ms": 710},
            {**provider, "phase": "provider_retry_wait", "elapsed_ms": 750, "wait_ms": 500},
            {**provider, "phase": "call_cancelled", "elapsed_ms": 800},
            {
                "event": "McpDiscoveryDiagnostic",
                "turn_id": "case-a",
                "stage": "selected_schema_discovery",
                "elapsed_ms": 125,
                "outcome": "ready",
            },
        ],
    )
    _write(
        traces / "different-case.jsonl",
        [{**provider, "turn_id": "case-b", "phase": "call_end", "elapsed_ms": 999}],
    )

    result = case_timing(event_file, traces, before)
    assert result["private_trace"] == "matched"
    assert result["model"]["reported_latency_ms"] == 800
    assert result["model"]["finished_rate_limited"] == 1
    assert result["provider"]["terminal_elapsed_ms"] == 800
    assert result["provider"]["waits"] == [
        {"kind": "rate_limited_retry", "requested_ms": 500, "observed_ms": 525, "complete": True},
        {"kind": "rate_pacing", "requested_ms": 100, "observed_ms": 110, "complete": True},
        {"kind": "provider_retry", "requested_ms": 500, "observed_ms": 50, "complete": False},
    ]
    assert result["tools"] == [
        {"tool": "run_shell", "outcome": "ok", "wire_elapsed_ms": 250},
        {"tool": "mcp", "outcome": "ok", "wire_elapsed_ms": 200},
    ]
    assert result["mcp_phases"] == [
        {"phase": "selected_schema_discovery", "elapsed_ms": 125, "outcome": "ready"}
    ]
    assert "SECRET" not in json.dumps(result)


def test_case_does_not_read_foreign_or_ambiguous_trace(tmp_path):
    from evals.release_phase_timing import case_timing, private_trace_dir

    assert private_trace_dir(tmp_path / "home", {"FUSION_MEMORY_DIR": str(tmp_path)}) is None
    events = _write(
        tmp_path / "mixed.jsonl",
        [{"tip": "olay", "veri": {"olay": "ToolStarted", "turn_id": key}} for key in ("a", "b")],
    )
    assert case_timing(events, tmp_path, set())["private_trace"] == "unbound"
