"""Zamanlananlar: sıradaki çalışma hesabı, depo ve vadesi geleni verme."""

from __future__ import annotations

import json
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


def test_bozuk_depo_hata_verir_ve_gorev_siniri_uygulanir(tmp_path, monkeypatch):
    path = tmp_path / "z.json"
    path.write_text("{bozuk", encoding="utf-8")
    assert schedule.list_schedules(path)["ok"] is False
    assert path.read_text(encoding="utf-8") == "{bozuk"
    assert _new(tmp_path, tur="gunluk", saat="10:00")["ok"] is False
    assert path.read_text(encoding="utf-8") == "{bozuk"
    path.unlink()
    monkeypatch.setattr(schedule, "MAX_SCHEDULES", 1)
    assert _new(tmp_path, tur="gunluk", saat="11:00")["ok"] is True
    assert "En çok" in _new(tmp_path, tur="gunluk", saat="12:00")["metin"]


def _bozuk_kayitli_depo(tmp_path):
    """Biri geçerli, biri bozuk `teslimler` taşıyan iki kayıt (S2-12)."""

    iyi = _new(tmp_path, tur="gunluk", saat="09:00")["gorev"]
    path = tmp_path / "z.json"
    kayitlar = json.loads(path.read_text(encoding="utf-8"))
    bozuk = {**kayitlar[0], "id": "bozuk-1", "teslimler": "liste-degil"}
    path.write_text(json.dumps([*kayitlar, bozuk, "kayit-degil"]), encoding="utf-8")
    return path, iyi


def test_tek_bozuk_kayit_listeyi_bos_gostermez_ve_yazmalari_engeller(tmp_path):
    path, iyi = _bozuk_kayitli_depo(tmp_path)
    onceki = path.read_bytes()

    listed = schedule.list_schedules(path)

    assert listed["ok"] is True and listed["bozuk_kayit"] == 2
    assert [item["id"] for item in listed["gorevler"]] == [iyi["id"]]
    # Bilinçli sözleşme (test_schedule_delivery): bozuk kayıt varken hiçbir yazma yapılmaz.
    assert schedule.claim_due(path, NOW)["ok"] is False
    assert path.read_bytes() == onceki


def test_bozuk_kayitlar_acik_eylemle_yedeklenip_ayrilir_sonra_gorevler_calisir(tmp_path):

    path, iyi = _bozuk_kayitli_depo(tmp_path)

    sonuc = schedule.quarantine_invalid(path)

    assert sonuc["ok"] is True and sonuc["ayrilan"] == 2
    yedek = tmp_path / sonuc["yedek"]
    yedeklenen = json.loads(yedek.read_text(encoding="utf-8"))
    assert yedeklenen[0]["id"] == "bozuk-1" and "kayit-degil" in yedeklenen
    assert [item["id"] for item in json.loads(path.read_text(encoding="utf-8"))] == [iyi["id"]]
    due = schedule.claim_due(path, datetime.fromtimestamp(iyi["sonraki"] + 60, tz=TZ))
    assert due["ok"] is True and len(due["gorevler"]) == 1
    # Tekrar ayırmak yeni yedek üretmez.
    assert schedule.quarantine_invalid(path) == {"ok": True, "ayrilan": 0}
    assert len(list(tmp_path.glob("z.json.bad-*"))) == 1


def test_yedek_yazilamazsa_depoya_dokunulmaz(tmp_path, monkeypatch):
    path, _iyi = _bozuk_kayitli_depo(tmp_path)
    onceki = path.read_bytes()
    from pathlib import Path

    gercek = Path.write_text

    def reddet(self, *args, **kwargs):
        if ".bad-" in self.name:
            raise PermissionError("yedek yazılamıyor")
        return gercek(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", reddet)

    assert schedule.quarantine_invalid(path)["ok"] is False
    assert path.read_bytes() == onceki


def test_bozuk_ayirma_rotasi_kayitlidir():
    assert "zamanlama.bozuklari_ayir" in schedule.SCHEDULE_ROUTES


@pytest.mark.parametrize("kok", ["/", "~", "~/"])
def test_kok_dizin_ve_ev_klasoru_reddedilir(tmp_path, monkeypatch, kok):
    """S2-25: gözetimsiz görev `/` ya da ev klasöründe çalışmaz."""
    monkeypatch.setenv("HOME", str(tmp_path))
    sonuc = schedule.save_schedule(
        {"gorev": "Her şeyi tara", "kok": kok, "tur": "gunluk", "saat": "09:00"},
        tmp_path / "z.json",
        NOW,
    )

    assert sonuc["ok"] is False
    assert "proje klasörü" in sonuc["metin"]
    assert not (tmp_path / "z.json").exists()


def test_ev_klasorunun_altindaki_proje_kabul_edilir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    proje = tmp_path / "proje"
    proje.mkdir()

    sonuc = schedule.save_schedule(
        {"gorev": "Rapor", "kok": str(proje), "tur": "gunluk", "saat": "09:00"},
        tmp_path / "z.json",
        NOW,
    )

    assert sonuc["ok"] is True


def test_eski_kayittaki_tehlikeli_kok_vadesi_gelince_verilmez_ve_durdurulur(tmp_path, monkeypatch):
    """Doğrulamadan önce kaydedilmiş `/` kökü, vadesi gelince de çalışmamalı."""
    monkeypatch.setenv("HOME", str(tmp_path))
    proje = tmp_path / "proje"
    proje.mkdir()
    yol = tmp_path / "z.json"
    guvenli = _new(tmp_path, kok=str(proje), tur="gunluk", saat="11:00")["gorev"]

    kayitlar = json.loads(yol.read_text(encoding="utf-8"))
    kayitlar.append({**guvenli, "id": "eski", "kok": "/", "baslik": "eski kök"})
    yol.write_text(json.dumps(kayitlar), encoding="utf-8")

    verilen = schedule.claim_due(yol, datetime(2026, 10, 5, 12, 0, tzinfo=TZ))

    assert [g["id"] for g in verilen["gorevler"]] == [guvenli["id"]]
    liste = {g["id"]: g for g in schedule.list_schedules(yol)["gorevler"]}
    assert liste["eski"]["etkin"] is False
    assert "proje klasörü" in liste["eski"]["durdurma_nedeni"]


def test_simdi_calistir_tehlikeli_kokte_reddedilir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    proje = tmp_path / "proje"
    proje.mkdir()
    yol = tmp_path / "z.json"
    guvenli = _new(tmp_path, kok=str(proje), tur="gunluk", saat="11:00")["gorev"]
    kayitlar = json.loads(yol.read_text(encoding="utf-8"))
    kayitlar.append({**guvenli, "id": "eski", "kok": "/"})
    yol.write_text(json.dumps(kayitlar), encoding="utf-8")

    sonuc = schedule.run_now({"id": "eski"}, yol, NOW)

    assert sonuc["ok"] is False
    assert "proje klasörü" in sonuc["metin"]


# --- Cron ifadesi (P-038) ------------------------------------------------------- #


def test_cron_turu_siradaki_zamani_ifadeden_hesaplar():
    assert schedule.next_run({"tur": "cron", "cron": "30 10 * * *"}, NOW) == _at(5, 10, 30)
    assert schedule.next_run({"tur": "cron", "cron": "0 9 * * *"}, NOW) == _at(6, 9)


@pytest.mark.parametrize(
    "spec",
    [
        {"tur": "cron"},
        {"tur": "cron", "cron": "bozuk"},
        {"tur": "cron", "cron": "*/5 * * * *"},
        {"tur": "cron", "cron": "* * * * *"},
    ],
)
def test_cron_eksik_bozuk_ya_da_cok_sik_ifade_reddedilir(spec):
    with pytest.raises(schedule.ScheduleError):
        schedule.next_run(spec, NOW)


def test_cron_gorevi_kaydedilir_ve_ifade_normalize_edilir(tmp_path):
    path = tmp_path / "z.json"
    sonuc = schedule.save_schedule(
        {"gorev": "rapor", "kok": str(tmp_path), "tur": "cron", "cron": " 0  9 * * 1-5 "},
        path,
        NOW,
    )
    assert sonuc["ok"] is True
    assert sonuc["gorev"]["cron"] == "0 9 * * 1-5"
    assert "dakika" not in sonuc["gorev"]


@pytest.mark.parametrize("ifade", ["*/1 9 * * *", "* 9 * * *", "0,5 9 * * *", "50,59 9 * * *"])
def test_cron_siklik_denetimi_ilk_vadeden_bagimsiz(ifade):
    """Ölçüldü (31 Ekim): saat 08:00'da '*/1 9 * * *' kaydediliyordu (ilk vade 1 saat
    sonra); ilk çalışmadan sonra `_advance` hata yutup görevi sessizce kapatıyordu."""
    sabah = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)
    with pytest.raises(schedule.ScheduleError):
        schedule.next_run({"tur": "cron", "cron": ifade}, sabah)


@pytest.mark.parametrize("ifade", ["*/15 * * * *", "0 9 * * *", "0,30 9-18 * * 1-5"])
def test_cron_yeterince_seyrek_ifade_kabul_edilir(ifade):
    sabah = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)
    assert schedule.next_run({"tur": "cron", "cron": ifade}, sabah) is not None


def test_calisma_gecmisi_en_yeni_once_ve_tavanli_tutulur(tmp_path):
    """P-038: kalıcı görev yalnız `son_calisma` tutuyordu; sonuç ve sohbet görünmüyordu."""
    gorev = _new(tmp_path, tur="aralik", dakika=30)["gorev"]
    yol = tmp_path / "z.json"
    for sira in range(schedule.MAX_RUN_HISTORY + 2):
        sonuc = schedule.record_run(
            {"id": gorev["id"], "sohbet_id": f"s{sira}", "durum": "tamam", "ozet": "x" * 999},
            yol,
            NOW,
        )
        assert sonuc["ok"] is True
    gecmis = sonuc["gorev"]["gecmis"]
    assert len(gecmis) == schedule.MAX_RUN_HISTORY
    assert gecmis[0]["sohbet_id"] == f"s{schedule.MAX_RUN_HISTORY + 1}"
    assert len(gecmis[0]["ozet"]) == schedule.MAX_RUN_SUMMARY
    # Görev düzenlenince geçmiş korunur.
    guncel = schedule.save_schedule(
        {"id": gorev["id"], "gorev": "yeni", "kok": str(tmp_path), "tur": "aralik", "dakika": 30},
        yol,
        NOW,
    )
    assert len(guncel["gorev"]["gecmis"]) == schedule.MAX_RUN_HISTORY


def test_calisma_kaydi_gecersiz_durum_ve_bilinmeyen_gorevi_reddeder(tmp_path):
    gorev = _new(tmp_path, tur="aralik", dakika=30)["gorev"]
    yol = tmp_path / "z.json"
    assert (
        schedule.record_run({"id": gorev["id"], "sohbet_id": "s", "durum": "?"}, yol)["ok"] is False
    )
    assert schedule.record_run({"id": "yok", "sohbet_id": "s", "durum": "hata"}, yol)["ok"] is False
    assert "zamanlama.calisma_kaydet" in schedule.SCHEDULE_ROUTES
