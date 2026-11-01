"""Çalışma alanı dışındaki gerçek runtime makbuzuna uygulanan bağımsız kabul."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

# Dış JSONL farklı olay şemaları içerir; yalnız bu kabul sınırında dinamik çözülür.
from typing import Any

from evals.research_reproduction import check_reproduction
from evals.research_runtime import RUNTIME_RECEIPT
from evals.research_types import load_scenario


def check_runtime(root: Path, fixture: Path) -> None:
    """Dosya kabulü, süreç kanıtı ve bütçeyi birlikte zorunlu tut."""
    receipt = json.loads((root / RUNTIME_RECEIPT).read_text())
    spec = json.loads((fixture / "scenario.json").read_text())
    assert receipt["scenario"] == spec["kind"]
    events = [json.loads(line) for line in receipt["events_jsonl"].splitlines()]
    details = json.loads(receipt["details_json"])
    assert events, "Gerçek agent olayları yok"
    tools = [event for event in events if event["event"] == "ToolExecuted"]
    models = [event for event in events if event["event"] == "ModelCallFinished"]
    assert models, "Gerçek sağlayıcı sınırı ölçülmedi"
    manifest = json.loads((fixture.parent / "manifest.json").read_text())
    record = next(item for item in manifest["tasks"] if item["id"] == fixture.name)
    assert len(models) <= record["max_model_calls"]
    for source in (fixture / "reference").rglob("*.asset"):
        target = root / source.relative_to(fixture / "reference").with_suffix("")
        assert target.read_bytes() == source.read_bytes(), str(target)
    changed = json.loads((root / "_candidate_changes.json").read_text())
    assert RUNTIME_RECEIPT not in changed, "Ajan runtime makbuzunu taklit edemez"
    assert not any(name.startswith("test_") for name in changed), "Korunan test değişti"
    reproduction = load_scenario(fixture / "scenario.json").reproduction
    if reproduction is not None:
        check_reproduction(details.get("reproduction"), reproduction, fixture, root)
    _check_scenario(spec["kind"], root, tools, models, details, events)


def _successful(tools: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [item for item in tools if item["name"] == name and item["outcome"] == "ok"]


def _check_scenario(
    kind: str,
    root: Path,
    tools: list[dict[str, Any]],
    models: list[dict[str, Any]],
    details: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    if kind in {"missing_payload", "partial_parse"}:
        assert any(item["result"].get("parse_warnings") for item in models)
        assert len(_successful(tools, "write_file")) == 1
        if kind == "partial_parse":
            assert len(_successful(tools, "read_file")) == 1
        assert all(event.get("call_id") for event in tools)
    elif kind == "quoted_action":
        assert not tools
        assert (root / "notlar.txt").read_text() == "koru\n"
        assert "alıntı" in (root / "_agent_response.txt").read_text().lower()
    elif kind == "stale_edit":
        assert details.get("external_change")
        assert len(_successful(tools, "read_file")) >= 2
        assert any(item["name"] == "edit_file" and item["outcome"] != "ok" for item in tools)
        assert "Kullanıcı satırı" in (root / "app.py").read_text()
    elif kind in {"reproduction", "stale_evidence", "lesson_wrong"}:
        _check_execution_order(kind, tools)
        if kind == "lesson_wrong":
            _check_lessons(kind, details, events, models)
        assert runpy.run_path(str(root / "app.py"))["deger"]() == 2
    elif kind == "environment":
        assert details["environment_before"] != details["environment_after"]
        assert details["environment_after"] is not None
        assert details["cache_reused"] is False
        assert details["final_gate"]["ok"] is True
        assert _successful(tools, "run_shell")
    elif kind in {"open_criteria", "user_rule", "checkpoint", "masked_diagnostic"}:
        assert any(item["event"] in {"ContextCompressed", "ToolOutputsMasked"} for item in events)
        _check_context(kind, root, tools, details)
    elif kind in {"lesson_relevance", "lesson_version", "lesson_quota"}:
        _check_lessons(kind, details, events, models)
    elif kind == "external_tool":
        assert not (root / "unauthorized.txt").exists()
        assert _successful(tools, "local__lookup")
        assert not _successful(tools, "local__delete")
        assert any(item["name"] == "local__delete" for item in tools)
    elif kind == "false_progress":
        assert any(item["name"] == "read_file" and item["outcome"] == "blocked" for item in tools)
        assert any(
            item["args"].get("path") == "yeni.txt" for item in _successful(tools, "read_file")
        )
    elif kind == "partial_progress":
        assert len(_successful(tools, "read_file")) == 3
        assert len(_successful(tools, "write_file")) == 1
        assert details["hit_step_limit"] is False
    else:
        raise AssertionError(f"Bilinmeyen senaryo: {kind}")


def _check_execution_order(kind: str, tools: list[dict[str, Any]]) -> None:
    shell = [(index, item) for index, item in enumerate(tools) if item["name"] == "run_shell"]
    edits = [
        index
        for index, item in enumerate(tools)
        if item["name"] == "edit_file" and item["outcome"] == "ok"
    ]
    assert len(shell) >= 2 and edits
    assert shell[0][0] < edits[0] < shell[-1][0]
    if kind != "stale_evidence":
        assert shell[0][1]["outcome"] != "ok"
    assert shell[-1][1]["outcome"] == "ok"


def _check_context(
    kind: str, root: Path, tools: list[dict[str, Any]], details: dict[str, Any]
) -> None:
    assert details["checkpoint_loaded"] is True
    assert details["final_criteria_ok"] is True
    assert details["journal_message_count"] > 0
    assert details["original_read"]["status"] == "redacted_original"
    assert details["criteria"] and all(item["status"] == "passed" for item in details["criteria"])
    assert details["active_context"]["note"]
    assert _successful(tools, "edit_file")
    if kind == "user_rule":
        function = runpy.run_path(str(root / "app.py"))["oku"]
        assert function("42") == 42
        try:
            function("yanlış")
        except ValueError as error:
            assert str(error) == "Geçersiz sayı"
        else:
            raise AssertionError("Parser hatalı girdiyi kabul etti")
    if kind == "masked_diagnostic":
        assert "ÖZGÜN TANI" in json.dumps(details["original_read"], ensure_ascii=False)


def _check_lessons(
    kind: str, details: dict[str, Any], events: list[dict[str, Any]], models: list[dict[str, Any]]
) -> None:
    offered = [item for item in events if item["event"] == "LessonOffered"]
    current = {
        item["id"]
        for item in details["lessons"]
        if item["subject"] == "python"
        and item["text"].startswith("python")
        and item["version"] == "2"
    }
    assert current and offered and {item["lesson_id"] for item in offered} == current
    outcomes = [item for item in events if item["event"] == "LessonOutcome"]
    assert outcomes and {item["lesson_id"] for item in outcomes} == current
    assert all(
        item["confidence"] == 0.5 and item["success_count"] == 0 and item["failure_count"] == 0
        for item in details["lessons"]
        if item["id"] in current
    )
    if kind == "lesson_quota":
        assert any(
            not item["result"]["ok"] and "429" in str(item["result"]["error"]) for item in models
        )
        assert all(item["outcome"] == "unknown" for item in outcomes)
