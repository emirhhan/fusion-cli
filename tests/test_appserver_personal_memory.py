"""Kaydedilen anılar görünür, silinebilir ve kapatılınca prompta girmez."""

from __future__ import annotations

import pytest

from fusion_cli.appserver.personal_memory import PersonalMemory


def test_anilar_kalici_ve_kullanici_tarafindan_yonetilebilir(tmp_path):
    memory = PersonalMemory(tmp_path)
    result = memory.add("Kısa Türkçe yanıtları tercih ederim.")
    assert result["ok"] is True
    assert "Kısa Türkçe" in PersonalMemory(tmp_path).prompt_block()
    assert memory.list()["anilar"] == [
        {"id": result["id"], "metin": "Kısa Türkçe yanıtları tercih ederim."}
    ]

    assert memory.set_enabled(False)["ok"] is True
    assert memory.prompt_block() == ""
    assert memory.list()["anilar"]
    assert memory.set_enabled(True)["ok"] is True
    assert memory.delete(result["id"])["ok"] is True
    assert memory.list()["anilar"] == []


def test_gecersiz_girdi_ve_baska_id_baska_aniyi_silmez(tmp_path):
    memory = PersonalMemory(tmp_path)
    assert memory.add(" ")["ok"] is False
    saved = memory.add("Önce testleri çalıştır.")
    assert memory.delete("bilinmeyen")["ok"] is False
    assert memory.list()["anilar"][0]["id"] == saved["id"]


def test_islem_sonunda_baglanti_kapanir(tmp_path, monkeypatch):
    """Ölçüldü (30 Ekim, S2-26): `with sqlite3.connect()` bağlantıyı kapatmıyordu."""
    import sqlite3

    acilan: list[sqlite3.Connection] = []
    gercek = sqlite3.connect

    def kaydet(*args, **kwargs):
        baglanti = gercek(*args, **kwargs)
        acilan.append(baglanti)
        return baglanti

    monkeypatch.setattr(sqlite3, "connect", kaydet)
    bellek = PersonalMemory(tmp_path)
    bellek.add("kasklar L beden")
    bellek.list()

    assert acilan
    for baglanti in acilan:
        with pytest.raises(sqlite3.ProgrammingError):
            baglanti.execute("SELECT 1")


def test_prompt_blogu_toplam_karakter_tavanini_asmaz(tmp_path):
    """Ölçüldü (30 Ekim, S2-26): 100 anı × 500 karakter her tura koşulsuz ekleniyordu."""
    bellek = PersonalMemory(tmp_path)
    for numara in range(40):
        bellek.add(f"{numara:02d} " + "x" * 490)

    blok = bellek.prompt_block()

    assert len(blok) < 7_000
    assert "39 xxx" in blok  # en yeni anı kalır
