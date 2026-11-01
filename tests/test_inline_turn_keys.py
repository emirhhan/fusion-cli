"""Satır içi REPL: tur sürerken yazılan mesaj aynı tura verilir, Ctrl+B devreder (#190, #218)."""

from __future__ import annotations

import pytest

from fusion_cli.cli.repl.inline_turn_keys import InlineTurnKeys
from fusion_cli.core.steering import steering_text


def _keys():
    drafts: list[str] = []
    queued: list[str] = []
    backgrounds: list[bool] = []
    keys = InlineTurnKeys(
        on_draft=drafts.append,
        on_queued=queued.append,
        on_background=lambda: backgrounds.append(True),
    )
    return keys, drafts, queued, backgrounds


def test_duz_mesaj_ayni_turun_kuyruguna_girer_komut_tur_sonunu_bekler():
    keys, _drafts, queued, _ = _keys()
    steering = keys.begin()
    keys.feed("şunu da yap\r")
    keys.feed("/compact\r! ls\r")
    assert queued == ["şunu da yap", "/compact", "! ls"]
    assert [steering_text(m) for m in steering.drain()] == ["şunu da yap"]
    lines, draft = keys.end()
    assert lines == ["/compact", "! ls"] and draft == ""


def test_tuketilmeyen_mesaj_tur_sonunda_siradaki_satir_olur_taslak_korunur():
    keys, drafts, _, _ = _keys()
    keys.begin()
    keys.feed("bunu ekle\ryarım")
    lines, draft = keys.end()
    assert lines == ["bunu ekle"] and draft == "yarım"
    assert drafts[-1] == "yarım"


def test_duzenleme_tuslari_ve_kacis_dizileri():
    keys, drafts, _, backgrounds = _keys()
    keys.begin()
    keys.feed("abc\x7f")
    assert drafts[-1] == "ab"
    keys.feed("\x1b[A")  # Up oku yok sayılır
    assert drafts[-1] == "ab"
    keys.feed("\x15x")
    assert drafts[-1] == "x"
    keys.feed("\x02")
    assert backgrounds == [True]


@pytest.mark.asyncio
async def test_okuyucu_tty_degilken_sessizce_gecer():
    keys, *_ = _keys()
    with keys.reading(), keys.paused():
        pass


@pytest.mark.asyncio
async def test_kuyruktaki_satir_istem_acilmadan_okunur(tmp_path):
    from fusion_cli.cli.repl.loop import _queue_leftovers, _read_line
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    keys, *_ = _keys()
    keys.begin()
    keys.feed("ikinci iş\r/status\rtaslak")
    _queue_leftovers(state, keys)
    assert state.pending_input == "taslak"

    class _Okuyucu:
        async def prompt(self, default=""):
            raise AssertionError("istem açılmamalı")

    assert await _read_line(_Okuyucu(), state) == "ikinci iş"
    assert await _read_line(_Okuyucu(), state) == "/status"
    assert state.queued_lines == []


def test_satir_ici_ctrl_b_suren_kabugu_devreder(tmp_path):
    from io import StringIO

    from rich.console import Console

    from fusion_cli.cli.repl.loop import _inline_background
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    out = StringIO()
    console = Console(file=out, width=120)
    _inline_background(state, console)
    assert "/bg" in out.getvalue()
    event = state.shell_handoff.begin()
    _inline_background(state, console)
    assert event.is_set() and "arka plana alındı" in out.getvalue()


def test_anlik_komut_kuyruga_girmeden_calisir():
    calisan: list[str] = []
    keys = InlineTurnKeys(
        on_draft=lambda _t: None,
        on_queued=lambda _t: None,
        on_background=lambda: None,
        on_immediate=lambda line: line.startswith("/status") and not calisan.append(line),
    )
    keys.begin()
    keys.feed("/status\r/compact\r")
    assert calisan == ["/status"]
    assert keys.end() == (["/compact"], "")
