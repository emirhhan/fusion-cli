"""Teslim kuyruğu: kayıtlar birbirinden bağımsız ilerler, eski vadeler toplu gitmez.

Ölçüldü (29 Ekim): kuyruk kaydı görev kaydının içindedir; bir kaydın ack'i, silinmesi
ya da hiç ack almaması başka görevin teslimini etkilemez.
"""

import json
from datetime import UTC, datetime, timedelta

from fusion_cli.appserver.schedule import claim_due, delete_schedule, save_schedule
from fusion_cli.appserver.schedule_delivery import acknowledge_delivery, pending_deliveries

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def _task(path, root, title, **spec):
    result = save_schedule({"baslik": title, "gorev": title, "kok": str(root), **spec}, path, NOW)
    assert result["ok"], result
    return result["gorev"]


def test_ilk_kayit_ack_almasa_da_sonrakiler_ack_alip_ilerler(tmp_path):
    path = tmp_path / "schedule.json"
    first = NOW + timedelta(minutes=1)
    for index in range(3):
        _task(
            path,
            tmp_path,
            f"gorev-{index}",
            tur="bir_kez",
            zaman=(first + timedelta(minutes=index)).timestamp(),
        )
    claim_due(path, NOW + timedelta(hours=1))
    stuck, *others = pending_deliveries(path)
    for delivery in others:
        assert acknowledge_delivery(
            path, delivery.occurrence_id, f"schedule-{delivery.occurrence_id}"
        )
    assert pending_deliveries(path) == (stuck,)


def test_bir_gorevin_silinmesi_baska_gorevin_bekleyen_teslimini_korur(tmp_path):
    path = tmp_path / "schedule.json"
    zaman = (NOW + timedelta(minutes=1)).timestamp()
    deleted = _task(path, tmp_path, "silinecek", tur="bir_kez", zaman=zaman)
    kept = _task(path, tmp_path, "kalacak", tur="bir_kez", zaman=zaman)
    claim_due(path, NOW + timedelta(hours=1))
    assert {d.schedule_id for d in pending_deliveries(path)} == {deleted["id"], kept["id"]}
    assert delete_schedule({"id": deleted["id"]}, path)["ok"]
    assert [d.schedule_id for d in pending_deliveries(path)] == [kept["id"]]


def test_ack_bilinmeyen_vadeyi_ve_baska_kaydi_degistirmez(tmp_path):
    path = tmp_path / "schedule.json"
    _task(path, tmp_path, "gorev", tur="bir_kez", zaman=(NOW + timedelta(minutes=1)).timestamp())
    claim_due(path, NOW + timedelta(hours=1))
    before = path.read_text(encoding="utf-8")
    assert not acknowledge_delivery(path, "f" * 64, "task-x")
    assert path.read_text(encoding="utf-8") == before


def test_eski_depo_gecikmis_vadeleri_gorev_basina_tek_gecikmeli_teslim_verir(tmp_path):
    """Kuyruk alanı olmayan eski kayıtlar: kaçırılan her vade değil, görev başına bir teslim."""
    path = tmp_path / "zamanlananlar.json"
    old = (NOW - timedelta(days=3)).timestamp()
    legacy = [
        {
            "id": f"eski-{index}",
            "baslik": f"Eski {index}",
            "gorev": "rapor çıkar",
            "kok": str(tmp_path),
            "tur": "aralik",
            "dakika": 15,
            "etkin": True,
            "sonraki": old,
            "son_calisma": None,
            "olusturma": old - 10,
        }
        for index in range(3)
    ]
    path.write_text(json.dumps(legacy), encoding="utf-8")
    claimed = claim_due(path, NOW)["gorevler"]
    assert len(claimed) == 3 and all(item["son_gecikmeli"] for item in claimed)
    assert len(pending_deliveries(path)) == 3  # 3 gün * 96 vade değil, görev başına bir
    assert claim_due(path, NOW)["gorevler"] == []
