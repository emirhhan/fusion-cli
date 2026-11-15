"""Satır içi REPL'de tur sürerken Ctrl+B (Claude Code, #320)."""

from __future__ import annotations

import asyncio
import os
import sys
import termios

import pytest

from fusion_cli.cli.repl import turn_keys


def test_ctrl_b_eylemi_cagirir_metin_taslaga_gider():
    calls: list[int] = []
    keys = turn_keys.TurnKeys(lambda: calls.append(1), fd=-1)

    keys.feed(b"merhabx\x7fa\x02 d\xc3\xbcnya\r")

    assert calls == [1]
    assert keys.typed == "merhaba dünya"


def test_tty_degilse_izleme_sessizce_gecer(tmp_path):
    path = tmp_path / "dosya"
    path.write_text("x")
    with path.open() as stream:
        keys = turn_keys.TurnKeys(lambda: None, fd=stream.fileno())
        with keys.watching(), turn_keys.paused():
            pass


@pytest.mark.skipif(sys.platform == "win32", reason="pty yok")
def test_pty_uzerinde_ctrl_b_okunur_onayda_kanonik_kipe_doner():
    master, slave = os.openpty()
    calls: list[int] = []
    before = termios.tcgetattr(slave)

    async def run() -> None:
        keys = turn_keys.TurnKeys(lambda: calls.append(1), fd=slave)
        with keys.watching():
            assert not termios.tcgetattr(slave)[3] & termios.ICANON
            os.write(master, b"\x02")
            for _ in range(50):
                await asyncio.sleep(0.01)
                if calls:
                    break
            with turn_keys.paused():
                assert termios.tcgetattr(slave)[3] & termios.ICANON
            assert not termios.tcgetattr(slave)[3] & termios.ICANON

    try:
        asyncio.run(run())
        assert calls == [1]
        mask = termios.ICANON | termios.ECHO
        assert termios.tcgetattr(slave)[3] & mask == before[3] & mask
    finally:
        os.close(master)
        os.close(slave)


def test_ctrl_b_kabuk_komutunu_devreder_yoksa_tur_tasinir(tmp_path, monkeypatch):
    """Satır içi Ctrl+B (#12, #320): süren kabuk komutu kesilmeden devredilir; yoksa tur."""
    from fusion_cli.cli.repl.inline_keys import BackgroundKey, background_key_action
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.config.loader import load_config
    from fusion_cli.core import foreground_handoff
    from fusion_cli.memory.factory import null_memory

    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    state = ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    assert background_key_action(state) is BackgroundKey.TURN

    asked: list[bool] = []
    monkeypatch.setattr(
        foreground_handoff, "request_background", lambda: asked.append(True) or True
    )
    assert background_key_action(state) is BackgroundKey.SUBAGENT
    assert asked == [True]
