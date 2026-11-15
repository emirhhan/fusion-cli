"""Computer use kapalıyken masaüstü isteğinde açma önerisi (#420)."""

from __future__ import annotations

from fusion_cli.engines.agent.computer_use_hint import (
    COMPUTER_USE_OFF_NOTE,
    computer_use_off_hint,
)


def test_kapaliyken_masaustu_isteginde_acma_onerisi():
    note = computer_use_off_hint("Finder'da indirilenleri aç", enabled=False, tool_names=())
    assert note == COMPUTER_USE_OFF_NOTE
    assert "/mcp enable computer-use" in note and "Bu bilgisayar" in note


def test_acikken_ya_da_masaustu_disi_istekte_not_yok():
    assert computer_use_off_hint("Finder'da aç", enabled=True, tool_names=()) is None
    assert computer_use_off_hint("README'yi düzelt", enabled=False, tool_names=()) is None


def test_desktop_araci_varsa_not_yok():
    names = ("read_file", "desktop_screenshot")
    assert computer_use_off_hint("Finder'da aç", enabled=False, tool_names=names) is None
