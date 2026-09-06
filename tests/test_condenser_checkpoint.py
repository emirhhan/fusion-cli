"""Özetleme olayı devam kaydına yazılır.

Bir oturum özetlendikten sonra duraklarsa, devam eden tur neyin özetlendiğini
bilmelidir: aksi halde "bu dosyayı zaten okumuştum" sanır ya da yapılmış işi
yeniden yapar. OpenHands'in condenser'ı da özetlemeyi olay kaydına yazar.
"""

from __future__ import annotations

from fusion_cli.core.checkpoint import WorkflowCheckpoint
from fusion_cli.core.execution_plan import ExecutionPlan, PlanStatus
from fusion_cli.memory.checkpoint_store import JsonCheckpointStore


def _checkpoint(root, *, condensations: int) -> WorkflowCheckpoint:
    return WorkflowCheckpoint(
        plan=ExecutionPlan("plan-1", "iş", (), status=PlanStatus.PAUSED),
        root=str(root),
        conversation_id="conv",
        completed_step_ids=(),
        updated_at=1.0,
        condensations=condensations,
    )


def test_ozetleme_sayisi_round_trip_korunur(tmp_path):
    store = JsonCheckpointStore(tmp_path)
    kayit = _checkpoint(tmp_path, condensations=2)

    store.save(kayit)

    assert store.load("plan-1") == kayit


def test_eski_kayitta_alan_yoksa_sifir_sayilir(tmp_path):
    import json

    store = JsonCheckpointStore(tmp_path)
    store.save(_checkpoint(tmp_path, condensations=0))
    yol = tmp_path / "plan-1.json"
    payload = json.loads(yol.read_text(encoding="utf-8"))
    payload.pop("condensations")
    yol.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    yuklenen = store.load("plan-1")

    assert yuklenen is not None
    assert yuklenen.condensations == 0
