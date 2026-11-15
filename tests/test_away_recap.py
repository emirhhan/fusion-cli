"""Uzaklaşınca oturum özeti (#230, Claude Code Session recap)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.cli.repl.away_recap import AWAY_AFTER_S, AwayRecap
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.types import Message
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


class _Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def _kur(tmp_path: Path, turns: int = 3, busy: bool = False):
    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    for index in range(turns):
        state.history += [Message("user", f"istek {index}"), Message("assistant", "tamam")]
    clock, shown = _Clock(), []

    async def produce() -> str:
        return "Oyun motoru kuruldu, testler yeşil."

    away = AwayRecap(state, lambda: busy, produce, shown.append, clock)
    return state, clock, shown, away


async def test_bosta_kalinca_bir_kez_ozet_basar(tmp_path: Path) -> None:
    _state, clock, shown, away = _kur(tmp_path)
    clock.now = AWAY_AFTER_S - 1
    assert not await away.tick()
    clock.now = AWAY_AFTER_S
    assert await away.tick() and shown == ["Oyun motoru kuruldu, testler yeşil."]
    clock.now += 1000
    assert not await away.tick()
    away.touch()
    clock.now += AWAY_AFTER_S
    assert await away.tick() and len(shown) == 2


async def test_az_tur_mesgul_ve_kapali_ayar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _s, clock, shown, away = _kur(tmp_path, turns=2)
    clock.now = AWAY_AFTER_S * 2
    assert not await away.tick()
    _s, clock, shown, away = _kur(tmp_path, busy=True)
    clock.now = AWAY_AFTER_S * 2
    assert not await away.tick()
    state, clock, shown, away = _kur(tmp_path)
    clock.now = AWAY_AFTER_S * 2
    monkeypatch.setenv("CLAUDE_CODE_ENABLE_AWAY_SUMMARY", "0")
    assert not await away.tick()
    monkeypatch.delenv("CLAUDE_CODE_ENABLE_AWAY_SUMMARY")
    state.config = replace(state.config, runtime=replace(state.config.runtime, session_recap=False))
    assert not await away.tick() and shown == []
