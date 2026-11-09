"""Verifier derives acceptance from independent inspection, observed calls and pinned config."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

import pytest
from evals.driver_config import ConfigReceipt
from evals.effective_config import project_effective
from evals.engine_proof import ImportedEngineProof
from evals.executor import _snapshot
from evals.profiles import _digest_entries, _scorer_entries, _source_entries
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion, TaskBudget
from scripts import release_oracle, release_verify
from scripts.release_manifest import ROOT, sha256_file

from .fakes import make_config


def _runs(tmp_path, monkeypatch):
    monkeypatch.setattr(release_verify, "PROTECTED_TARGETS", {"fixture-platform"})
    task = EvalTask(
        "one",
        "change file",
        SuccessCriterion(
            CriterionKind.EXIT_CODE,
            expected_exit_code=0,
            command=(
                "python -c \"from pathlib import Path; assert Path('product').read_text()=='good'\""
            ),
        ),
        setup={"product": "seed"},
        budget=TaskBudget(30, 180),
    )
    monkeypatch.setattr(release_verify, "load_tasks", lambda path: (task,))
    monkeypatch.setattr(release_oracle, "load_tasks", lambda path: (task,))
    monkeypatch.setattr(release_verify, "_validate_live_measurement", lambda *args: None)

    # Unit test runs on macOS; Linux bubblewrap behavior is tested separately.
    async def inspect(root, *, repeat, isolated):
        assert isolated is True
        return await release_oracle.inspect_workspaces(root, repeat=repeat)

    monkeypatch.setattr(release_verify, "inspect_workspaces", inspect)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    archive = artifacts / "runtime.tar.gz"
    archive.write_bytes(b"exact-built-runtime-fixture")
    manifest = artifacts / "manifest.json"
    manifest.write_text("frozen manifest fixture")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("explicit-approved-configuration")
    source = _digest_entries(_source_entries(ROOT))
    config = make_config()
    effective = project_effective(config, config.agent, "general")
    proof = ImportedEngineProof(
        123,
        "/runtime/fusion_cli/__init__.py",
        "/runtime/fusion_cli/cli/app.py",
        "/runtime",
        source,
        "a" * 40,
    )
    receipt = ConfigReceipt(1, 123, source, "a" * 40, "unverified", effective)
    observations = []
    directory = tmp_path / "runs/platform"
    for index in range(1, 4):
        candidate = directory / "workspaces/one" / f"run-{index:02d}"
        candidate.mkdir(parents=True)
        (candidate / "product").write_text("good")
        event_path = directory / f"events-{index}.jsonl"
        events = [
            {"veri": {"olay": "ModelCallStarted", "call_id": f"call-{index}"}},
            {
                "veri": {
                    "olay": "ModelCallFinished",
                    "call_id": f"call-{index}",
                    "requested_model": config.agent.model,
                    "result": {"ok": True, "served_by": config.agent.model},
                }
            },
        ]
        event_path.write_text("\n".join(json.dumps(item) for item in events))
        observations.append(
            {
                "task_id": "one",
                "repeat": index,
                "started_at": time.time() - 2,
                "finished_at": time.time() - 1,
                "candidate_digest": _digest_entries(_snapshot(candidate)),
                "events": event_path.name,
                "driver": {"motor_kaniti": asdict(proof), "efektif_kanitlar": [asdict(receipt)]},
            }
        )
    raw = {
        "status": "completed",
        "target": "fixture-platform",
        "binding": {
            "commit": "a" * 40,
            "version": "1.2.3",
            "source_digest": source,
            "scorer_digest": _digest_entries(_scorer_entries(ROOT)),
            "config_file_sha256": sha256_file(config_file),
            "archive": archive.name,
            "manifest": manifest.name,
            "manifest_sha256": sha256_file(manifest),
            "archive_sha256": sha256_file(archive),
        },
        "observations": observations,
    }
    (directory / "observations.json").write_text(json.dumps(raw))
    expected = _digest_entries([("one", _digest_entries([effective.digest]))])
    args = argparse.Namespace(
        runs=tmp_path / "runs",
        artifacts=artifacts,
        config=config_file,
        commit="a" * 40,
        version="1.2.3",
        model=config.agent.model,
        effective_config_digest=expected,
        target=["fixture-platform"],
    )
    return args, directory, raw


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "failed_oracle",
        "unknown_model",
        "wrong_config",
        "wrong_artifact",
        "wrong_source",
        "duplicate_repeat",
        "stale_execution",
        "incomplete_checkpoint",
        "diagnostic_checkpoint",
    ],
)
async def test_independent_verifier_rejects_unmeasured_or_mismatched_runs(
    tmp_path, monkeypatch, mutation
):
    args, directory, raw = _runs(tmp_path, monkeypatch)
    if mutation == "failed_oracle":
        (directory / "workspaces/one/run-01/product").write_text("bad")
    if mutation == "unknown_model":
        event = directory / "events-1.jsonl"
        event.write_text(event.read_text().replace(args.model, ""))
    if mutation == "wrong_config":
        args.effective_config_digest = "0" * 64
    if mutation == "wrong_artifact":
        (args.artifacts / "runtime.tar.gz").write_bytes(b"changed")
    if mutation == "wrong_source":
        raw["binding"]["source_digest"] = "0" * 64
    if mutation == "diagnostic_checkpoint":
        raw["acceptance_eligible"] = False
    if mutation == "incomplete_checkpoint":
        raw["status"] = "invalid"
    if mutation == "stale_execution":
        raw["observations"][0]["started_at"] = 0
        raw["observations"][0]["finished_at"] = 1
    if mutation == "duplicate_repeat":
        raw["observations"][-1]["repeat"] = 1
    (directory / "observations.json").write_text(json.dumps(raw))
    if mutation is None:
        report = await release_verify.verify_runs(args)
        assert report["results"][0]["success"] is True
        assert report["binding"]["artifacts"]["runtime.tar.gz"] == sha256_file(
            args.artifacts / "runtime.tar.gz"
        )
    else:
        with pytest.raises(ValueError):
            await release_verify.verify_runs(args)
