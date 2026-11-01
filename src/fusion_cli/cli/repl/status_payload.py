"""Durum satırı betiğinin stdin JSON'u: Claude Code `statusLine` şeması (#191).

Alan adları https://code.claude.com/docs/en/statusline "Full JSON schema" ile aynıdır.
Claude'da olmayan bilgiler (motor, izin kipi, kademe, çağrı sayısı) `fusion` anahtarı
altındadır. Belgenin "may be absent" dediği alanlar (`session_name`, `vim`, `agent`, `pr`,
`worktree`, `workspace.git_worktree`) yalnız geçerliyken yazılır. Fusion'ın ölçmediği
sayaçlar (API süresi, satır sayıları) 0, `current_usage` ilk API yanıtına kadar `null`dır.
Sır yok: yalnız model adı, yollar ve sayaçlar.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .state import ReplState
from .status_view import context_report
from .transcript_store import transcript_events_path

#: `exceeds_200k_tokens` eşiği (Claude Code ile aynı).
LARGE_CONTEXT_TOKENS = 200_000


def _model(state: ReplState) -> dict[str, Any]:
    agent = state.config.agent
    return {"id": agent.model, "display_name": agent.name or agent.model}


def _workspace(state: ReplState) -> dict[str, Any]:
    tree = state.worktree
    project = tree.origin if tree is not None else state.root
    workspace: dict[str, Any] = {
        "current_dir": str(state.root),
        "project_dir": str(project),
        "added_dirs": [str(path) for path in state.extra_roots],
    }
    if tree is not None:
        workspace["git_worktree"] = tree.name
    return workspace


def _cost(state: ReplState) -> dict[str, Any]:
    started = getattr(state, "started_at", None)
    elapsed_ms = int((time.monotonic() - started) * 1000) if isinstance(started, float) else 0
    return {
        "total_cost_usd": round(state.cost.total.cost_usd, 6),
        "total_duration_ms": max(0, elapsed_ms),
        "total_api_duration_ms": 0,
        "total_lines_added": 0,
        "total_lines_removed": 0,
    }


def _context_window(state: ReplState) -> dict[str, Any]:
    """Claude Code: sayılar EN SON API yanıtındandır, oturum birikimi değil (#191)."""
    report = context_report(state)
    last = getattr(state.cost, "last_usage", None)
    size = report.window_tokens or 0
    used = report.percent if last is not None else None
    current: dict[str, int] | None = None
    if last is not None:
        current = {
            "input_tokens": last.prompt_tokens,
            "output_tokens": last.completion_tokens,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
    return {
        "total_input_tokens": last.prompt_tokens if last is not None else 0,
        "total_output_tokens": last.completion_tokens if last is not None else 0,
        "context_window_size": size,
        "used_percentage": used,
        "remaining_percentage": None if used is None else max(0, 100 - used),
        "current_usage": current,
    }


def _optional(state: ReplState) -> dict[str, Any]:
    """Belgede "may be absent" olan alanlar: yalnız geçerliyken yazılır."""
    extra: dict[str, Any] = {}
    if state.conversation_name:
        extra["session_name"] = state.conversation_name
    if getattr(state.config.runtime, "vim_mode", False):
        extra["vim"] = {"mode": str(getattr(state, "vim_state", "") or "INSERT")}
    persona = getattr(state, "persona", None)
    if persona is not None:
        extra["agent"] = {"name": persona.name}
    link = state.linked_pr
    if link is not None:
        extra["pr"] = {"number": link.number, "url": link.url}
    tree = state.worktree
    if tree is not None:
        extra["worktree"] = {
            "name": tree.name,
            "path": str(tree.path),
            "branch": tree.branch,
            "original_cwd": str(tree.origin),
        }
    return extra


def _fusion(state: ReplState) -> dict[str, Any]:
    tier = next(
        (item.name for item in state.config.tiers if item.agent.model == state.config.agent.model),
        "",
    )
    total = state.cost.total
    return {
        "tier": tier,
        "engine": state.engine.value,
        "approval_mode": state.approval.value,
        "calls": state.cost.calls,
        "total_tokens": total.prompt_tokens + total.completion_tokens,
    }


def claude_status_payload(state: ReplState, *, version: str) -> dict[str, Any]:
    """Claude Code şemasında durum satırı yükü."""
    context = _context_window(state)
    effort = getattr(state.config.runtime, "reasoning_effort", None)
    style = str(getattr(state.config.runtime, "output_style", "") or "default")
    payload: dict[str, Any] = {
        "cwd": str(state.root),
        "session_id": state.conversation_id,
        "transcript_path": str(_transcript(state)),
        "model": _model(state),
        "workspace": _workspace(state),
        "version": version,
        "output_style": {"name": style},
        "cost": _cost(state),
        "context_window": context,
        "exceeds_200k_tokens": (
            context["total_input_tokens"] + context["total_output_tokens"] > LARGE_CONTEXT_TOKENS
        ),
        "fast_mode": False,
        "thinking": {"enabled": bool(getattr(state, "show_thinking", False))},
    }
    if effort is not None:
        payload["effort"] = {"level": str(getattr(effort, "value", effort))}
    payload.update(_optional(state))
    payload["fusion"] = _fusion(state)
    return payload


def _transcript(state: ReplState) -> Path:
    return transcript_events_path(state.config.memory_dir, state.root)
