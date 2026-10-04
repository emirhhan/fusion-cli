"""Zamanlananlar: sıradaki çalışma hesabı, depo ve vadesi geleni verme."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fusion_cli.appserver import schedule

TZ = timezone(timedelta(hours=3))
#: 5 Ekim 2026 Pazartesi 10:00 (+03).
NOW = datetime(2026, 10, 5, 10, 0, tzinfo=TZ)


def _at(day: int, hour: int, minute: int = 0) -> float:
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ).timestamp()


def _new(tmp_path, **fields):
    data = {"gorev": "Stok raporunu çıkar", "kok": str(tmp_path), **fields}
    return schedule.save_schedule(data, tmp_path / "z.json", NOW)


def test_gunluk_gorev_saat_gectiyse_yarina_kalir():
    assert schedule.next_run({"tur": "gunluk", "saat": "14:30"}, NOW) == _at(5, 14, 30)
    assert schedule.next_run({"tur": "gunluk", "saat": "09:00"}, NOW) == _at(6, 9)
    assert schedule.next_run({"tur": "gunluk", "saat": "10:00"}, NOW) == _at(6, 10)


def test_haftalik_gorev_secili_gunlerde_calisir():
    spec = {"tur": "haftalik", "saat": "09:00", "gunler": [0, 3]}

    assert schedule.next_run(spec, NOW) == _at(8, 9)
    assert schedule.next_run(spec, datetime(2026, 10, 8, 9, 0, tzinfo=TZ)) == _at(12, 9)


def test_tek_seferlik_ve_aralik():
    assert schedule.next_run({"tur": "bir_kez", "zaman": _at(7, 8)}, NOW) == _at(7, 8)
    assert schedule.next_run({"tur": "bir_kez", "zaman": _at(4, 8)}, NOW) is None
    assert schedule.next_run({"tur": "aralik", "dakika": 30}, NOW) == _at(5, 10, 30)


@pytest.mark.parametrize(
    "spec",
    [
        {"tur": "gunluk", "saat": "25:00"},
        {"tur": "gunluk", "saat": "dokuz"},
        {"tur": "haftalik", "saat": "09:00", "gunler": []},
        {"tur": "haftalik", "saat": "09:00", "gunler": [7]},
        {"tur": "aralik", "dakika": 1},
        {"tur": "aralik", "dakika": True},
        {"tur": "bir_kez"},
        {"tur": "aylik"},
    ],
)
def test_gecersiz_zamanlama_reddedilir(spec):
    with pytest.raises(schedule.ScheduleError):
        schedule.next_run(spec, NOW)


def test_kayit_dogrulanir_ve_bilinmeyen_alan_tasinmaz(tmp_path):
    result = _new(tmp_path, tur="gunluk", saat="09:00", baslik="  Sabah raporu ", sizinti="x")

    task = result["gorev"]
    assert result["ok"] and task["baslik"] == "Sabah raporu" and task["etkin"] is True
    assert task["sonraki"] == _at(6, 9) and "sizinti" not in task and len(task["id"]) == 32
    assert _new(tmp_path, tur="gunluk", saat="09:00", gorev="  ")["ok"] is False
    assert _new(tmp_path, tur="gunluk", saat="09:00", kok=str(tmp_path / "yok"))["ok"] is False
    assert "geçmişte" in _new(tmp_path, tur="bir_kez", zaman=_at(1, 9))["metin"]


def test_baslik_verilmezse_gorevden_turetilir_ve_liste_siralanir(tmp_path):
    _new(tmp_path, tur="gunluk", saat="18:00", gorev="Akşam işi")
    _new(tmp_path, tur="gunluk", saat="12:00", gorev="Öğle işi")

    titles = [g["baslik"] for g in schedule.list_schedules(tmp_path / "z.json")["gorevler"]]

    assert titles == ["Öğle işi", "Akşam işi"]


def test_vadesi_gelen_gorev_bir_kez_verilir_ve_takvim_ilerler(tmp_path):
    path = tmp_path / "z.json"
    _new(tmp_path, tur="gunluk", saat="11:00")
    _new(tmp_path, tur="gunluk", saat="15:00", gorev="Sonraki")

    assert schedule.claim_due(path, NOW)["gorevler"] == []
    at_eleven = datetime(2026, 10, 5, 11, 0, 20, tzinfo=TZ)
    first = schedule.claim_due(path, at_eleven)["gorevler"]
    second = schedule.claim_due(path, at_eleven + timedelta(seconds=30))["gorevler"]

    assert [g["gorev"] for g in first] == ["Stok raporunu çıkar"]
    assert first[0]["sonraki"] == _at(6, 11) and first[0]["son_gecikmeli"] is False
    assert second == []


def test_tek_seferlik_gorev_calisinca_kapanir_gec_kalan_isaretlenir(tmp_path):
    path = tmp_path / "z.json"
    _new(tmp_path, tur="bir_kez", zaman=_at(5, 12))

    late = schedule.claim_due(path, datetime(2026, 10, 6, 9, 0, tzinfo=TZ))["gorevler"]

    assert late[0]["son_gecikmeli"] is True and late[0]["etkin"] is False
    assert late[0]["sonraki"] is None
    assert schedule.claim_due(path, datetime(2026, 10, 7, 9, 0, tzinfo=TZ))["gorevler"] == []


def test_duraklatilan_gorev_verilmez_surdurulunce_zamani_yeniden_hesaplanir(tmp_path):
    path = tmp_path / "z.json"
    task_id = _new(tmp_path, tur="gunluk", saat="11:00")["gorev"]["id"]

    assert (
        schedule.set_enabled({"id": task_id, "etkin": False}, path, NOW)["gorev"]["etkin"] is False
    )
    assert schedule.claim_due(path, datetime(2026, 10, 5, 12, 0, tzinfo=TZ))["gorevler"] == []
    resumed = schedule.set_enabled(
        {"id": task_id, "etkin": True}, path, datetime(2026, 10, 5, 12, 0, tzinfo=TZ)
    )
    assert resumed["gorev"]["etkin"] is True and resumed["gorev"]["sonraki"] == _at(6, 11)
    assert schedule.set_enabled({"id": "yok", "etkin": True}, path, NOW)["ok"] is False


def test_guncelleme_tur_degisince_eski_alanlari_birakir_silme_calisir(tmp_path):
    path = tmp_path / "z.json"
    task_id = _new(tmp_path, tur="haftalik", saat="09:00", gunler=[2])["gorev"]["id"]

    updated = schedule.save_schedule(
        {"id": task_id, "gorev": "Yeni", "kok": str(tmp_path), "tur": "aralik", "dakika": 60},
        path,
        NOW,
    )["gorev"]

    assert updated["id"] == task_id and updated["tur"] == "aralik"
    assert "gunler" not in updated and "saat" not in updated
    assert (
        schedule.save_schedule(
            {"id": "yok", "gorev": "x", "kok": str(tmp_path), "tur": "aralik", "dakika": 60},
            path,
            NOW,
        )["ok"]
        is False
    )
    assert schedule.delete_schedule({"id": task_id}, path) == {"ok": True}
    assert schedule.delete_schedule({"id": task_id}, path)["ok"] is False


def test_simdi_calistir_takvimi_degistirmez(tmp_path):
    path = tmp_path / "z.json"
    task = _new(tmp_path, tur="gunluk", saat="11:00")["gorev"]

    started = schedule.run_now({"id": task["id"]}, path, NOW)["gorev"]

    assert started["son_calisma"] == NOW.timestamp() and started["sonraki"] == task["sonraki"]
    assert schedule.run_now({"id": "yok"}, path, NOW)["ok"] is False


def test_bozuk_depo_bos_sayilir_ve_gorev_siniri_uygulanir(tmp_path, monkeypatch):
    path = tmp_path / "z.json"
    path.write_text("{bozuk", encoding="utf-8")
    assert schedule.list_schedules(path)["gorevler"] == []
    monkeypatch.setattr(schedule, "MAX_SCHEDULES", 1)
    assert _new(tmp_path, tur="gunluk", saat="11:00")["ok"] is True
    assert "En çok" in _new(tmp_path, tur="gunluk", saat="12:00")["metin"]
