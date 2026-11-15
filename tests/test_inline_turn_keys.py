"""Satır içi REPL: tur sürerken yazılan mesaj aynı tura verilir (#190, #209).

Tek uygulama `inline_keys.InlineKeys` (Ctrl+B, #12): agent turu `begin_turn`/`end_turn` ile
yönlendirme kuyruğunu ve taslak/anlık komut kancalarını bağlar.
"""

from __future__ import annotations

import io

import pytest

from fusion_cli.cli.repl.inline_keys import InlineKeys
from fusion_cli.core.steering import steering_text


def _keys(**hooks):
    keys = InlineKeys(frozenset({0x02}), None, out=io.StringIO())
    drafts: list[str] = []
    queued: list[str] = []
    steering = keys.begin_turn(
        on_draft=drafts.append, on_queued=queued.append, on_immediate=hooks.get("on_immediate")
    )
    return keys, steering, drafts, queued


def test_duz_mesaj_ayni_turun_kuyruguna_girer_komut_tur_sonunu_bekler():
    keys, steering, _drafts, queued = _keys()
    keys.feed("şunu da yap\r".encode())
    keys.feed(b"/compact\r! ls\r")
    assert queued == ["şunu da yap", "/compact", "! ls"]
    assert [steering_text(m) for m in steering.drain()] == ["şunu da yap"]
    keys.end_turn()
    assert keys.typeahead.take_line() == "/compact"
    assert keys.typeahead.take_line() == "! ls"
    assert keys.typeahead.take_partial() == ""


def test_tuketilmeyen_mesaj_tur_sonunda_siradaki_satir_olur_taslak_korunur():
    keys, _steering, drafts, _ = _keys()
    keys.feed("bunu ekle\ryarım".encode())
    keys.end_turn()
    assert keys.typeahead.take_line() == "bunu ekle"
    assert keys.typeahead.take_partial() == "yarım"
    assert drafts[-1] == "yarım"


def test_duzenleme_tuslari_ve_kacis_dizileri():
    keys, _steering, drafts, _ = _keys()
    keys.feed(b"abc\x7f")
    assert drafts[-1] == "ab"
    keys.feed(b"\x1b[A")  # Up oku yok sayılır
    assert drafts[-1] == "ab"
    keys.feed(b"\x15x")
    assert drafts[-1] == "x"
    assert keys.feed(b"\x02") is True  # Ctrl+B tetik tuşu


def test_tur_disinda_taslak_ham_yansitilir_mesaj_siradaki_satirdir():
    out = io.StringIO()
    keys = InlineKeys(frozenset({0x02}), None, out=out)
    keys.feed(b"sonra\r")
    assert keys.typeahead.take_line() == "sonra" and "sonra" in out.getvalue()


@pytest.mark.asyncio
async def test_kuyruktaki_satir_istem_acilmadan_okunur(tmp_path):
    from fusion_cli.cli.repl.loop import _read_line
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
    state.inline_keys = keys
    keys.feed("ikinci iş\r/status\rtaslak".encode())
    keys.end_turn()

    class _Okuyucu:
        def __init__(self) -> None:
            self.defaults: list[str] = []
            self.mode = state.approval

        async def prompt(self, default=""):
            self.defaults.append(default)
            return ""

    okuyucu = _Okuyucu()
    assert await _read_line(okuyucu, state) == "ikinci iş"
    assert await _read_line(okuyucu, state) == "/status"
    assert okuyucu.defaults == []
    await _read_line(okuyucu, state)
    assert okuyucu.defaults == ["taslak"]  # yarım taslak istemi doldurur


def test_satir_ici_ctrl_b_suren_kabugu_devreder(tmp_path):
    from fusion_cli.cli.repl.inline_keys import BackgroundKey, background_key_action
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.core import foreground_handoff
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    assert background_key_action(state) is BackgroundKey.TURN
    with foreground_handoff.handoff_slot() as event:
        assert background_key_action(state) is BackgroundKey.SUBAGENT
        assert event.is_set()


def test_anlik_komut_kuyruga_girmeden_calisir():
    calisan: list[str] = []
    keys, _steering, _drafts, _queued = _keys(
        on_immediate=lambda line: line.startswith("/status") and not calisan.append(line)
    )
    keys.feed(b"/status\r/compact\r")
    assert calisan == ["/status"]
    keys.end_turn()
    assert keys.typeahead.take_line() == "/compact"
    assert keys.typeahead.take_line() is None
