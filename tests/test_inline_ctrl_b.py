"""Satır içi REPL'de tur sürerken Ctrl+B (Claude Code, #12).

Gerçek bir sözde terminal (pty) üzerinde: tuş gözcüsü kanonik olmayan kipe geçer, Ctrl+B
baytını yakalar, yazılanları saklar ve tur bitince terminal kipini geri yükler.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="termios/pty yalnız POSIX")

from fusion_cli.cli.repl import inline_keys, loop  # noqa: E402
from fusion_cli.cli.repl.inline_keys import (  # noqa: E402
    BackgroundKey,
    InlineKeys,
    Typeahead,
    background_key_action,
    trigger_bytes,
)


def _pty() -> tuple[int, int]:
    master, slave = os.openpty()
    return master, slave


def _lflag(fd: int) -> int:
    import termios

    return termios.tcgetattr(fd)[3]


def test_arka_plana_al_bagi_ctrl_bayti_olur_ayrilmis_tuslar_dislanir():
    assert trigger_bytes({"c-b": "arka_plana_al"}) == frozenset({0x02})
    assert trigger_bytes({"c-g": "arka_plana_al", "c-b": "kes"}) == frozenset({0x07})
    # Ctrl+C (SIGINT), Ctrl+D (EOF) ve tuş olmayan bağlar satır içinde kullanılamaz.
    assert trigger_bytes({"c-c": "arka_plana_al", "c-d": "arka_plana_al"}) == frozenset()
    assert trigger_bytes({"escape": "arka_plana_al", "f2": "arka_plana_al"}) == frozenset()
    # Kullanıcı bağı kaldırdıysa (`"c-b": null`) gözcü kurulmaz.
    assert trigger_bytes({}) == frozenset()


def test_yazilanlar_satir_ve_yarim_satir_olarak_saklanir():
    buffer = Typeahead()
    triggered, echo = buffer.feed("ab\x7fç\nyarım\x1b[A\x02".encode(), frozenset({0x02}))
    assert triggered is True
    assert buffer.take_line() == "aç"
    assert buffer.take_line() is None
    assert buffer.take_partial() == "yarım"
    assert "\x1b" not in echo and "\x02" not in echo
    assert echo.startswith("ab\b \bç\r\n")


async def test_pty_uzerinde_ctrl_b_tetikler_kip_geri_yuklenir():
    import termios

    master, slave = _pty()
    try:
        before = termios.tcgetattr(slave)
        keys = InlineKeys(frozenset({0x02}), slave, out=io.StringIO())
        fired = asyncio.Event()
        with keys.watching(fired.set):
            assert keys.active
            assert not _lflag(slave) & termios.ICANON
            assert _lflag(slave) & termios.ISIG  # Ctrl+C turu kesmeye devam eder
            os.write(master, b"merhaba\nyar\x02")
            await asyncio.wait_for(fired.wait(), 10)
            with keys.paused():
                # Onay istemi sırasında eski kip: kanonik + yankılı.
                assert _lflag(slave) & termios.ICANON and _lflag(slave) & termios.ECHO
            assert not _lflag(slave) & termios.ICANON
        assert not keys.active
        after = termios.tcgetattr(slave)
        # Çekirdek kanonik kipe dönüşte PENDIN koyabilir (bekleyen girdiyi yeniden yaz).
        pendin = getattr(termios, "PENDIN", 0)
        assert after[3] & ~pendin == before[3] & ~pendin
        assert after[:3] == before[:3] and after[4:] == before[4:]
        assert keys.typeahead.take_line() == "merhaba"
        assert keys.typeahead.take_partial() == "yar"
    finally:
        os.close(master)
        os.close(slave)


async def test_terminal_degilse_gozcu_hicbir_sey_yapmaz(tmp_path):
    target = tmp_path / "dosya"
    target.write_text("")
    with target.open() as handle:
        keys = InlineKeys(frozenset({0x02}), handle.fileno())
        with keys.watching(lambda: None):
            assert not keys.active
    assert not InlineKeys(frozenset(), None).usable()


def _state(*, disabled: bool = False, pending: bool = False):
    launch = SimpleNamespace(disable_background_tasks=disabled)
    calls: list[str] = []

    def request_background() -> bool:
        calls.append("istek")
        return pending

    return SimpleNamespace(
        config=SimpleNamespace(agent_launch=launch),
        child_runs=SimpleNamespace(request_background=request_background),
        inline_keys=None,
    ), calls


def test_ctrl_b_kurali_tui_ile_ayni():
    state, calls = _state(disabled=True, pending=True)
    assert background_key_action(state) is BackgroundKey.NONE
    assert calls == []  # arka plan kapalıyken alt ajan da taşınmaz
    state, _ = _state(pending=True)
    assert background_key_action(state) is BackgroundKey.SUBAGENT
    state, _ = _state()
    assert background_key_action(state) is BackgroundKey.TURN


def _wire(monkeypatch, state, slave: int, dispatch):
    keys = InlineKeys(frozenset({0x02}), slave, out=io.StringIO())
    state.inline_keys = keys
    monkeypatch.setattr(loop, "_dispatch", dispatch)
    monkeypatch.setattr(loop, "apply_auto_profile", lambda *args: None)
    return keys


async def test_satir_ici_turda_bekleyen_alt_ajan_tasinir_tur_surer(monkeypatch):
    from rich.console import Console

    master, slave = _pty()
    try:
        state, calls = _state(pending=True)
        started, release = asyncio.Event(), asyncio.Event()

        async def dispatch(*args):
            started.set()
            await release.wait()

        asked = asyncio.Event()
        original = state.child_runs.request_background

        def request_background() -> bool:
            asked.set()
            return original()

        state.child_runs.request_background = request_background
        _wire(monkeypatch, state, slave, dispatch)
        console = Console(file=io.StringIO(), width=100)
        turn = asyncio.ensure_future(loop._run_turn("uzun iş", state, console, None))
        await asyncio.wait_for(started.wait(), 10)
        os.write(master, b"\x02")
        await asyncio.wait_for(asked.wait(), 10)
        assert calls == ["istek"]
        assert not turn.done()
        release.set()
        assert await asyncio.wait_for(turn, 10) is True
    finally:
        os.close(master)
        os.close(slave)


async def test_satir_ici_turda_alt_ajan_yoksa_tur_arka_plana_tasinir(monkeypatch):
    from rich.console import Console

    master, slave = _pty()
    try:
        state, _ = _state()
        started = asyncio.Event()
        moved: list[str] = []

        async def dispatch(*args):
            started.set()
            await asyncio.Event().wait()

        _wire(monkeypatch, state, slave, dispatch)
        monkeypatch.setattr(
            loop,
            "interrupted_to_background",
            lambda _state, line: moved.append(line) or "Arka plana taşındı: bg-1",
        )
        out = io.StringIO()
        turn = asyncio.ensure_future(loop._run_turn("uzun iş", state, Console(file=out), None))
        await asyncio.wait_for(started.wait(), 10)
        os.write(master, b"\x02")
        assert await asyncio.wait_for(turn, 10) is False
        assert moved == ["uzun iş"]
        assert "bg-1" in out.getvalue()
    finally:
        os.close(master)
        os.close(slave)


async def test_tur_sirasinda_yazilan_satir_siradaki_mesaj_olur():
    state, _ = _state()
    keys = InlineKeys(frozenset({0x02}), None)
    keys.typeahead.feed(b"ikinci mesaj\nyar", frozenset({0x02}))
    state.inline_keys = keys
    state.take_pending_input = lambda: ""
    prompts: list[str] = []

    class Reader:
        mode = "auto"

        async def prompt(self, default: str = "") -> str:
            prompts.append(default)
            return default + "ım"

    assert await loop._read_line(Reader(), state) == "ikinci mesaj"
    assert prompts == []
    assert await loop._read_line(Reader(), state) == "yarım"
    assert prompts == ["yar"]


def test_disable_background_tasks_ile_gercek_ayar(tmp_path):
    from tests.fakes import make_config

    config = make_config(memory_dir=tmp_path / "bellek")
    config = replace(
        config, agent_launch=replace(config.agent_launch, disable_background_tasks=True)
    )
    state = SimpleNamespace(config=config, child_runs=None, inline_keys=None)
    assert inline_keys.background_key_action(state) is BackgroundKey.NONE


async def test_add_reader_basarisizsa_terminal_kipi_geri_yuklenir(monkeypatch):
    """İnceleme bulgusu 1: tcsetattr'dan sonra add_reader düşerse kip kanonik kalmalı."""
    import termios

    master, slave = _pty()
    try:
        before = _lflag(slave)
        loop_ = asyncio.get_running_loop()

        def broken_add_reader(*args):
            raise OSError("fd reddedildi")

        monkeypatch.setattr(loop_, "add_reader", broken_add_reader)
        keys = InlineKeys(frozenset({0x02}), slave, out=io.StringIO())
        with keys.watching(lambda: None):
            assert not keys.active
            assert _lflag(slave) & termios.ICANON and _lflag(slave) & termios.ECHO
        pendin = getattr(termios, "PENDIN", 0)
        assert _lflag(slave) & ~pendin == before & ~pendin
    finally:
        os.close(master)
        os.close(slave)


async def test_ic_ice_onay_istemlerinde_terminal_kanonik_kalir():
    """İnceleme bulgusu 2: paralel alt ajanların onayları iç içe `paused` açar."""
    import termios

    master, slave = _pty()
    try:
        keys = InlineKeys(frozenset({0x02}), slave, out=io.StringIO())
        with keys.watching(lambda: None):
            first, second = keys.paused(), keys.paused()
            first.__enter__()
            second.__enter__()
            first.__exit__(None, None, None)
            # B hâlâ soruyor: kanonik + yankılı kalmalı, gözcü yeniden açılmamalı.
            assert _lflag(slave) & termios.ICANON and _lflag(slave) & termios.ECHO
            assert not keys.active
            second.__exit__(None, None, None)
            assert keys.active
            assert not _lflag(slave) & termios.ICANON
        assert not keys.active
        assert _lflag(slave) & termios.ICANON
    finally:
        os.close(master)
        os.close(slave)


async def test_tur_bitince_acik_kalan_onay_gozcuyu_yeniden_acmaz():
    import termios

    master, slave = _pty()
    try:
        keys = InlineKeys(frozenset({0x02}), slave, out=io.StringIO())
        pause = keys.paused()
        with keys.watching(lambda: None):
            pause.__enter__()
        pause.__exit__(None, None, None)
        assert not keys.active
        assert _lflag(slave) & termios.ICANON and _lflag(slave) & termios.ECHO
    finally:
        os.close(master)
        os.close(slave)
