"""Workflow checkpoint deposunun atomiklik ve veri minimizasyonu kuralları."""

from __future__ import annotations

import json
from dataclasses import replace

from fusion_cli.core.checkpoint import (
    ArtifactFingerprint,
    StepCheckpointEvidence,
    WorkflowBudgetUsage,
    WorkflowCheckpoint,
)
from fusion_cli.core.constants import MAX_CHECKPOINT_OUTPUT_CHARS
from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus, ToolUse
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanPhase,
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


def test_checkpoint_plan_fazi_revizyonu_ve_ilerleme_izini_korur(tmp_path):
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    checkpoint = _checkpoint(tmp_path)
    step = replace(
        checkpoint.plan.steps[0],
        phase=PlanPhase.DISCOVERY,
        expected_effects=(),
        revision=2,
        last_progress_fingerprint="abc123",
    )
    checkpoint = replace(checkpoint, plan=replace(checkpoint.plan, steps=(step,)))

    store.save(checkpoint)

    assert store.load("plan-1") == checkpoint


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


def _evidence(output: str = "tamam", secret_arg: str = "x") -> StepCheckpointEvidence:
    return StepCheckpointEvidence(
        step_id="inspect",
        criteria=(
            CriterionEvidence(
                criterion_id="kaynak bulundu",
                kind=VerificationCheckKind.COMMAND,
                status=EvidenceStatus.PASSED,
                summary="pytest -q çalıştı",
                command="pytest -q",
                output=output,
            ),
        ),
        artifacts=(ArtifactFingerprint(path="player.gd", digest="abc"),),
        tool_uses=(
            ToolUse(
                name="shell",
                ok=True,
                mutating=False,
                arguments={"command": secret_arg},
                output=output,
            ),
        ),
        tool_calls=1,
        mutation_calls=0,
        already_done_calls=0,
    )


def test_kanit_ve_zarf_harcamasi_round_trip_korunur(tmp_path):
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    checkpoint = replace(
        _checkpoint(tmp_path),
        step_evidence=(_evidence(),),
        budget_usage=(WorkflowBudgetUsage(envelope="per_step", scope="inspect", calls=3),),
    )

    store.save(checkpoint)

    assert store.load("plan-1") == checkpoint


def test_eski_surum_checkpoint_kanitsiz_okunur(tmp_path):
    directory = tmp_path / "checkpoints"
    store = JsonCheckpointStore(directory)
    store.save(_checkpoint(tmp_path))
    path = directory / "plan-1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    payload.pop("step_evidence")
    payload.pop("budget_usage")
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = store.load("plan-1")

    assert loaded is not None
    assert loaded.step_evidence == ()
    assert loaded.budget_usage == ()


def test_kanit_ciktisi_maskelenir_ve_sinirlanir(tmp_path):
    store = JsonCheckpointStore(tmp_path / "checkpoints")
    store.save(
        replace(
            _checkpoint(tmp_path),
            step_evidence=(
                _evidence(
                    output="api_key=sk-canli-anahtar\n" + "x" * (MAX_CHECKPOINT_OUTPUT_CHARS + 500),
                    secret_arg="cat .env  # password=gizli-parola",
                ),
            ),
        )
    )

    raw = (tmp_path / "checkpoints" / "plan-1.json").read_text(encoding="utf-8")
    saved = store.load("plan-1")

    assert "sk-canli-anahtar" not in raw
    assert "gizli-parola" not in raw
    assert saved is not None
    assert len(saved.step_evidence[0].tool_uses[0].output) == MAX_CHECKPOINT_OUTPUT_CHARS
    assert len(saved.step_evidence[0].criteria[0].output) == MAX_CHECKPOINT_OUTPUT_CHARS
