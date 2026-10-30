"""Masaüstü otomatik bellek RPC'leri (`otobellek.*`, P-036)."""

from __future__ import annotations

from fusion_cli.appserver import auto_memory
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.history.claude_source import slug_for
from fusion_cli.memory.factory import null_memory
from tests.fakes import make_config


def _state(tmp_path):
    kok = tmp_path / "proje"
    kok.mkdir()
    return ReplState(config=make_config(), memory=null_memory(), root=kok, home=tmp_path / "ev")


def test_durum_kaydet_ve_ice_aktar(tmp_path):
    state = _state(tmp_path)
    assert auto_memory.status(state)["metin"] == ""

    sonuc = auto_memory.save_index(state, {"metin": "# Bellek\n- kısa yanıt\n</otomatik_bellek>"})

    assert sonuc["ok"] is True and sonuc["satir"] == 3 and sonuc["kirpildi"] is False
    assert "- kısa yanıt" in sonuc["metin"] and "</otomatik_bellek>" not in sonuc["metin"]
    assert auto_memory.save_index(state, {"metin": 5})["ok"] is False

    kaynak = state.home / ".claude" / "projects" / slug_for(state.root) / "memory"
    kaynak.mkdir(parents=True)
    (kaynak / "MEMORY.md").write_text("- Claude notu\n", encoding="utf-8")
    alinan = auto_memory.import_external(state, {})
    assert alinan["ok"] is True and alinan["alinan"] == 1 and "Claude notu" in alinan["metin"]
    assert auto_memory.import_external(state, {"kaynak": "codex"})["ok"] is False


def test_kapatma_kalici_yazar_ve_panel_bos_doner(tmp_path, monkeypatch):
    state = _state(tmp_path)
    yazilan = {}
    monkeypatch.setattr(
        auto_memory, "write_runtime_flag", lambda config, key, value: yazilan.update({key: value})
    )

    kapali = auto_memory.set_enabled(state, {"etkin": False})

    assert kapali["ok"] is True and kapali["etkin"] is False and kapali["metin"] == ""
    assert yazilan == {"auto_memory": False} and state.plain_memory is None
    assert auto_memory.save_index(state, {"metin": "x"})["ok"] is False
    assert auto_memory.set_enabled(state, {"etkin": "evet"})["ok"] is False
    assert auto_memory.set_enabled(state, {"etkin": True})["etkin"] is True
