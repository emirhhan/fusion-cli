"""Onarım harcaması ve bağımsız deneme kimliği devam kaydında kaybolmaz."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from fusion_cli.core.budget import BudgetStop
from fusion_cli.core.repair_ledger import FailureEvidence, SourceFingerprint
from fusion_cli.core.tools import ToolResult
from fusion_cli.engines.agent.repair_flow import record_failure_evidence
from fusion_cli.memory.checkpoint_store import JsonCheckpointStore

from .test_checkpoint_store import _checkpoint
from .test_repair_flow import budget


def failure(attempt):
    return ToolResult(
        "ölçüm düştü",
        ok=False,
        failure_evidence=(
            FailureEvidence(
                "video/layout",
                "overflow",
                attempt,
                (SourceFingerprint("src/a.tsx", "a" * 64),),
            ),
        ),
    )


def test_checkpoint_roundtrip_resume_poll_and_same_source_budget(tmp_path):
    turn = budget()
    record_failure_evidence(failure("first"), turn)
    checkpoint = replace(_checkpoint(tmp_path), turn_repair=turn.snapshot_repairs())
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    store.save(checkpoint)
    loaded = store.load("plan-1")
    assert loaded is not None and loaded.turn_repair == checkpoint.turn_repair
    resumed = budget()
    resumed.restore_repairs(loaded.turn_repair)
    assert not record_failure_evidence(failure("first"), resumed).is_new_failure
    assert resumed.verify_rounds == 1
    assert "yaklaşımı değiştir" in record_failure_evidence(failure("second"), resumed).note
    assert resumed.verify_rounds == 2
    assert record_failure_evidence(failure("third"), resumed).is_exhausted
    assert resumed.stop is BudgetStop.NO_PROGRESS


def test_restore_is_exact_idempotent_and_rejects_disjoint_state():
    original = budget()
    record_failure_evidence(failure("first"), original)
    snapshot = original.snapshot_repairs()
    original.restore_repairs(snapshot)
    assert original.verify_rounds == 1
    disjoint = budget()
    record_failure_evidence(failure("other"), disjoint)
    with pytest.raises(ValueError):
        disjoint.restore_repairs(snapshot)
    assert disjoint.verify_rounds == 1
    assert disjoint.repair_ledger.snapshot().failures[0].attempt_id == "other"


@pytest.mark.parametrize("bad", [True, -1, "1"])
def test_invalid_counter_rejects_entire_checkpoint(tmp_path, bad):
    store = JsonCheckpointStore(tmp_path)
    store.save(_checkpoint(tmp_path))
    path = next(tmp_path.glob("*.json"))
    payload = json.loads(path.read_text())
    payload["turn_repair"] = {"verify_rounds": bad, "failures": []}
    path.write_text(json.dumps(payload))
    assert store.load("plan-1") is None


@pytest.mark.parametrize(
    "path", [".env.json", "src/.env/config.ts", "../private.ts", "/private.ts"]
)
def test_private_source_path_rejects_checkpoint(tmp_path, path):
    turn = budget()
    item = failure("first").failure_evidence[0]
    record_failure_evidence(
        replace(
            failure("first"),
            failure_evidence=(
                replace(
                    item,
                    sources=(SourceFingerprint(path, "a" * 64),),
                ),
            ),
        ),
        turn,
    )
    store = JsonCheckpointStore(tmp_path)
    with pytest.raises(ValueError):
        store.save(replace(_checkpoint(tmp_path), turn_repair=turn.snapshot_repairs()))


def test_old_checkpoint_absent_field_has_no_invented_repair_usage(tmp_path):
    store = JsonCheckpointStore(tmp_path)
    store.save(_checkpoint(tmp_path))
    path = next(tmp_path.glob("*.json"))
    payload = json.loads(path.read_text())
    payload.pop("turn_repair", None)
    path.write_text(json.dumps(payload))
    loaded = store.load("plan-1")
    assert loaded is not None and loaded.turn_repair is None


async def test_real_plan_entry_saves_and_restores_repair_before_resume(tmp_path, monkeypatch):
    from fusion_cli.core.execution_plan import ExecutionPlan
    from fusion_cli.engines.agent import plan_runner
    from fusion_cli.engines.agent.loop import AgentOutcome

    from .test_plan_repair import _deps
    from .test_plan_runner import _step

    original = _deps(tmp_path)
    original.budget = budget()
    record_failure_evidence(failure("first"), original.budget)
    plan = ExecutionPlan("repair-continuity", "iş", (_step("inspect"),))

    async def unused_agent(*args, **kwargs):
        raise AssertionError("Model çağrısı bu sınır testinde başlamamalı.")

    async def save_only(run):
        await run.save()
        return AgentOutcome("kaydedildi", [])

    monkeypatch.setattr(plan_runner._PlanRun, "run", save_only)
    await plan_runner.run_execution_plan("iş", original, unused_agent, plan=plan)
    saved = original.checkpoint_store.load(plan.plan_id)
    assert saved.turn_repair == original.budget.snapshot_repairs()
    resumed = _deps(tmp_path)
    resumed.budget = budget()
    seen = []

    async def resume(checkpoint, deps):
        # Restore, tamamlanmış adım doğrulamasından da önce olmalı.
        seen.append(deps.budget.verify_rounds)
        assert not record_failure_evidence(failure("first"), deps.budget).is_new_failure
        assert "yaklaşımı değiştir" in record_failure_evidence(failure("second"), deps.budget).note
        return checkpoint.plan, {}

    monkeypatch.setattr(plan_runner, "resume_plan", resume)
    await plan_runner.run_execution_plan("devam", resumed, unused_agent)
    assert seen == [1]
    assert resumed.budget.verify_rounds == 2
    assert record_failure_evidence(failure("third"), resumed.budget).is_exhausted


@pytest.mark.parametrize("origin", ["infrastructure", "provider"])
def test_product_external_failure_does_not_enter_checkpoint(origin, tmp_path):
    from fusion_cli.core.repair_ledger import FailureOrigin

    turn = budget()
    item = failure("first").failure_evidence[0]
    record_failure_evidence(
        replace(
            failure("first"),
            failure_evidence=(
                replace(
                    item,
                    origin=FailureOrigin(origin),
                ),
            ),
        ),
        turn,
    )
    store = JsonCheckpointStore(tmp_path)
    store.save(replace(_checkpoint(tmp_path), turn_repair=turn.snapshot_repairs()))
    saved = store.load("plan-1")
    assert saved.turn_repair.verify_rounds == 0
    assert saved.turn_repair.snapshot.failures == ()


def test_serialized_repair_contains_hashes_not_tool_output(tmp_path):
    turn = budget()
    record_failure_evidence(failure("first"), turn)
    store = JsonCheckpointStore(tmp_path)
    store.save(replace(_checkpoint(tmp_path), turn_repair=turn.snapshot_repairs()))
    payload = json.loads((next(tmp_path.glob("*.json"))).read_text())["turn_repair"]
    assert set(payload) == {"verify_rounds", "failures"}
    item = payload["failures"][0]
    assert set(item) == {"check_id", "family", "attempt_id", "origin", "sources"}
    assert item["sources"] == [{"path": "src/a.tsx", "digest": "a" * 64}]


@pytest.mark.parametrize(
    "field,value",
    [
        ("origin", "unknown"),
        ("family", "token=private"),
        ("check_id", "/outside:layout"),
    ],
)
def test_malformed_failure_identity_rejects_loaded_checkpoint(tmp_path, field, value):
    turn = budget()
    record_failure_evidence(failure("first"), turn)
    store = JsonCheckpointStore(tmp_path)
    store.save(replace(_checkpoint(tmp_path), turn_repair=turn.snapshot_repairs()))
    path = next(tmp_path.glob("*.json"))
    payload = json.loads(path.read_text())
    payload["turn_repair"]["failures"][0][field] = value
    path.write_text(json.dumps(payload))
    assert store.load("plan-1") is None


def test_private_source_in_loaded_checkpoint_rejected(tmp_path):
    turn = budget()
    record_failure_evidence(failure("first"), turn)
    store = JsonCheckpointStore(tmp_path)
    store.save(replace(_checkpoint(tmp_path), turn_repair=turn.snapshot_repairs()))
    path = next(tmp_path.glob("*.json"))
    payload = json.loads(path.read_text())
    payload["turn_repair"]["failures"][0]["sources"][0]["path"] = ".env.json"
    path.write_text(json.dumps(payload))
    assert store.load("plan-1") is None


def test_duplicate_attempt_in_loaded_checkpoint_rejected(tmp_path):
    turn = budget()
    record_failure_evidence(failure("first"), turn)
    store = JsonCheckpointStore(tmp_path)
    store.save(replace(_checkpoint(tmp_path), turn_repair=turn.snapshot_repairs()))
    path = next(tmp_path.glob("*.json"))
    payload = json.loads(path.read_text())
    failures = payload["turn_repair"]["failures"]
    failures.append(failures[0])
    path.write_text(json.dumps(payload))
    assert store.load("plan-1") is None


def test_matching_root_check_identifier_roundtrips(tmp_path):
    turn = budget()
    item = failure("first").failure_evidence[0]
    record_failure_evidence(
        replace(
            failure("first"),
            failure_evidence=(
                replace(
                    item,
                    check_id=f"{tmp_path}:layout",
                ),
            ),
        ),
        turn,
    )
    store = JsonCheckpointStore(tmp_path)
    saved = replace(_checkpoint(tmp_path), turn_repair=turn.snapshot_repairs())
    store.save(saved)
    assert store.load("plan-1") == saved


@pytest.mark.parametrize(
    "check,family",
    [
        ("Remotion yerleşim", "card overflow"),
        ("token=fixture-private", "bearer fixture-private"),
    ],
)
def test_actual_job_producer_opaque_ids_checkpoint_without_crash(tmp_path, check, family):
    from fusion_cli.tools.job_evidence import (
        FAILURE_PROTOCOL,
        completed_evidence,
        prepare_manifest,
        save_manifest,
    )

    (tmp_path / "a.tsx").write_text("fixture")
    manifest = prepare_manifest({"failure_check": check, "failure_sources": ["a.tsx"]}, tmp_path)
    save_manifest(tmp_path / "job.proof.json", manifest)
    (tmp_path / "job.log").write_text(
        FAILURE_PROTOCOL + json.dumps({"version": 1, "families": [family]}) + "\n",
    )
    evidence = completed_evidence(tmp_path, "job")
    turn = budget()
    record_failure_evidence(ToolResult("ürün kusuru", ok=False, failure_evidence=evidence), turn)
    saved = replace(_checkpoint(tmp_path), turn_repair=turn.snapshot_repairs())
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    store.save(saved)
    assert store.load("plan-1") == saved
    raw = (tmp_path / "job.proof.json").read_text()
    checkpoint_raw = next((tmp_path / "checkpoints").glob("*.json")).read_text()
    assert check not in raw and check not in checkpoint_raw and family not in checkpoint_raw
    resumed = budget()
    resumed.restore_repairs(store.load("plan-1").turn_repair)
    assert not record_failure_evidence(
        ToolResult("aynı sorgu", ok=False, failure_evidence=evidence), resumed
    ).is_new_failure
