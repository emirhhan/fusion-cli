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


def test_yapistirilan_metin_arama_kipini_acar_ve_tek_satira_iner():
    arama = ChoiceSearch(SATIRLAR)
    assert arama.type("feat/x\n") and arama.query == "feat/x"
    assert [c.value for c in arama.visible()] == ["b2"]
    assert not ChoiceSearch(SATIRLAR).type("\x1b[15~")  # yazdırılamayan tuş dizisi değil


def test_gizli_anahtar_sozcuk_aranir_satirda_gorunmez():
    arama = ChoiceSearch([Choice("a1", "giriş", "main", keywords="https://x/pull/1"), *SATIRLAR])
    assert arama.type("h") and arama.type("ttps://x/pull/1")
    assert [c.value for c in arama.visible()] == ["a1"]


async def test_tam_ekran_seciciye_gercek_yapistirma_aramaya_gider():
    # Terminal yapıştırmayı köşeli parantezli (bracketed) tek olay olarak yollar.
    import contextlib

    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    from fusion_cli.cli.repl.tui import FusionTui

    satirlar = [Choice("a1", "giriş", "main", keywords="https://github.com/o/r/pull/12"), *SATIRLAR]
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        tui = FusionTui(
            on_submit=lambda _t: None,
            on_interrupt=lambda: None,
            on_exit=lambda: None,
            on_cycle_mode=lambda: None,
        )
        app = asyncio.create_task(tui.application.run_async())
        await asyncio.sleep(0.2)
        secim = asyncio.ensure_future(tui.await_choice("t", satirlar, searchable=True))
        await asyncio.sleep(0.1)
        try:
            pipe.send_text("\x1b[200~https://github.com/o/r/pull/12\x1b[201~")
            await asyncio.sleep(0.3)
            assert [c.value for c in tui._choices] == ["a1"]
            assert tui._input.buffer.text == ""  # girdi kutusuna katlanmadı
            pipe.send_text("\r")
            assert await asyncio.wait_for(secim, timeout=3) == "a1"
        finally:
            with contextlib.suppress(Exception):
                tui.application.exit()
            await asyncio.sleep(0.1)
            app.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await app


def test_satir_ici_secicide_yapistirma_bagi_aramaya_gider():
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.keys import Keys

    from fusion_cli.ui.picker import PickerState, SearchView

    view, state, kb = SearchView(SATIRLAR, True), PickerState(2), KeyBindings()
    view.bind(kb, state)
    paste = kb.get_bindings_for_keys((Keys.BracketedPaste,))[-1]
    paste.handler(type("E", (), {"data": "feat/x"})())
    assert [c.value for c in view.rows()] == ["b2"]
