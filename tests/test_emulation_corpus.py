"""Çok çağrılı yerel corpus bütün çağrıları ve gerçek ölçüm sınırlarını denetler."""

from __future__ import annotations

import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.tool_emulation import CALL_CLOSE, CALL_OPEN
from fusion_cli.observability.json_sink import JsonRenderer
from fusion_cli.tools import emulation_eval as evaluation

CORPUS = Path(__file__).parent / "fixtures/emulation/corpus-v2.json"


def _call(name: str, arguments: dict[str, object]) -> str:
    return f"{CALL_OPEN}\n{json.dumps({'name': name, 'arguments': arguments})}\n{CALL_CLOSE}"


def test_second_wrong_call_fails_even_when_first_matches():
    assert hasattr(evaluation, "ExpectedCall"), "Çoklu beklenen çağrı sözleşmesi eksik"
    case = evaluation.EvalCase(
        output=_call("read_file", {"path": "a"}) + "\n" + _call("write_file", {"path": "wrong"}),
        expected_tool=None,
        expected_calls=(
            evaluation.ExpectedCall("read_file", {"path": "a"}),
            evaluation.ExpectedCall("write_file", {"path": "b"}),
        ),
    )
    score = evaluation.score_emulation([case])
    assert score.argument_preservation == 0
    assert score.argument_preservation_measured == 1
    assert (
        evaluation.score_emulation(
            [replace(case, output=case.output + "\n" + _call("extra", {}))]
        ).tool_selection
        == 0
    )


def test_synthetic_corpus_replays_all_calls_and_payloads():
    assert hasattr(evaluation, "load_corpus"), "Etiketli corpus yükleyicisi eksik"
    cases = evaluation.load_corpus(CORPUS)
    assert len(cases) == 12 and {case.provenance for case in cases} == {"synthetic"}
    assert len({case.case_id for case in cases}) == 12
    score = evaluation.score_emulation(cases)
    assert score.passes()
    assert score.argument_preservation_measured > 0
    assert any(len(case.expected_calls or ()) > 1 for case in cases)


def test_replay_cli_reports_missing_real_records_and_unknown_usage(capsys):
    from evals.cli import main

    assert main(["emulation-replay", str(CORPUS)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["synthetic_cases"] == 12 and report["recorded_cases"] == 0
    assert report["missing_recorded_cases"] == 200
    assert report["missing_recorded_train"] == 160 and report["missing_recorded_holdout"] == 40
    assert report["usage_unknown_cases"] == 12


def test_replay_cli_bad_payload_exits_nonzero(tmp_path, capsys):
    from evals.cli import main

    assert CORPUS.exists(), "Corpus fixture eksik"
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    payload["cases"][0]["output"] = "bozuk payload"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["emulation-replay", str(path)]) == 1
    assert not json.loads(capsys.readouterr().out)["passed"]


def test_recorded_rows_require_provenance_and_disjoint_split(tmp_path):
    assert hasattr(evaluation, "load_corpus"), "Etiketli corpus yükleyicisi eksik"
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    payload["cases"][0]["provenance"] = "recorded"
    path = tmp_path / "recorded.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        evaluation.load_corpus(path)


def test_redaction_preserves_valid_json_and_call_identity():
    stream = io.StringIO()
    event = ToolExecuted(
        name="read_file",
        args={"token": "sk-" + "x" * 40},
        outcome=ToolOutcome.OK,
        output="token=secret",
        call_id="call-a",
        attempt_id="attempt-a",
        event_id="event-a",
        session_id="session-a",
        turn_id="turn-a",
    )
    JsonRenderer(stream).handle(event)
    payload = json.loads(stream.getvalue())
    assert payload["call_id"] == "call-a" and payload["attempt_id"] == "attempt-a"
    assert payload["event_id"] == "event-a" and "secret" not in stream.getvalue()


def test_multicall_order_and_payload_are_compared_directly():
    from fusion_cli.core.tool_emulation import parse_tool_calls

    for case in evaluation.load_corpus(CORPUS):
        parsed = parse_tool_calls(case.output)
        assert [(call.name, json.loads(call.arguments)) for call in parsed.calls] == [
            (expected.name, expected.arguments) for expected in case.expected_calls or ()
        ], case.case_id


def test_negative_case_rejects_false_calls_and_wrong_second_tool():
    negative = evaluation.EvalCase(_call("write_file", {"path": "false"}), None, expected_calls=())
    assert evaluation.score_emulation([negative]).no_false_calls == 0
    multiple = evaluation.EvalCase(
        _call("read_file", {"path": "a"}) + "\n" + _call("wrong_tool", {}),
        None,
        expected_calls=(
            evaluation.ExpectedCall("read_file", {"path": "a"}),
            evaluation.ExpectedCall("write_file", {}),
        ),
    )
    assert evaluation.score_emulation([multiple]).tool_selection == 0


def test_duplicate_recorded_source_cannot_fill_two_splits(tmp_path):
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    for index, split in enumerate(("train", "holdout")):
        payload["cases"][index].update(
            provenance="recorded",
            provider="captured-provider",
            transport="browser",
            split=split,
            source_id="same-record",
        )
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="tekrarlanamaz"):
        evaluation.load_corpus(path)
    with pytest.raises(ValueError, match="160 train"):
        evaluation.load_corpus(CORPUS, require_complete=True)


def test_unknown_usage_uses_existing_measured_flags(tmp_path):
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    payload["cases"][0]["usage"] = {
        "prompt_tokens": 3,
        "completion_tokens": 5,
        "cost_usd": 0,
        "prompt_measured": True,
        "completion_measured": True,
        "cost_known": True,
    }
    path = tmp_path / "usage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = evaluation.replay_corpus_report(evaluation.load_corpus(path))
    assert report["usage_unknown_cases"] == report["cost_unknown_cases"] == 11


def _admission_shaped_bundle(protocol: str, lost: int = 100):
    """Hermetik admission biçimi; gerçek kayıt veya pilot kanıtı değildir."""
    import hashlib
    from dataclasses import asdict

    from .test_web_tool_provenance import observed_origin

    rows = []
    for index in range(200):
        call = _call("read_file", {"path": "a"})
        output = f"Örnek:\n```\n{call}\n```" if index < lost else call
        if index >= 100:
            output = "Yanıt"
        source = f"hermetic-{index}"
        rows.append(
            {
                "case_id": source,
                "source_id": source,
                "provider": "fixture",
                "transport": "browser",
                "split": "train" if index < 160 else "holdout",
                "capture_group": "train-group" if index < 160 else "holdout-group",
                "provenance": "recorded",
                "protocol": protocol,
                "output": output,
                "expected_calls": [{"name": "read_file", "arguments": {"path": "a"}}]
                if index < 100
                else [],
                "web_provenance": asdict(observed_origin()),
                "capture_receipt": {
                    "run_id": "hermetic",
                    "source_id": source,
                    "redaction_status": "unchanged",
                    "body_digest": hashlib.sha256(output.encode()).hexdigest(),
                },
            }
        )
    negatives = json.loads((CORPUS.parent / "origin-v2.json").read_text())["cases"]
    return {
        "version": 2,
        "cases": rows + negatives,
        "capture_manifest": {
            "source_kind": "controlled_browser_probe",
            "capture_path": "explicit_probe",
            "body_stage": "adapter_preparse_text",
            "redaction_policy": "central-v1",
            "label_review": "reviewed",
            "status": "complete",
            "run_id": "hermetic",
            "source_reference": "hermetic-fixture",
            "license_id": "CC0-1.0",
            "rights_holder": "fixture-author",
        },
    }


def test_v1_only_admission_cannot_close_v2_strict_cli(tmp_path, capsys, monkeypatch):
    import evals.cli as command

    monkeypatch.setattr(command, "load_config", lambda: pytest.fail("Config okunamaz"))
    path = tmp_path / "hermetic.json"
    path.write_text(json.dumps(_admission_shaped_bundle("v1")))
    assert command.main(["emulation-replay", str(path)]) == 0
    diagnostic = json.loads(capsys.readouterr().out)
    assert diagnostic["passed"] and diagnostic["metrics"]["tool_selection"] == 1
    assert command.main(["emulation-replay", str(path), "--require-complete"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["f03_complete"] and report["recorded_cases"] == 200
    assert not report["f06_complete"] and not report["complete"]
    assert report["f06_comparison"]["positive_cases"] == 0
    assert report["f06_comparison"]["recall_loss_pp"] is None
    assert report["f06_comparison"]["recall_passed"] is None


@pytest.mark.parametrize("lost,strict_exit", [(0, 0), (1, 0), (2, 1), (100, 1)])
def test_v2_paired_recall_cli_measures_one_percentage_point_limit(
    tmp_path, capsys, lost, strict_exit
):
    from evals.cli import main

    path = tmp_path / "hermetic.json"
    path.write_text(json.dumps(_admission_shaped_bundle("v2", lost)))
    assert main(["emulation-replay", str(path), "--require-complete"]) == strict_exit
    report = json.loads(capsys.readouterr().out)
    comparison = report["f06_comparison"]
    assert comparison["positive_cases"] == 100
    assert comparison["v1_recall"] == 1
    assert comparison["v2_recall"] == pytest.approx(1 - lost / 100)
    assert comparison["recall_loss_pp"] == pytest.approx(lost)
    assert comparison["recall_passed"] is (lost <= 1)
    assert report["f06_complete"] is (lost <= 1)


def test_paired_recall_does_not_hide_a_v2_negative_false_call(tmp_path, capsys):
    from evals.cli import main

    payload = _admission_shaped_bundle("v2", 0)
    # Admitted negatif gövde ve receipt aynı kalır; beklenti bilerek çağrı yoktur.
    payload["cases"][0]["expected_calls"] = []
    # 100 pozitif şartını ayrı tutmak için son admitted negatif pozitif yapılır.
    row = payload["cases"][100]
    import hashlib

    row["output"] = _call("read_file", {"path": "a"})
    row["capture_receipt"]["body_digest"] = hashlib.sha256(row["output"].encode()).hexdigest()
    row["expected_calls"] = [{"name": "read_file", "arguments": {"path": "a"}}]
    path = tmp_path / "hermetic-negative.json"
    path.write_text(json.dumps(payload))
    assert main(["emulation-replay", str(path), "--require-complete"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["f06_comparison"]["positive_cases"] == 100
    assert report["f06_comparison"]["recall_passed"]
    assert not report["f06_complete"]
