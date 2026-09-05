"""Workflow checkpoint deposunun atomiklik ve veri minimizasyonu kuralları."""

from __future__ import annotations

from fusion_cli.core.checkpoint import WorkflowCheckpoint
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStep,
    RetrySafety,
    VerificationCheck,
    VerificationCheckKind,
)
from fusion_cli.memory.checkpoint_store import JsonCheckpointStore


def _checkpoint(root) -> WorkflowCheckpoint:
    step = PlanStep(
        step_id="inspect",
        goal="kaynağı incele",
        depends_on=(),
        expected_effects=(),
        allowed_tool_families=("files",),
        success_criteria=("kaynak bulundu",),
        verification_hint="dosyayı oku",
        retry_safety=RetrySafety.SAFE,
        verification_checks=(
            VerificationCheck(
                criterion_id="kaynak bulundu",
                kind=VerificationCheckKind.COMMAND,
                target="pytest -q",
            ),
        ),
    )
    return WorkflowCheckpoint(
        plan=ExecutionPlan(plan_id="plan-1", task="özellik ekle", steps=(step,)),
        root=str(root),
        conversation_id="conv-1",
        completed_step_ids=("inspect",),
        updated_at=123.0,
    )


def test_checkpoint_atomik_round_trip(tmp_path):
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    checkpoint = _checkpoint(tmp_path)

    store.save(checkpoint)

    assert store.load("plan-1") == checkpoint
    assert not tuple((tmp_path / "checkpoints").glob("*.tmp"))


def test_bozuk_checkpoint_yok_sayilir(tmp_path):
    directory = tmp_path / "checkpoints"
    directory.mkdir()
    (directory / "plan-1.json").write_text("{bozuk", encoding="utf-8")

    assert JsonCheckpointStore(directory).load("plan-1") is None


def test_checkpoint_ham_prompt_ve_arac_ciktisi_saklamaz(tmp_path):
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    store.save(_checkpoint(tmp_path))

    raw = (tmp_path / "checkpoints" / "plan-1.json").read_text(encoding="utf-8")

    assert "messages" not in raw
    assert "tool_output" not in raw
    assert '"prompt":' not in raw


def test_devam_edilebilir_checkpoint_kok_ve_konusmayla_bulunur(tmp_path):
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    checkpoint = _checkpoint(tmp_path)
    store.save(checkpoint)

    assert store.find_resumable(str(tmp_path), "conv-1") == checkpoint
    assert store.find_resumable(str(tmp_path), "baska") is None
