"""Olay veriyolu — sıralama ve dayanıklılık garantileri."""

from __future__ import annotations

from fusion_cli.core.events import Channel, StatusChanged, TokenReceived, TurnFinished
from fusion_cli.observability.bus import EventBus

from .fakes import ExplodingSink, RecordingSink


async def test_olaylar_yayinlanma_sirasiyla_dagitilir():
    sink = RecordingSink()
    async with EventBus() as bus:
        bus.subscribe(sink)
        for index in range(50):
            bus.publish(StatusChanged(f"adim-{index}"))
        await bus.drain()

    assert [event.message for event in sink.events] == [f"adim-{i}" for i in range(50)]


async def test_iki_kanalin_metni_birbirine_karismaz():
    sink = RecordingSink()
    async with EventBus() as bus:
        bus.subscribe(sink)
        bus.publish(TokenReceived(Channel.MAIN, "ana-1"))
        bus.publish(TokenReceived(Channel.SUBAGENT, "alt-1"))
        bus.publish(TokenReceived(Channel.MAIN, "ana-2"))
        await bus.drain()

    assert [(e.channel, e.text) for e in sink.events] == [
        (Channel.MAIN, "ana-1"),
        (Channel.SUBAGENT, "alt-1"),
        (Channel.MAIN, "ana-2"),
    ]


async def test_kapanista_kuyruk_bosaltilir_son_olay_kaybolmaz():
    sink = RecordingSink()
    async with EventBus() as bus:
        bus.subscribe(sink)
        bus.publish(StatusChanged("ilk"))
        bus.publish(TurnFinished())

    assert len(sink.events) == 2
    assert isinstance(sink.events[-1], TurnFinished)


async def test_bir_dinleyicinin_hatasi_digerlerini_etkilemez():
    saglam = RecordingSink()
    async with EventBus() as bus:
        bus.subscribe(ExplodingSink())
        bus.subscribe(saglam)
        bus.publish(StatusChanged("devam"))
        await bus.drain()

        assert len(saglam.events) == 1
        assert bus.failures and "ExplodingSink" in bus.failures[0]


async def test_birden_cok_dinleyici_ekleme_sirasiyla_calisir():
    ilk, ikinci = RecordingSink(), RecordingSink()
    async with EventBus() as bus:
        bus.subscribe(ilk)
        bus.subscribe(ikinci)
        bus.publish(StatusChanged("olay"))
        await bus.drain()

    assert len(ilk.events) == len(ikinci.events) == 1
