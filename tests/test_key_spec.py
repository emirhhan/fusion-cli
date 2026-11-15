"""Tuş dizgisi sözdizimi masaüstü ve Chrome araçlarında ortaktır (P-032)."""

from __future__ import annotations

import pytest

from fusion_cli.tools import chrome
from fusion_cli.tools.key_spec import KeyChord, key_base, parse_key_sequence


def test_tek_tus_ve_degistiriciler_cozulur() -> None:
    assert parse_key_sequence("cmd+shift+4") == (KeyChord(key="4", command=True, shift=True),)


def test_bosluk_ayrilmis_dizi_sirayla_cozulur() -> None:
    chords = parse_key_sequence("cmd+l  Return esc")

    assert [chord.key for chord in chords] == ["l", "enter", "escape"]
    assert chords[0].command and not chords[1].command


@pytest.mark.parametrize(
    ("takma", "alan"),
    [
        ("ctrl", "control"),
        ("control", "control"),
        ("alt", "option"),
        ("opt", "option"),
        ("meta", "command"),
        ("super", "command"),
        ("command", "command"),
    ],
)
def test_degistirici_takma_adlari(takma: str, alan: str) -> None:
    chord = parse_key_sequence(f"{takma}+a")[0]
    assert getattr(chord, alan) is True


def test_tek_basina_degistirici_tusa_donusmez() -> None:
    with pytest.raises(ValueError, match="değiştirici"):
        parse_key_sequence("cmd+")
    with pytest.raises(ValueError, match="değiştirici"):
        parse_key_sequence("shift")


def test_bos_ve_asiri_uzun_dizi_reddedilir() -> None:
    with pytest.raises(ValueError):
        parse_key_sequence("   ")
    with pytest.raises(ValueError, match="en fazla"):
        parse_key_sequence(" ".join(["a"] * 40))


def test_arti_tusu_tek_basina_korunur() -> None:
    assert parse_key_sequence("+")[0].key == "+"
    assert parse_key_sequence("shift++")[0] == KeyChord(key="+", shift=True)


def test_chrome_taban_tus_ayni_ayristiriciyi_kullanir() -> None:
    """Ölçüldü (31 Ekim): chrome.py kendi `_key_base`'ini taşıyordu; sözdizimi ayrışabiliyordu."""
    assert key_base("Ctrl+Shift+Enter") == "enter"
    assert key_base("+") == "+"
    assert chrome._key_base("Meta+Enter") == key_base("Meta+Enter")
