"""Kaydedilen anılar görünür, silinebilir ve kapatılınca prompta girmez."""

from __future__ import annotations

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
