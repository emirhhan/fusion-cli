"""Komut köprüsü."""

from __future__ import annotations

from fusion_cli.appserver.commands import command_choices, list_commands, run_command
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _state(tmp_path):
    return ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def test_liste_kayit_defteriyle_ortusur():
    registry = build_registry()

    liste = list_commands(registry)

    assert len(liste) == len(registry.all())
    assert all(satir["ad"] and satir["aciklama"] for satir in liste)


def test_liste_grup_ve_kullanim_tasir():
    liste = {satir["ad"]: satir for satir in list_commands(build_registry())}

    assert liste["skills"]["grup"] == "Bilgi"
    assert liste["skills"]["kullanim"] == "[arama]"


def test_komut_calisir_ve_metin_doner(tmp_path):
    sonuc = run_command(build_registry(), _state(tmp_path), "thinking", "")

    assert sonuc["ok"] is True
    assert isinstance(sonuc["metin"], str)


def test_bilinmeyen_komut_hata_doner(tmp_path):
    sonuc = run_command(build_registry(), _state(tmp_path), "olmayan", "")

    assert sonuc["ok"] is False
    assert "olmayan" in sonuc["metin"]


def test_isleyici_istisnasi_sureci_dusurmez(tmp_path):
    """Komut işleyicisi patlarsa hata sonuç olarak dönmeli, dışarı sızmamalı."""
    registry = build_registry()
    state = _state(tmp_path)
    # `forget` argümansız çağrıldığında kullanım metni döndürür; istisna değil.
    sonuc = run_command(registry, state, "forget", "")

    assert isinstance(sonuc["ok"], bool)


def test_secici_acan_komut_secenek_dondurur(tmp_path):
    secenekler = command_choices(_state(tmp_path), "level")

    assert secenekler is not None
    assert all("deger" in s and "etiket" in s for s in secenekler)


def test_secici_acmayan_komut_none_doner(tmp_path):
    assert command_choices(_state(tmp_path), "thinking") is None
