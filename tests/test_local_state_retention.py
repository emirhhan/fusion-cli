"""Fusion'ın kendi ürettiği iz/artifact/checkpoint dosyalarının 30 günlük saklaması (L1-30, M1-44).

Ölçüldü (30 Ekim): `memory/traces` ve `memory/artifacts` hiç temizlenmiyordu (bu makinede 134
iz dosyası, 6,9 MB); tamamlanan workflow checkpoint'leri de sonsuza dek kalıyordu. Temizlik
yalnız bu üç Fusion klasöründe, yalnız bilinen uzantılı düzenli dosyalarda çalışır.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from fusion_cli.core.checkpoint import WorkflowCheckpoint
from fusion_cli.core.execution_plan import ExecutionPlan, PlanStatus
from fusion_cli.engines.retention import (
    LOCAL_STATE_RETENTION_S,
    purge_local_state,
    purge_local_state_daily,
)
from fusion_cli.memory.checkpoint_store import JsonCheckpointStore

DAY = 86_400.0
NOW = 10_000_000.0


def _aged(path: Path, days: float, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    stamp = NOW - days * DAY
    os.utime(path, (stamp, stamp))
    return path


def test_eski_izler_silinir_taze_ve_yabanci_dosyalar_kalir(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    old = _aged(memory / "traces" / "eski.jsonl", 31)
    fresh = _aged(memory / "traces" / "taze.jsonl", 2)
    foreign = _aged(memory / "traces" / "not.md", 90)
    sibling = _aged(memory / "audit" / "eski.jsonl", 90)

    report = purge_local_state(memory, now=NOW)

    assert not old.exists()
    assert fresh.exists() and foreign.exists() and sibling.exists()
    assert report.traces == 1


def test_eski_artifact_oturumu_silinir_icinde_taze_dosya_olan_kalir(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    old_dir = memory / "artifacts" / "20260101-000000-000001"
    _aged(old_dir / "001-run_shell.txt", 40)
    _aged(old_dir / "002-run_shell.txt", 35)
    mixed = memory / "artifacts" / "20260901-000000-000001"
    old_in_mixed = _aged(mixed / "001-a.txt", 40)
    fresh_in_mixed = _aged(mixed / "002-b.txt", 1)
    stranger = _aged(memory / "artifacts" / "20260101-000000-000002" / "kullanici.docx", 99)

    report = purge_local_state(memory, now=NOW)

    assert not old_dir.exists()
    assert not old_in_mixed.exists() and fresh_in_mixed.exists()
    # Fusion'ın yazmadığı uzantı: dosya da, onu tutan klasör de kalır.
    assert stranger.exists()
    assert report.artifacts == 3


def test_sembolik_baglar_izlenmez_hedef_dosya_silinmez(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    outside = _aged(tmp_path / "kullanici.jsonl", 365)
    (memory / "traces").mkdir(parents=True)
    link = memory / "traces" / "kisayol.jsonl"
    link.symlink_to(outside)
    old_stamp = NOW - 90 * DAY
    os.utime(link, (old_stamp, old_stamp), follow_symlinks=False)
    linked_dir = memory / "artifacts" / "baglanti"
    linked_dir.parent.mkdir(parents=True)
    victim_dir = tmp_path / "baska-klasor"
    _aged(victim_dir / "001-x.txt", 365)
    linked_dir.symlink_to(victim_dir, target_is_directory=True)

    purge_local_state(memory, now=NOW)

    assert outside.exists() and link.is_symlink()
    assert (victim_dir / "001-x.txt").exists()


def _checkpoint(root: Path, plan_id: str, status: PlanStatus, updated_days_ago: float):
    plan = ExecutionPlan(plan_id=plan_id, task="görev", steps=(), status=status)
    return WorkflowCheckpoint(
        plan=plan,
        root=str(root),
        conversation_id="konusma",
        completed_step_ids=(),
        updated_at=NOW - updated_days_ago * DAY,
    )


def test_yalniz_eski_tamamlanmis_checkpointler_silinir(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    directory = memory / "workflow-checkpoints"
    store = JsonCheckpointStore(directory)
    root = tmp_path / "proje"
    root.mkdir()
    cases = {
        "eski-tamam": (PlanStatus.COMPLETED, 40, False),
        "taze-tamam": (PlanStatus.COMPLETED, 3, True),
        "eski-calisan": (PlanStatus.RUNNING, 40, True),
        "eski-duraklatilmis": (PlanStatus.PAUSED, 40, True),
        "eski-basarisiz": (PlanStatus.FAILED, 40, True),
    }
    for plan_id, (status, age, _) in cases.items():
        store.save(_checkpoint(root, plan_id, status, age))
        # Dosyanın değişme zamanı da eskidir (ucuz ön eleme mtime'a bakar).
        stamp = NOW - age * DAY
        os.utime(store._canonical((str(root.resolve()), "konusma", plan_id)), (stamp, stamp))
    corrupt = _aged(directory / "bozuk.json", 90, "{bozuk")

    report = purge_local_state(memory, now=NOW)

    for plan_id, (_, _, kept) in cases.items():
        assert (store.load(plan_id) is not None) is kept, plan_id
    assert corrupt.exists()
    assert report.checkpoints == 1


def test_gunluk_damga_ikinci_cagriyi_atlar_bir_gun_sonra_yeniden_calisir(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    first = _aged(memory / "traces" / "a.jsonl", 40)

    assert purge_local_state_daily(memory, now=NOW) is not None
    assert not first.exists()
    second = _aged(memory / "traces" / "b.jsonl", 40)

    assert purge_local_state_daily(memory, now=NOW + 60) is None
    assert second.exists()
    assert purge_local_state_daily(memory, now=NOW + DAY + 1) is not None
    assert not second.exists()


def test_saklama_suresi_otuz_gundur() -> None:
    assert LOCAL_STATE_RETENTION_S == 30 * DAY


def test_dizin_yoksa_sessizce_gecer(tmp_path: Path) -> None:
    report = purge_local_state(tmp_path / "yok", now=NOW)
    assert (report.traces, report.artifacts, report.checkpoints) == (0, 0, 0)
    assert replace(report) == report
