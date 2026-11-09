from __future__ import annotations

import hashlib

import pytest

from fusion_cli.core.checkpoint import StepCheckpointEvidence, WorkflowCheckpoint
from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStep,
    RetrySafety,
    VerificationCheckKind,
)
from fusion_cli.core.workspace_fingerprint import content_digest
from fusion_cli.engines.agent import context_projection as projection
from fusion_cli.engines.agent.plan_checkpoint import _digest
from fusion_cli.engines.agent.verify_discovery import source_digest

from .fakes import RecordingSink
from .test_agent_loop import _deps


def test_large_sparse_file_does_not_read_or_return_a_partial_digest(tmp_path):
    from fusion_cli.core.read_budget import ReadBudget, ReadBudgetExceededError

    path = tmp_path / "large.py"
    with path.open("wb") as stream:
        stream.truncate(1 << 30)
    budget = ReadBudget(max_bytes=1024)
    with pytest.raises(ReadBudgetExceededError):
        content_digest([path], strict=True, read_budget=budget)
    assert budget.bytes_read == 0
    assert _digest(tmp_path, "large.py", read_budget=ReadBudget(max_bytes=1024)) == ""


def test_hashes_share_one_cumulative_byte_budget(tmp_path):
    from fusion_cli.core.read_budget import ReadBudget, ReadBudgetExceededError

    first, second = tmp_path / "a.py", tmp_path / "b.py"
    first.write_bytes(b"a" * 8)
    second.write_bytes(b"b" * 8)
    budget = ReadBudget(max_bytes=12)
    assert content_digest([first], read_budget=budget) == content_digest([first])
    with pytest.raises(ReadBudgetExceededError):
        content_digest([second], read_budget=budget)
    assert budget.bytes_read == 8


def test_bounded_hashes_preserve_legacy_file_and_sorted_directory_formats(tmp_path):
    from fusion_cli.core.read_budget import ReadBudget

    directory = tmp_path / "assets"
    (directory / "a").mkdir(parents=True)
    (directory / "a" / "item").write_bytes(b"ABC")
    (directory / "a.txt").write_bytes(b"DEF")
    assert _digest(tmp_path, "assets", read_budget=ReadBudget()) == _digest(tmp_path, "assets")
    assert (
        _digest(tmp_path, "assets/a.txt", read_budget=ReadBudget())
        == hashlib.sha256(b"DEF").hexdigest()
    )
    assert source_digest(tmp_path, read_budget=ReadBudget()) == source_digest(tmp_path)


def test_directory_entry_cap_stops_before_unbounded_materialization(tmp_path):
    from fusion_cli.core.read_budget import ReadBudget

    directory = tmp_path / "assets"
    directory.mkdir()
    for i in range(30):
        (directory / str(i)).write_bytes(b"x")
    budget = ReadBudget(max_entries=5)
    assert _digest(tmp_path, "assets", read_budget=budget) == ""
    assert budget.entries_read <= 5


def test_revoked_owner_stops_between_physical_chunks(tmp_path):
    from fusion_cli.core.read_budget import ReadBudget, ReadBudgetExceededError

    path = tmp_path / "source.py"
    path.write_bytes(b"x" * 200_000)
    active = [True]
    budget = ReadBudget(valid=lambda: active[0])
    chunks = budget.chunks(path)
    assert len(next(chunks)) <= 65_536
    before = budget.bytes_read
    active[0] = False
    with pytest.raises(ReadBudgetExceededError):
        next(chunks)
    assert budget.bytes_read == before


async def test_unknown_source_hash_cannot_equal_an_unknown_evidence_hash(tmp_path, monkeypatch):
    from fusion_cli.core.evidence import EvidenceEnvironment

    deps = _deps(tmp_path, RecordingSink())
    step = PlanStep("step", "task", (), (), (), ("condition",), "", RetrySafety.SAFE)
    environment = EvidenceEnvironment("python -V", str(tmp_path), "fixture", "", "")
    criterion = CriterionEvidence(
        "criterion",
        VerificationCheckKind.COMMAND,
        EvidenceStatus.FAILED,
        "fixture",
        source_after_digest="",
        call_id="unknown-call",
        environment=environment,
    )
    checkpoint = WorkflowCheckpoint(
        ExecutionPlan("plan", "task", (step,)),
        str(tmp_path),
        "chat",
        (),
        1,
        (StepCheckpointEvidence("step", criteria=(criterion,)),),
    )

    class Store:
        def load(self, _plan_id):
            return checkpoint

    deps.checkpoint_store = Store()
    deps.conversation_id = "chat"
    deps.context_plan_id = "plan"
    monkeypatch.setattr(projection, "source_digest", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(projection, "evidence_environment", lambda *_args, **_kwargs: environment)
    assert not (await projection.derive_context(deps)).pinned_call_ids


def test_production_checkpoint_load_has_a_shared_bounded_api(tmp_path):
    from fusion_cli.core.read_budget import ReadBudget
    from fusion_cli.memory.checkpoint_store import JsonCheckpointStore

    store = JsonCheckpointStore(tmp_path / "checkpoints", root=tmp_path, conversation_id="chat")
    checkpoint = WorkflowCheckpoint(ExecutionPlan("plan", "task", ()), str(tmp_path), "chat", (), 1)
    store.save(checkpoint)
    assert store.load_bounded("plan", read_budget=ReadBudget()) == store.load("plan")
    budget = ReadBudget(max_bytes=10)
    assert store.load_bounded("plan", read_budget=budget) is None
    assert budget.bytes_read == 0


def test_bounded_environment_preserves_normal_installed_runner_version(tmp_path):
    from fusion_cli.core.read_budget import ReadBudget
    from fusion_cli.engines.agent.verify_discovery import evidence_environment

    commands = ("python -m pytest -q",)
    legacy = evidence_environment(tmp_path, commands, runtime="fixture")
    bounded = evidence_environment(tmp_path, commands, runtime="fixture", read_budget=ReadBudget())
    assert legacy is not None and bounded == legacy


async def test_projection_shares_source_and_artifact_budget(tmp_path, monkeypatch):
    from fusion_cli.core.checkpoint import ArtifactFingerprint
    from fusion_cli.core.read_budget import ReadBudget

    source = tmp_path / "app.py"
    artifact = tmp_path / "data.bin"
    source.write_bytes(b"SOURCE12")
    artifact.write_bytes(b"ARTIFACT")
    step = PlanStep("step", "task", (), (), (), ("condition",), "", RetrySafety.SAFE)
    evidence = StepCheckpointEvidence(
        "step", artifacts=(ArtifactFingerprint("data.bin", _digest(tmp_path, "data.bin")),)
    )
    checkpoint = WorkflowCheckpoint(
        ExecutionPlan("plan", "task", (step,)), str(tmp_path), "chat", (), 1, (evidence,)
    )

    class Store:
        def load(self, _plan_id):
            return checkpoint

    deps = _deps(tmp_path, RecordingSink())
    deps.checkpoint_store = Store()
    deps.conversation_id = "chat"
    deps.context_plan_id = "plan"
    budget = ReadBudget(max_bytes=12)
    monkeypatch.setattr(projection, "ReadBudget", lambda **_kwargs: budget)
    result = await projection.derive_context(deps)
    assert budget.bytes_read == 8 and budget.exhausted
    assert not result.note and not result.pinned_call_ids


@pytest.mark.parametrize("ending", ["owner", "deadline"])
async def test_revoked_projection_stops_actual_source_reads(tmp_path, monkeypatch, ending):
    import asyncio
    import time

    from fusion_cli.core import read_budget

    (tmp_path / "app.py").write_bytes(b"x" * 200_000)
    step = PlanStep("step", "task", (), (), (), ("condition",), "", RetrySafety.SAFE)
    checkpoint = WorkflowCheckpoint(
        ExecutionPlan("plan", "task", (step,)), str(tmp_path), "chat", (), 1
    )

    class Store:
        def load(self, _plan_id):
            return checkpoint

    deps = _deps(tmp_path, RecordingSink())
    deps.checkpoint_store = Store()
    deps.conversation_id = "chat"
    deps.context_plan_id = "plan"
    actual_read = read_budget.os.read
    requests = []

    def revoke(descriptor, requested):
        requests.append(requested)
        if ending == "deadline":
            time.sleep(0.05)
        data = actual_read(descriptor, requested)
        if ending == "owner":
            deps.conversation_id = "new-owner"
        return data

    monkeypatch.setattr(read_budget.os, "read", revoke)
    if ending == "deadline":
        monkeypatch.setattr(projection, "CONTEXT_TIMEOUT_S", 0.02)
    result = await projection.derive_context(deps)
    if ending == "deadline":
        await asyncio.sleep(0.08)
    assert requests == [65_536]
    assert not result.note and not result.pinned_call_ids
