"""Zamanlama: yaz saati geçişi, kapalı cihaz ve tek sahiplik (WP17).

Ölçüldü (29 Ekim): `datetime.now().astimezone()` sabit ofsetli zaman üretir; gün
eklemek ofseti değiştirmez. Yaz saatine geçilen bölgede günlük 09:00 görevi geçişten
sonraki gün yerel 10:00'da çalışıyordu. Europe/Istanbul'da yaz saati yoktur; görev
her gün aynı yerel saatte kalmalıdır.
"""

from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from fusion_cli.appserver.schedule import claim_due, next_run, save_schedule


@pytest.fixture
def yerel_saat(monkeypatch):
    def ayarla(bolge: str) -> None:
        monkeypatch.setenv("TZ", bolge)
        time.tzset()

    yield ayarla
    monkeypatch.undo()
    time.tzset()


@pytest.mark.parametrize(
    ("bolge", "simdi", "beklenen"),
    [
        # Bahar geçişi (29 Mart 2026, 02:00 → 03:00): 09:00 yerel kalmalı.
        ("Europe/Berlin", datetime(2026, 3, 28, 10, 0), datetime(2026, 3, 29, 9, 0)),
        # Güz geçişi (25 Ekim 2026).
        ("Europe/Berlin", datetime(2026, 10, 24, 10, 0), datetime(2026, 10, 25, 9, 0)),
        ("Europe/Istanbul", datetime(2026, 3, 28, 10, 0), datetime(2026, 3, 29, 9, 0)),
    ],
)
def test_gunluk_gorev_yaz_saati_gecisinde_yerel_saatinde_kalir(yerel_saat, bolge, simdi, beklenen):
    yerel_saat(bolge)
    zone = ZoneInfo(bolge)
    after = simdi.replace(tzinfo=zone).astimezone()  # uygulamanın ürettiği sabit ofsetli an

    upcoming = next_run({"tur": "gunluk", "saat": "09:00"}, after)

    assert upcoming == beklenen.replace(tzinfo=zone).timestamp()
    assert datetime.fromtimestamp(upcoming, zone).hour == 9


def test_uc_gun_kapali_kalan_cihaz_gorevi_bir_kez_gecikmeli_verir(tmp_path, yerel_saat):
    yerel_saat("Europe/Istanbul")
    path = tmp_path / "zamanlama.json"
    zone = ZoneInfo("Europe/Istanbul")
    kurulum = datetime(2026, 10, 1, 8, 0, tzinfo=zone)
    saved = save_schedule(
        {
            "baslik": "Rapor",
            "gorev": "rapor",
            "tur": "gunluk",
            "saat": "09:00",
            "etkin": True,
            "kok": str(tmp_path),
        },
        path,
        kurulum,
    )
    assert saved["ok"], saved

    acilis = datetime(2026, 10, 4, 12, 0, tzinfo=zone)
    first = claim_due(path, acilis)
    second = claim_due(path, acilis)

    assert len(first["gorevler"]) == 1, "kaçırılan üç çalışma toplu verilmez"
    assert first["gorevler"][0]["son_gecikmeli"] is True
    assert second["gorevler"] == [], "aynı vade ikinci kez verilmez"
    assert first["gorevler"][0]["sonraki"] == datetime(2026, 10, 5, 9, 0, tzinfo=zone).timestamp()
