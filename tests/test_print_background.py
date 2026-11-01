"""`-p` arka plan işini bekleme: tavan kesintisiz boşta süredir, `0` tavansızdır (#316)."""

from __future__ import annotations

import asyncio

from fusion_cli.cli.print_background import ActivityClock, wait_background


class _Runs:
    def __init__(self, seconds: float, clock: ActivityClock | None = None) -> None:
        self.seconds = seconds
        self.clock = clock
        self.closed = False
        self.finished = False

    @property
    def active_count(self) -> int:
        return 1

    async def drain(self) -> None:
        steps = max(1, int(self.seconds / 0.01))
        for _ in range(steps):
            await asyncio.sleep(0.01)
            if self.clock is not None:
                self.clock.handle(object())  # alt ajan olayı: etkinlik
        self.finished = True

    async def close(self) -> None:
        self.closed = True


def test_tavan_sifirsa_tavansiz_bekler(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "0")
    runs = _Runs(0.08)
    asyncio.run(wait_background(runs, lambda _t: None, delay_s=10))
    assert runs.finished and not runs.closed


def test_etkinlik_surdukce_tavan_dolmaz(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "40")
    clock = ActivityClock()
    runs = _Runs(0.2, clock)
    asyncio.run(wait_background(runs, lambda _t: None, delay_s=10, activity=clock))
    assert runs.finished and not runs.closed


def test_boşta_tavan_dolunca_is_durdurulur(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS", "30")
    runs = _Runs(5)
    asyncio.run(wait_background(runs, lambda _t: None, delay_s=10, activity=ActivityClock()))
    assert runs.closed and not runs.finished
