"""Paket 8 için mevcut public checkpoint yüzeyinin çevrimdışı sözleşmeleri."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.core.checkpoint import WorkflowCheckpoint
from fusion_cli.core.errors import CheckpointConflictError
from fusion_cli.core.execution_plan import ExecutionPlan
from fusion_cli.memory.checkpoint_store import JsonCheckpointStore


def _checkpoint(root: Path, plan_id: str) -> WorkflowCheckpoint:
    return WorkflowCheckpoint(
        plan=ExecutionPlan(plan_id=plan_id, task="Devam kaydını koru", steps=()),
        root=str(root),
        conversation_id="task8-conversation",
        completed_step_ids=(),
        updated_at=1.0,
    )


def test_task8_checkpoint_public_round_trip_korunur(tmp_path: Path) -> None:
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    checkpoint = _checkpoint(tmp_path, "task8-plan")

    store.save(checkpoint)

    assert store.load(checkpoint.plan.plan_id) == checkpoint
    assert store.find_resumable(checkpoint.root, checkpoint.conversation_id) == checkpoint


@pytest.mark.parametrize("plan_ids", [("a/b", "a_b"), (".", "..")])
def test_task8_checkpoint_farkli_plan_kimlikleri_ezilmez(
    tmp_path: Path, plan_ids: tuple[str, str]
) -> None:
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    first = _checkpoint(tmp_path, plan_ids[0])
    second = replace(_checkpoint(tmp_path, plan_ids[1]), updated_at=2.0)

    store.save(first)
    store.save(second)

    assert store.load(first.plan.plan_id) == first
    assert store.load(second.plan.plan_id) == second


@pytest.mark.parametrize("schema_version", [999, True, -1])
def test_task8_checkpoint_gecersiz_dis_sema_devam_edilemez(
    tmp_path: Path, schema_version: int | bool
) -> None:
    directory = tmp_path / "checkpoints"
    store = JsonCheckpointStore(directory)
    checkpoint = _checkpoint(tmp_path, "task8-plan")
    store.save(checkpoint)
    # Dosyayı public save üretir; yeni dosya adlandırma sözleşmesine bağlanmayız.
    path = next(directory.glob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = schema_version
    path.write_text(json.dumps(payload), encoding="utf-8")
    original_bytes = path.read_bytes()

    assert store.load(checkpoint.plan.plan_id) is None
    assert store.find_resumable(checkpoint.root, checkpoint.conversation_id) is None
    assert path.read_bytes() == original_bytes


def test_task8_checkpoint_replace_oncesi_hata_eski_kaydi_korur(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "checkpoints"
    store = JsonCheckpointStore(directory)
    checkpoint = _checkpoint(tmp_path, "task8-plan")
    store.save(checkpoint)
    checkpoint = store.load(checkpoint.plan.plan_id)

    def fail_replace(source: Path, target: Path) -> Path:
        raise OSError("Kontrollü replace öncesi hata")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="Kontrollü replace öncesi hata"):
        store.save(replace(checkpoint, updated_at=2.0))

    assert store.load(checkpoint.plan.plan_id) == checkpoint
    assert not tuple(directory.glob("*.tmp"))


def test_task8_same_plan_name_in_two_conversations_is_isolated(tmp_path: Path) -> None:
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    first = _checkpoint(tmp_path, "shared")
    second = replace(first, conversation_id="another", updated_at=2.0)
    store.save(first)
    store.save(second)
    assert store.find_resumable(first.root, first.conversation_id) == first
    assert store.find_resumable(second.root, second.conversation_id) == second
    # Legacy plan-only lookup cannot guess the intended conversation.
    assert store.load("shared") is None


def test_repl_session_identity_scopes_real_checkpoint_resume(tmp_path: Path) -> None:
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    first = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    other = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    assert first.conversation_id != other.conversation_id
    checkpoint = replace(_checkpoint(tmp_path, "repl-plan"), conversation_id=first.conversation_id)
    directory = tmp_path / "checkpoints"
    owner = JsonCheckpointStore(directory, root=tmp_path, conversation_id=first.conversation_id)
    owner.save(checkpoint)
    unrelated = JsonCheckpointStore(directory, root=tmp_path, conversation_id=other.conversation_id)
    assert owner.find_resumable(str(tmp_path), first.conversation_id) == checkpoint
    assert unrelated.find_resumable(str(tmp_path), other.conversation_id) is None
    restored = ReplState(
        config=make_config(),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path,
        conversation_id=first.conversation_id,
    )
    assert restored.conversation_id == first.conversation_id


def test_task8_stale_loaded_writer_cannot_replace_new_checkpoint(tmp_path: Path) -> None:
    first_store = JsonCheckpointStore(tmp_path / "checkpoints")
    second_store = JsonCheckpointStore(tmp_path / "checkpoints")
    original = _checkpoint(tmp_path, "revision")
    first_store.save(original)
    first = first_store.load("revision")
    stale = second_store.load("revision")
    assert first is not None and stale is not None
    first_store.save(replace(first, updated_at=2.0))
    with pytest.raises(CheckpointConflictError, match=r"Checkpoint.*değiş"):
        second_store.save(replace(stale, updated_at=3.0))
    assert first_store.load("revision").updated_at == 2.0


def test_task8_explicit_compare_and_save_has_one_process_winner(tmp_path: Path) -> None:
    import subprocess
    import sys

    script = """
import sys
from pathlib import Path
from fusion_cli.core.checkpoint import WorkflowCheckpoint
from fusion_cli.core.execution_plan import ExecutionPlan
from fusion_cli.core.errors import CheckpointConflictError
from fusion_cli.memory.checkpoint_store import JsonCheckpointStore
store = JsonCheckpointStore(Path(sys.argv[1]))
checkpoint = WorkflowCheckpoint(
    ExecutionPlan("parallel", "iş", ()), sys.argv[2], "offline", (), float(sys.argv[3])
)
try:
    store.save(checkpoint, expected_revision=0)
    print("winner")
except CheckpointConflictError:
    print("conflict")
"""
    children = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(tmp_path / "checkpoints"),
                str(tmp_path),
                str(index),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in (1, 2)
    ]
    try:
        results = [child.communicate(timeout=10) for child in children]
        assert all(child.returncode == 0 for child in children), results
        assert sorted(output.strip() for output, _error in results) == ["conflict", "winner"]
        loaded = JsonCheckpointStore(tmp_path / "checkpoints").load("parallel")
        assert loaded is not None and loaded.storage_revision == 1
        assert not tuple((tmp_path / "checkpoints").glob("*.tmp"))
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()


def test_task8_loaded_legacy_zero_revision_is_not_fresh_facade(tmp_path: Path) -> None:
    directory = tmp_path / "checkpoints"
    store = JsonCheckpointStore(directory)
    store.save(_checkpoint(tmp_path, "legacy"))
    path = next(directory.glob("*.json"))
    payload = json.loads(path.read_text())
    payload["schema_version"] = 4
    payload.pop("storage_revision")
    path.write_text(json.dumps(payload))
    path.replace(directory / "legacy.json")
    loaded = store.load("legacy")
    assert loaded is not None and loaded.storage_revision == 0
    store.save(replace(loaded, updated_at=2.0))
    with pytest.raises(CheckpointConflictError):
        store.save(replace(loaded, updated_at=3.0))
    assert store.load("legacy").updated_at == 2.0
