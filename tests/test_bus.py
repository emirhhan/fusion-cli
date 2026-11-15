"""Olay veriyolu — sıralama ve dayanıklılık garantileri."""

from __future__ import annotations

import asyncio

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


async def test_turdan_sonra_gelen_arka_plan_olaylari_muhasebeden_kaybolmaz():
    sink = RecordingSink()
    async with EventBus() as bus:
        bus.subscribe(sink)
        bus.publish(StatusChanged("cevap"))
    bus.publish(StatusChanged("arka plan kullanım"))
    await bus.drain()
    assert [event.message for event in sink.events] == ["cevap", "arka plan kullanım"]


async def test_kapanis_beklerken_planlanan_olay_kaybolmaz():
    class SchedulingSink(RecordingSink):
        def handle(self, event):
            super().handle(event)
            if event.message == "ilk":
                asyncio.get_running_loop().call_soon(bus.publish, StatusChanged("son"))

    sink = SchedulingSink()
    async with EventBus() as bus:
        bus.subscribe(sink)
        bus.publish(StatusChanged("ilk"))
    assert [event.message for event in sink.events] == ["ilk", "son"]
    await asyncio.wait_for(bus.drain(), timeout=1)


async def test_korelasyon_hatasi_kaydedilir_sonraki_olay_ve_kapanis_tamamlanir():
    def correlate(event):
        if event.message == "bozuk":
            raise ValueError("kimlik üretilemedi")
        return event

    first, second = RecordingSink(), RecordingSink()
    bus = EventBus(event_correlator=correlate)
    await bus.__aenter__()
    try:
        bus.subscribe(first)
        bus.subscribe(second)
        bus.publish(StatusChanged("bozuk"))
        bus.publish(StatusChanged("sonraki"))
        await asyncio.wait_for(bus.drain(), timeout=0.5)
        await asyncio.wait_for(bus.__aexit__(None, None, None), timeout=0.5)
        assert [event.message for event in first.events] == ["sonraki"]
        assert first.events == second.events
        assert len(bus.failures) == 1
        assert "event_correlator" in bus.failures[0] and "ValueError" in bus.failures[0]
    finally:
        # Kırmızı sürümün ölü tüketicisi/yarım kuyruğu testi asılı bırakmamalı.
        if bus._consumer is not None:
            bus._consumer.cancel()
            await asyncio.gather(bus._consumer, return_exceptions=True)


async def test_kapali_bus_korelasyon_hatasi_sinirli_kayitla_izole_edilir():
    def correlate(event):
        if event.message.startswith("bozuk"):
            raise ValueError(event.message)
        return event

    sink = RecordingSink()
    async with EventBus(event_correlator=correlate) as bus:
        bus.subscribe(sink)
    for index in range(205):
        bus.publish(StatusChanged(f"bozuk-{index}"))
    bus.publish(StatusChanged("sonraki"))
    await asyncio.wait_for(bus.drain(), timeout=0.5)
    assert [event.message for event in sink.events] == ["sonraki"]
    assert len(bus.failures) == 200
    assert "bozuk-204" in bus.failures[-1]
    assert all("event_correlator" in failure for failure in bus.failures)


async def test_korelasyon_iptali_normal_hata_olarak_yutulmaz():
    import pytest

    def correlate(event):
        raise asyncio.CancelledError

    sink = RecordingSink()
    async with EventBus(event_correlator=correlate) as bus:
        bus.subscribe(sink)
    with pytest.raises(asyncio.CancelledError):
        bus.publish(StatusChanged("iptal"))
    assert bus.failures == [] and sink.events == []
