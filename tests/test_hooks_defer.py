"""PreToolUse `defer` (#114): `-p`'de tur `tool_deferred` ile biter, çağrı sonuçta ve dökümde."""

from __future__ import annotations

import json

from fusion_cli.cli import headless
from fusion_cli.core.hooks.events import HookEvent
from fusion_cli.engines.hooks.transcript import HookTranscript
from fusion_cli.observability.cost import CostTracker

from .test_hooks_loop import _kanca, _oturum, _tur, _yaz

_DEFER = (
    "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',"
    " 'permissionDecision': 'defer'}}))\n"
)


async def test_defer_turu_bitirir_cagriyi_sonuca_tasir(monkeypatch, tmp_path):
    session = _oturum(tmp_path, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _DEFER, "Write"))
    session.transcript_dir = tmp_path / "dokum"

    outcome, provider, _prompter, _sink = await _tur(monkeypatch, tmp_path, _yaz("a.txt"), session)

    assert outcome.stop_reason == "tool_deferred"
    deferred = outcome.deferred_tool_use
    assert deferred is not None
    assert deferred["name"] == "Write"
    assert deferred["input"]["file_path"] == str(tmp_path / "a.txt")
    assert not (tmp_path / "a.txt").exists()
    assert len(provider.seen_requests) == 1  # model yeniden çağrılmadı
    transcript = session.transcript()
    assert isinstance(transcript, HookTranscript)
    rows = [json.loads(line) for line in transcript.path.read_text().splitlines()]
    kinds = [
        block.get("type")
        for row in rows
        for block in (row.get("message", {}).get("content") or [])
        if isinstance(block, dict)
    ]
    assert "tool_use" in kinds and "tool_result" not in kinds


def test_json_sonucu_deferred_tool_use_alani():
    call = {"id": "c1", "name": "Bash", "input": {"command": "ls"}}
    result = headless.result_object(
        final_text="tool_deferred",
        ok=True,
        budget_stopped=False,
        stop_reason="tool_deferred",
        model_calls=1,
        cost=CostTracker(),
        structured=None,
        deferred_tool_use=call,
    )
    assert result["durma_nedeni"] == "tool_deferred"
    assert result["deferred_tool_use"] == call
