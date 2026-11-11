"""Failed integrity checks retain real observations and stop before another actor run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion, TaskBudget
from scripts import release_live

from .test_live_drive_engine_proof import settings


async def test_release_driver_requests_nonpersistent_session_mode(tmp_path):
    from evals.live_drive import drive

    args, received = settings(tmp_path)
    args.persist_mode = False
    await drive(args, None)
    first = json.loads(received.read_text().splitlines()[0])
    assert first["ad"] == "oturum.baslat"
    assert first["veri"]["mod_kalici"] is False


def _mutate_config(options):
    Path(options.runtime_env["FUSION_CONFIG"]).write_text("runtime:\n  approval_mode: auto\n")


def _host_config_exists(options):
    return Path(options.runtime_env["FUSION_CONFIG"]).exists()


def _fake_run(tmp_path, monkeypatch, *, mutate_config=False):
    task = EvalTask(
        "one",
        "do it",
        SuccessCriterion(CriterionKind.EXIT_CODE, expected_exit_code=0, command="true"),
        budget=TaskBudget(30, 180),
    )
    monkeypatch.setattr(release_live, "load_tasks", lambda path: (task,))
    monkeypatch.setattr(release_live, "temporary_roots", lambda: ())
    monkeypatch.setattr(release_live, "_source_entries", lambda root: ())
    monkeypatch.setattr(release_live, "_scorer_entries", lambda root: ())
    monkeypatch.setattr(release_live, "verify_runtime_files", lambda *args: None)
    monkeypatch.setattr(
        release_live,
        "prepare_feedback",
        lambda *args: SimpleNamespace(
            environment={},
            manifest=lambda: {},
            assert_unchanged=lambda: None,
        ),
    )
    source = release_live._digest_entries(())

    def extract(archive, manifest, root):
        (root / "_internal").mkdir(parents=True)
        (root / "fusion").write_text("fake only")
        (root / "_internal/release-build.json").write_text(
            json.dumps(
                {
                    "version": "1.2.3",
                    "commit": "a" * 40,
                    "source_digest": source,
                    "scorer_digest": source,
                }
            )
        )
        return root / "fusion", {"target": "aarch64-apple-darwin", "runtime_version": "1.2.3"}

    monkeypatch.setattr(release_live, "extract_runtime", extract)
    calls = []

    async def driver(options, stderr, events):
        calls.append(options)
        if mutate_config:
            _mutate_config(options)
        return {"actual_driver_observation": len(calls)}

    monkeypatch.setattr(release_live, "drive", driver)
    for name in ("archive", "manifest"):
        (tmp_path / name).write_text("fixture")
    config = tmp_path / "profile.yaml"
    config.write_text("# explicit immutable profile\nruntime:\n  self_review: true\n")
    args = argparse.Namespace(
        out=tmp_path / "out",
        archive=tmp_path / "archive",
        manifest=tmp_path / "manifest",
        config=config,
        version="1.2.3",
        commit="a" * 40,
        repeat=3,
        provider_env=[],
    )
    return args, calls


async def test_failed_config_check_preserves_observation_before_host_cleanup(tmp_path, monkeypatch):
    args, calls = _fake_run(tmp_path, monkeypatch, mutate_config=True)
    before = args.config.read_bytes()
    with pytest.raises(ValueError, match="config"):
        await release_live.run(args)
    assert len(calls) == 1
    assert not (args.out / "observations.json").exists()
    checkpoint = json.loads((args.out / "observations.partial.json").read_text())
    assert checkpoint["status"] == "invalid"
    assert checkpoint["acceptance_eligible"] is False
    assert checkpoint["observations"][0]["driver"] == {"actual_driver_observation": 1}
    failure = json.loads((args.out / "failure-evidence.json").read_text())
    assert failure["config"]["expected_sha256"] == hashlib.sha256(before).hexdigest()
    assert failure["config"]["actual_sha256"] != failure["config"]["expected_sha256"]
    assert args.config.read_bytes() == before
    assert not _host_config_exists(calls[0])


async def test_success_checkpoints_all_rows_and_keeps_exact_profile_bytes(tmp_path, monkeypatch):
    args, calls = _fake_run(tmp_path, monkeypatch)
    before = args.config.read_bytes()
    result = await release_live.run(args)
    assert len(result["observations"]) == 3 and len(calls) == 3
    assert all(options.persist_mode is False for options in calls)
    checkpoint = json.loads((args.out / "observations.partial.json").read_text())
    assert checkpoint["status"] == "completed" and checkpoint["acceptance_eligible"] is False
    assert json.loads((args.out / "observations.json").read_text())["status"] == "completed"
    assert args.config.read_bytes() == before


async def test_timing_is_retained_for_each_failed_case_without_changing_its_verdict(
    tmp_path, monkeypatch
):
    args, _ = _fake_run(tmp_path, monkeypatch)
    run_count = 0

    async def driver(options, stderr, events):
        nonlocal run_count
        run_count += 1
        turn = f"attempt-{run_count}"
        events.write(
            (
                json.dumps({"tip": "olay", "veri": {"olay": "ModelCallAbandoned", "turn_id": turn}})
                + "\n"
            ).encode()
        )
        traces = Path(options.runtime_env["HOME"]) / ".local/share/fusion-cli/memory/traces"
        traces.mkdir(parents=True, exist_ok=True)
        provider = {"event": "ProviderCallDiagnostic", "turn_id": turn, "call_id": "private"}
        (traces / f"trace-{run_count}.jsonl").write_text(
            "\n".join(
                json.dumps({**provider, "phase": phase, "elapsed_ms": elapsed})
                for phase, elapsed in (("call_enter", 0), ("call_cancelled", run_count * 10))
            ),
            encoding="utf-8",
        )
        assert options.sure == 180
        return {"sonuc": {"ok": False}}

    monkeypatch.setattr(release_live, "drive", driver)
    result = await release_live.run(args)
    rows = result["observations"]
    assert all(row["driver"]["sonuc"]["ok"] is False for row in rows)
    assert [row["phase_timing"]["provider"]["terminal_elapsed_ms"] for row in rows] == [10, 20, 30]
    assert (
        json.loads((args.out / "observations.partial.json").read_text())["acceptance_eligible"]
        is False
    )


async def test_integrity_guard_stops_before_model_turn_request(tmp_path):
    from evals.live_drive import drive

    args, received = settings(tmp_path)

    def fail():
        raise ValueError("config changed during initialization")

    args.runtime_config_guard = fail
    args.persist_mode = False
    with pytest.raises(ValueError, match="config"):
        await drive(args, None)
    requests = [json.loads(line)["ad"] for line in received.read_text().splitlines()]
    assert requests == ["oturum.baslat"]


def test_semantic_equivalence_does_not_waive_exact_profile_byte_binding(tmp_path):
    original = b"# immutable approved formatting\nruntime:\n  self_review: true\n"
    source = tmp_path / "profile.yaml"
    source.write_bytes(original)
    host = tmp_path / "host.yaml"
    host.write_bytes(b"runtime: {self_review: true}\n")
    evidence = release_live._config_failure_evidence(host, original)
    assert evidence["yaml_semantically_equal"] is True
    assert evidence["actual_sha256"] != evidence["expected_sha256"]
    with pytest.raises(ValueError, match="config"):
        release_live._assert_config_unchanged(host, source, hashlib.sha256(original).hexdigest())
