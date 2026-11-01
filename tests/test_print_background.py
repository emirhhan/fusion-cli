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


def test_butce_dolunca_arka_plan_isi_beklenmez(monkeypatch):
    from types import SimpleNamespace

    from fusion_cli.cli.print_background import budget_check, run_then_wait

    async def _turn():
        return SimpleNamespace(stop_reason="cost_limit")

    runs = _Runs(5)
    asyncio.run(run_then_wait(_turn(), runs, lambda _t: None, ActivityClock()))
    assert runs.closed and not runs.finished

    spent = SimpleNamespace(total=SimpleNamespace(cost_usd=0.0))
    check = budget_check(spent, 1.0)
    assert check is not None and not check()
    later = _Runs(5)

    async def _ok():
        return SimpleNamespace(stop_reason=None)

    async def _spend():
        await asyncio.sleep(0.02)
        spent.total = SimpleNamespace(cost_usd=1.5)

    async def _both():
        spender = asyncio.ensure_future(_spend())
        await run_then_wait(_ok(), later, lambda _t: None, ActivityClock(), check)
        await spender

    asyncio.run(_both())
    assert later.closed and not later.finished
    assert budget_check(spent, None) is None
