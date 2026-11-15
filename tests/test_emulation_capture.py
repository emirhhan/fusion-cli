"""Açık yakalama yerel doğrulama, sınırlı saklama ve gerçek kabul ayrımını korur."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.tools.emulation_eval import load_corpus, replay_corpus_report


def test_declared_recorded_without_capture_receipt_is_not_genuine(tmp_path):
    payload = {
        "version": 2,
        "cases": [
            {
                "case_id": "r1",
                "provider": "provider",
                "transport": "browser",
                "split": "train",
                "provenance": "recorded",
                "source_id": "source1",
                "output": "Yanıt",
                "expected_calls": [],
            }
        ],
    }
    corpus = tmp_path / "claimed.json"
    corpus.write_text(json.dumps(payload))
    report = replay_corpus_report(load_corpus(corpus))
    assert report["recorded_cases"] == 0
    assert report["missing_recorded_cases"] == 200


def test_strict_replay_reports_missing_evidence_without_provider(capsys):
    from evals.cli import main

    path = Path(__file__).parent / "fixtures/emulation/corpus-v2.json"
    assert main(["emulation-replay", str(path), "--require-complete"]) != 0
    report = json.loads(capsys.readouterr().out)
    assert report["missing_recorded_cases"] == 200
    assert report["missing_genuine_positive_cases"] == 100


def test_capture_manifest_validation_rejects_missing_limits_before_config(tmp_path, monkeypatch):
    import evals.cli as command
    from evals.cli import main

    def forbidden():
        raise AssertionError("Yerel doğrulama yapılandırma okuyamaz")

    monkeypatch.setattr(command, "load_config", forbidden)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    assert (
        main(
            [
                "emulation-record",
                str(manifest),
                "--out-dir",
                str(tmp_path / "run"),
                "--validate-only",
            ]
        )
        == 2
    )


async def test_explicit_export_redacts_decoded_leaves_and_does_not_admit_synthetic(tmp_path):
    from evals.emulation_capture import CaptureManifest, export_capture

    from fusion_cli.engines.emulation_probe import ProbeLimits, ProbeReport, ProbeScenario
    from fusion_cli.tools.emulation_eval import EvalCase, score_emulation

    case = EvalCase("Bearer fixture-sensitive", None, case_id="case-1")
    report = ProbeReport(score_emulation([case]), (), (case,))
    manifest = CaptureManifest(
        model="fixture",
        provider="fixture",
        scenarios=(ProbeScenario("Yanıtla", None),),
        limits=ProbeLimits(1, 2048, 100000, 5),
        source_reference="public-fixture",
        rights_holder="fixture-author",
        license_id="CC0-1.0",
        split="train",
        capture_group="group-1",
        label_review="reviewed",
        source_kind="synthetic",
        protocol="v1",
    )
    result = await export_capture(
        report, manifest, tmp_path / "run", run_id="run-1", captured_at=123
    )
    assert result.ok
    payload = json.loads((tmp_path / "run" / "corpus.json").read_text())
    assert "fixture-sensitive" not in json.dumps(payload)
    assert payload["capture_manifest"]["redaction_status"] == "changed"
    assert (
        replay_corpus_report(load_corpus(tmp_path / "run" / "corpus.json"))["recorded_cases"] == 0
    )
    assert not (
        await export_capture(report, manifest, tmp_path / "run", run_id="run-1", captured_at=123)
    ).ok


async def test_export_rejects_symlink_budget_and_uncertain_commit(tmp_path, monkeypatch):
    from dataclasses import replace

    from evals import emulation_capture as capture

    from fusion_cli.core.atomic_file import AtomicCommitUncertainError
    from fusion_cli.engines.emulation_probe import ProbeLimits, ProbeReport, ProbeScenario
    from fusion_cli.tools.emulation_eval import EvalCase, score_emulation

    case = EvalCase("yanıt", None, case_id="case-1")
    report = ProbeReport(score_emulation([case]), (), (case,))
    manifest = capture.CaptureManifest(
        "fixture",
        "fixture",
        (ProbeScenario("Yanıtla", None),),
        ProbeLimits(1, 2048, 100000, 5),
        "public-fixture",
        "author",
        "CC0-1.0",
        "train",
        "group",
        "reviewed",
        "synthetic",
        "v1",
    )
    (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
    assert not (
        await capture.export_capture(
            report, manifest, tmp_path / "link" / "run", run_id="run", captured_at=1
        )
    ).ok
    tiny = replace(manifest, limits=ProbeLimits(1, 2048, 5, 5))
    assert not (
        await capture.export_capture(report, tiny, tmp_path / "tiny", run_id="run", captured_at=1)
    ).ok

    def uncertain(target, body):
        raise AtomicCommitUncertainError("belirsiz")

    monkeypatch.setattr(capture, "atomic_create_bytes", uncertain)
    result = await capture.export_capture(
        report, manifest, tmp_path / "uncertain", run_id="run", captured_at=1
    )
    assert not result.ok and result.is_commit_uncertain


async def test_record_reuses_probe_and_marks_injected_registry_synthetic(tmp_path):
    from evals.emulation_capture import CaptureManifest, record_emulation

    from fusion_cli.engines.emulation_probe import ProbeLimits, ProbeScenario

    from .test_emulation_probe import MODEL, _config, _Registry, _ScriptedProvider

    class FakeClock:
        def now(self):
            return 123.0

        def monotonic(self):
            return 123.0

    provider = _ScriptedProvider(["Yanıt"])
    manifest = CaptureManifest(
        MODEL,
        "chatgpt_web",
        (ProbeScenario("Yanıtla", None),),
        ProbeLimits(1, 2048, 100000, 5),
        "public-fixture",
        "author",
        "CC0-1.0",
        "train",
        "group",
        "reviewed",
        "controlled_browser_probe",
        "v1",
    )
    identities = iter(["run", "session", "turn", "attempt", "call"])
    result = await record_emulation(
        _config(),
        manifest,
        tmp_path / "run",
        clock=FakeClock(),
        id_factory=lambda: next(identities),
        registry=_Registry(provider),
    )
    assert result.ok and len(provider.seen) == 1
    payload = json.loads((tmp_path / "run" / "corpus.json").read_text())
    assert payload["capture_manifest"]["source_kind"] == "synthetic"


async def test_nonfinite_values_cannot_publish_nonstandard_json(tmp_path):
    from evals.emulation_capture import CaptureManifest, export_capture

    from fusion_cli.engines.emulation_probe import ProbeLimits, ProbeReport, ProbeScenario
    from fusion_cli.tools.emulation_eval import EvalCase, ExpectedCall, score_emulation

    case = EvalCase("yanıt", None, expected_calls=(ExpectedCall("read_file", {"n": float("nan")}),))
    report = ProbeReport(score_emulation([case]), (), (case,))
    manifest = CaptureManifest(
        "fixture",
        "fixture",
        (ProbeScenario("Yanıtla", None),),
        ProbeLimits(1, 2048, 100000, 5),
        "public-fixture",
        "author",
        "CC0-1.0",
        "train",
        "group",
        "reviewed",
        "synthetic",
        "v1",
    )
    result = await export_capture(report, manifest, tmp_path / "run", run_id="run", captured_at=1)
    assert not result.ok
    assert not (tmp_path / "run" / "corpus.json").exists()


def _scenario_manifest(scenario):
    return {
        "model": "fixture",
        "provider": "fixture",
        "scenarios": [scenario],
        "limits": {
            "max_calls": 1,
            "max_response_bytes": 2048,
            "max_total_bytes": 100000,
            "timeout_s": 5,
        },
        "source_reference": "public-fixture",
        "rights_holder": "fixture-author",
        "license_id": "CC0-1.0",
        "split": "train",
        "capture_group": "group",
        "label_review": "reviewed",
        "source_kind": "synthetic",
        "protocol": "v1",
    }


def test_public_multicall_manifest_export_and_replay(tmp_path, monkeypatch, capsys):
    import asyncio
    from dataclasses import replace

    import evals.cli as command
    from evals.emulation_capture import load_capture_manifest, record_emulation

    from .test_emulation_probe import MODEL, _config, _Registry, _ScriptedProvider

    monkeypatch.setattr(command, "load_config", lambda: (_ for _ in ()).throw(AssertionError()))
    calls = [{"name": "read_file", "arguments": {"path": path}} for path in ("a", "b")]
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(_scenario_manifest({"prompt": "İki dosyayı oku", "expected_calls": calls}))
    )
    assert (
        command.main(
            ["emulation-record", str(path), "--out-dir", str(tmp_path / "run"), "--validate-only"]
        )
        == 0
    )
    capsys.readouterr()
    manifest = asyncio.run(load_capture_manifest(path))
    from fusion_cli.core.tool_emulation import render_call

    from .test_turn_deadline import FakeClock

    provider = _ScriptedProvider(["\n".join(render_call(call) for call in calls)])
    identities = iter(["run", "session", "turn", "attempt", "call"])
    result = asyncio.run(
        record_emulation(
            _config(),
            replace(manifest, model=MODEL, provider="chatgpt_web"),
            tmp_path / "run",
            clock=FakeClock(123),
            id_factory=lambda: next(identities),
            registry=_Registry(provider),
        )
    )
    assert result.ok and len(provider.seen) == 1
    cases = load_corpus(result.path)
    assert [(item.name, item.arguments) for item in cases[0].expected_calls] == [
        (item["name"], item["arguments"]) for item in calls
    ]
    assert not cases[0].is_admitted
    # Tek satır eski üç-senaryo yeterlilik eşiğini kapatmaz; replay yine ölçülür.
    assert command.main(["emulation-replay", str(result.path)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["metrics"]["argument_preservation"] == 1
    assert report["recorded_cases"] == 0


def test_manifest_legacy_coexistence_and_conflict_before_config(tmp_path, monkeypatch, capsys):
    import evals.cli as command

    monkeypatch.setattr(command, "load_config", lambda: (_ for _ in ()).throw(AssertionError()))
    call = {"name": "read_file", "arguments": {"path": "a"}}
    valid = [
        {"expected_tool": "read_file", "expected_arguments": {"path": "a"}},
        {"expected_tool": None},
        {"expected_calls": []},
        {"expected_tool": None, "expected_calls": [call, call]},
        {
            "expected_tool": "read_file",
            "expected_arguments": {"path": "a"},
            "expected_calls": [call],
        },
    ]
    invalid = [
        {},
        {"expected_calls": None},
        {"expected_calls": {}},
        {"expected_calls": [{"name": "read_file", "arguments": []}]},
        {"expected_tool": "write_file", "expected_calls": [call]},
        {"expected_tool": "read_file", "expected_calls": [call, call]},
        {"expected_tool": None, "expected_arguments": {"path": "a"}, "expected_calls": [call]},
        {
            "expected_tool": "read_file",
            "expected_arguments": {"path": "b"},
            "expected_calls": [call],
        },
    ]
    for index, scenario in enumerate(valid + invalid):
        path = tmp_path / f"manifest-{index}.json"
        path.write_text(json.dumps(_scenario_manifest({"prompt": "Oku", **scenario})))
        assert command.main(
            [
                "emulation-record",
                str(path),
                "--out-dir",
                str(tmp_path / f"run-{index}"),
                *(["--validate-only"] if index < len(valid) else []),
            ]
        ) == (0 if index < len(valid) else 2), scenario
        capsys.readouterr()
