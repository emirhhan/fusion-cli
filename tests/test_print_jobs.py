"""`fusion agent` arka plan işini bekler ve bildirimle sürer (Claude `-p`, #335)."""

from __future__ import annotations

from dataclasses import dataclass

from fusion_cli.cli.print_jobs import run_with_background
from fusion_cli.core.background_events import BackgroundEvents
from fusion_cli.core.types import Message
from fusion_cli.tools import job_lifetime
from fusion_cli.ui import messages


@dataclass
class _Outcome:
    final_text: str
    messages: tuple[Message, ...] = ()


async def test_bildirim_varsa_ek_tur_acilir_ve_gecmis_tasinir(monkeypatch):
    events = BackgroundEvents()
    calls: list[tuple[str, int]] = []

    async def turn(task, history):
        calls.append((task, len(history)))
        events.drain()  # gerçek motor olayları model isteğine boşaltır
        if len(calls) == 1:
            events.push("Arka plan işi abc bitti (çıkış kodu 0)")
            return _Outcome("başlattım", (Message("user", task), Message("assistant", "ok")))
        return _Outcome("sonuç: yeşil")

    monkeypatch.setattr(job_lifetime, "running_owned", lambda: ())
    monkeypatch.setattr(job_lifetime, "wait_owned", lambda *_a, **_k: True)

    outcome = await run_with_background(turn, "testleri arka planda koş", events, enabled=True)

    assert outcome.final_text == "sonuç: yeşil"
    assert calls == [("testleri arka planda koş", 0), (messages.BACKGROUND_WAKE, 2)]


async def test_kapaliysa_ya_da_is_yoksa_beklenmez(monkeypatch):
    events = BackgroundEvents()

    async def turn(task, history):
        events.push("iş bitti")
        return _Outcome("tek tur")

    monkeypatch.setattr(job_lifetime, "running_owned", lambda: ())
    assert (await run_with_background(turn, "x", events, enabled=False)).final_text == "tek tur"
    monkeypatch.setattr(job_lifetime, "wait_owned", lambda *_a, **_k: True)
    seen = BackgroundEvents()
    count = {"n": 0}

    async def once(task, history):
        count["n"] += 1
        if count["n"] == 1:
            seen.push("iş bitti")
        return _Outcome(f"tur {count['n']}")

    assert (await run_with_background(once, "x", seen, enabled=True)).final_text == "tur 2"
    assert count["n"] == 2

    quiet = BackgroundEvents()

    async def silent(task, history):
        return _Outcome("tamam")

    assert (await run_with_background(silent, "x", quiet, enabled=True)).final_text == "tamam"


def test_ctrl_c_bekleyen_isi_birakir_surec_hemen_cikar(monkeypatch):
    """İnceleme bulgusu 3: bekleme iptal edilebilir olmalı; `asyncio.run` kapanışta süren
    işin bitmesini (süre sınırına kadar) bekleyen bir iş parçacığına takılmamalı."""
    import asyncio
    import contextlib
    import time

    release = time.monotonic() + 3.0
    monkeypatch.setattr(
        job_lifetime, "running_owned", lambda: ("uzun",) if time.monotonic() < release else ()
    )

    async def turn(task, history):
        return _Outcome("başlattım")

    async def main() -> None:
        waiting = asyncio.create_task(
            run_with_background(turn, "x", BackgroundEvents(), enabled=True)
        )
        await asyncio.sleep(0.3)
        waiting.cancel()  # Ctrl+C: asyncio.run ana görevi iptal eder
        with contextlib.suppress(asyncio.CancelledError):
            await waiting

    started = time.monotonic()
    asyncio.run(main())
    assert time.monotonic() - started < 1.5
