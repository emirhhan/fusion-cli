"""Seçicide yazarak arama (#202)."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.cli.repl.choice_search import ChoiceSearch
from fusion_cli.ui.picker import Choice

SATIRLAR = [Choice("a1", "giriş hatası", "main"), Choice("b2", "README", "feat/x")]


def test_yazdirilabilir_karakter_arama_baslatir_jk_baslatmaz():
    arama = ChoiceSearch(SATIRLAR)
    assert not arama.type("j") and not arama.active
    assert arama.type("e") and [c.value for c in arama.visible()] == ["b2"]
    assert arama.type("k") and arama.visible() == []  # arama kipinde k sorguya yazılır
    assert arama.backspace() and [c.value for c in arama.visible()] == ["b2"]
    assert arama.exit() and not arama.exit()
    assert len(arama.visible()) == 2


def test_egik_cizgi_bos_sorguyla_acar_aciklamada_da_arar():
    arama = ChoiceSearch(SATIRLAR)
    assert arama.type("/") and arama.query == ""
    for harf in "feat":
        arama.type(harf)
    assert [c.value for c in arama.visible()] == ["b2"]


@pytest.mark.asyncio
async def test_tui_modalinda_arama_ve_esc_once_aramadan_cikar():
    from .test_tui import _press, _tui

    tui, _ = _tui()
    task = asyncio.ensure_future(tui.await_choice("t", list(SATIRLAR), searchable=True))
    await asyncio.sleep(0)
    tui._choice_type("E")
    assert [c.value for c in tui._choices] == ["b2"]
    _press(tui, "escape")  # arama kipinden çıkar, seçici açık kalır
    assert not task.done() and len(tui._choices) == 2
    tui._choice_type("g")
    tui._pick_current()
    assert await task == "a1"
