"""Zamanlayıcı sahipliği: aynı anda tek yoklayıcı (uygulama kopyaları/sekmeler arası)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

from fusion_cli.appserver import schedule
from fusion_cli.appserver.schedule_lease import (
    LEASE_MAX_S,
    LEASE_MIN_S,
    acquire_lease,
    release_lease,
)

TZ = timezone(timedelta(hours=3))
NOW = datetime(2026, 10, 5, 10, 0, tzinfo=TZ)


def test_ilk_sahip_alir_ikinci_bekler(tmp_path):
    yol = tmp_path / "z.json"

    birinci = acquire_lease("A", yol, now=1000.0, ttl=90.0)
    ikinci = acquire_lease("B", yol, now=1010.0, ttl=90.0)

    assert birinci == {"ok": True, "sahip": True, "bitis": 1090.0}
    assert ikinci["ok"] is True and ikinci["sahip"] is False
    assert ikinci["bekle_s"] == 80.0


def test_sahip_yenileyince_sure_uzar_ve_yabanci_alamaz(tmp_path):
    yol = tmp_path / "z.json"
    acquire_lease("A", yol, now=1000.0, ttl=90.0)

    yenilenen = acquire_lease("A", yol, now=1080.0, ttl=90.0)

    assert yenilenen["sahip"] is True and yenilenen["bitis"] == 1170.0
    assert acquire_lease("B", yol, now=1100.0, ttl=90.0)["sahip"] is False


def test_sahip_susarsa_sure_dolunca_baskasi_devralir(tmp_path):
    """Çöken/kapanan uygulamanın kirası sonsuza dek görevleri kilitlemez."""
    yol = tmp_path / "z.json"
    acquire_lease("A", yol, now=1000.0, ttl=90.0)

    devralan = acquire_lease("B", yol, now=1091.0, ttl=90.0)

    assert devralan["sahip"] is True
    assert acquire_lease("A", yol, now=1100.0, ttl=90.0)["sahip"] is False


def test_birakilan_kira_hemen_devralinir_yabanci_birakamaz(tmp_path):
    yol = tmp_path / "z.json"
    acquire_lease("A", yol, now=1000.0, ttl=90.0)

    assert release_lease("B", yol)["birakildi"] is False
    assert acquire_lease("B", yol, now=1001.0, ttl=90.0)["sahip"] is False
    assert release_lease("A", yol)["birakildi"] is True
    assert acquire_lease("B", yol, now=1002.0, ttl=90.0)["sahip"] is True


def test_bozuk_kira_dosyasi_kimseyi_kilitlemez(tmp_path):
    yol = tmp_path / "z.json"
    (tmp_path / "z.json.lease").write_text("{bozuk", encoding="utf-8")

    assert acquire_lease("A", yol, now=1000.0, ttl=90.0)["sahip"] is True


def test_gecersiz_sahip_ve_sure_sinirlanir(tmp_path):
    yol = tmp_path / "z.json"

    assert acquire_lease("", yol, now=1000.0)["ok"] is False
    assert acquire_lease(5, yol, now=1000.0)["ok"] is False  # type: ignore[arg-type]
    assert acquire_lease("A" * 200, yol, now=1000.0)["ok"] is False
    assert acquire_lease("A", yol, now=1000.0, ttl=1.0)["bitis"] == 1000.0 + LEASE_MIN_S
    assert acquire_lease("A", yol, now=1000.0, ttl=1e9)["bitis"] == 1000.0 + LEASE_MAX_S


def test_kira_gorev_deposunu_degistirmez(tmp_path):
    yol = tmp_path / "z.json"
    schedule.save_schedule(
        {"gorev": "Rapor", "kok": str(tmp_path), "tur": "gunluk", "saat": "11:00"}, yol, NOW
    )
    once = yol.read_text(encoding="utf-8")

    acquire_lease("A", yol, now=1000.0)

    assert yol.read_text(encoding="utf-8") == once
    assert json.loads(once)[0]["gorev"] == "Rapor"


def test_iki_yoklayici_ayni_vadeyi_iki_kez_almaz(tmp_path):
    """Ölçüldü (30 Ekim): sahiplik olmasa bile `claim_due` kilit altında atomiktir."""
    yol = tmp_path / "z.json"
    schedule.save_schedule(
        {"gorev": "Rapor", "kok": str(tmp_path), "tur": "gunluk", "saat": "11:00"}, yol, NOW
    )
    zaman = datetime(2026, 10, 5, 11, 0, 20, tzinfo=TZ)
    sonuclar: list[list[dict]] = []
    kilit = threading.Lock()

    def yokla():
        verilen = schedule.claim_due(yol, zaman)["gorevler"]
        with kilit:
            sonuclar.append(verilen)

    is_parcaciklari = [threading.Thread(target=yokla) for _ in range(8)]
    for parca in is_parcaciklari:
        parca.start()
    for parca in is_parcaciklari:
        parca.join()

    assert sum(len(verilen) for verilen in sonuclar) == 1


def test_rota_tablosunda_sahiplik_istekleri_var():
    assert "zamanlama.sahiplik" in schedule.SCHEDULE_ROUTES
    assert "zamanlama.sahiplik_birak" in schedule.SCHEDULE_ROUTES


def test_rota_isleyicileri_sahiplik_verir_ve_birakir(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule, "schedules_path", lambda: tmp_path / "z.json")
    rotalar = schedule.SCHEDULE_ROUTES

    assert rotalar["zamanlama.sahiplik"]({"sahip": "A"})["sahip"] is True
    assert rotalar["zamanlama.sahiplik"]({"sahip": "B"})["sahip"] is False
    assert rotalar["zamanlama.sahiplik"]({})["ok"] is False
    assert rotalar["zamanlama.sahiplik_birak"]({"sahip": "A"})["birakildi"] is True
    assert rotalar["zamanlama.sahiplik"]({"sahip": "B", "sure_s": 60})["sahip"] is True
