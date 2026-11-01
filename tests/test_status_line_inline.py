"""Satır içi REPL durum satırı tetikleri (#192): istem açıkken izin/vim kipi değişimi ve
`refreshInterval`; istem kapalıyken (tur sürerken) çalışmaz."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.status_line_inline import InlineStatusWatcher
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


class _Reader:
    def __init__(self) -> None:
        self.mode = ApprovalMode.AUTO
        self.vim_mode = False
        self.custom_status = ""
        self.waiting = True
        self.vi = ""

    def vi_state(self) -> str:
        return self.vi

    def invalidate(self) -> None:
        pass

    async def print_above(self, write) -> None:
        write()


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _watcher(tmp_path: Path, interval: int | None):
    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    reader, clock, runs = _Reader(), _Clock(), []

    async def show() -> None:
        runs.append(state.approval)

    watcher = InlineStatusWatcher(state, reader, show, lambda: interval, clock)
    return state, reader, clock, runs, watcher


async def test_izin_kipi_degisince_calisir(tmp_path: Path) -> None:
    state, reader, _clock, runs, watcher = _watcher(tmp_path, None)
    assert not await watcher.tick()
    reader.mode = ApprovalMode.PLAN
    assert await watcher.tick() and runs == [ApprovalMode.PLAN]
    assert state.approval is ApprovalMode.PLAN
    assert not await watcher.tick()


async def test_vim_kipi_degisince_calisir_ve_durum_aktarilir(tmp_path: Path) -> None:
    state, reader, _clock, runs, watcher = _watcher(tmp_path, None)
    reader.vim_mode, reader.vi = True, "INSERT"
    assert await watcher.tick()
    reader.vi = "NORMAL"
    assert await watcher.tick() and state.vim_state == "NORMAL" and len(runs) == 2


async def test_refresh_interval_ve_istem_kapaliyken_beklemesi(tmp_path: Path) -> None:
    _state, reader, clock, runs, watcher = _watcher(tmp_path, 5)
    clock.now += 4
    assert not await watcher.tick()
    clock.now += 1
    assert await watcher.tick() and len(runs) == 1
    clock.now += 10
    reader.waiting = False
    assert not await watcher.tick()
    watcher.mark_ran()
    reader.waiting = True
    assert not await watcher.tick()
