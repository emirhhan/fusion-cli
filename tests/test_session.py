"""Oturum akışı — uçtan uca, ağ olmadan."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli import session
from fusion_cli.config.models import Config, RuntimeConfig
from fusion_cli.core.events import (
    ErrorOccurred,
    ModelCallFinished,
    ModelCallStarted,
    StatusChanged,
    TokenReceived,
    TurnFinished,
)
from fusion_cli.core.types import ModelSpec

from .fakes import FakeProvider, RecordingSink


@pytest.fixture
def config():
    return Config(
        agent=ModelSpec(name="agent", model="sahte/model"),
        runtime=RuntimeConfig(request_timeout_s=5.0, max_retries=0, temperature=0.0, max_tokens=32),
        source=Path("test"),
    )


def _sahte_saglayici(monkeypatch, provider):
    from fusion_cli.providers.eventing import EventingProvider

    def _build(spec, *, publisher, channel=None, clock=None):
        from fusion_cli.core.events import Channel

        return EventingProvider(
            provider, publisher=publisher, role=spec.name, channel=channel or Channel.MAIN
        )

    monkeypatch.setattr(session, "build_provider", _build)


async def test_basarili_gorev_metni_akitir_ve_sonuc_dondurur(monkeypatch, config):
    _sahte_saglayici(monkeypatch, FakeProvider("sahte", chunks=("mer", "haba")))
    sink = RecordingSink()

    result = await session.run_task("selam", config, sinks=(sink,))

    assert result.ok
    assert result.text == "merhaba"
    metin = "".join(e.text for e in sink.events if isinstance(e, TokenReceived))
    assert metin == "merhaba"


async def test_olay_sirasi_beklenen_akisi_izler(monkeypatch, config):
    _sahte_saglayici(monkeypatch, FakeProvider("sahte", chunks=("a",)))
    sink = RecordingSink()

    await session.run_task("selam", config, sinks=(sink,))

    tipler = [type(event) for event in sink.events]
    assert tipler[0] is StatusChanged
    assert tipler[1] is ModelCallStarted
    assert ModelCallFinished in tipler
    assert tipler[-1] is TurnFinished


async def test_basarisiz_cagri_hata_olayi_yayinlar(monkeypatch, config):
    _sahte_saglayici(monkeypatch, FakeProvider("sahte", ok=False, error="503 sunucu"))
    sink = RecordingSink()

    result = await session.run_task("selam", config, sinks=(sink,))

    assert not result.ok
    hatalar = [event for event in sink.events if isinstance(event, ErrorOccurred)]
    assert hatalar and hatalar[0].fatal


async def test_hiz_siniri_ozel_mesaj_uretir(monkeypatch, config):
    _sahte_saglayici(monkeypatch, FakeProvider("sahte", ok=False, error="429 rate limit"))
    sink = RecordingSink()

    await session.run_task("selam", config, sinks=(sink,))

    hata = next(event for event in sink.events if isinstance(event, ErrorOccurred))
    assert "kota" in hata.message.lower()


def test_istek_yapilandirmadaki_calisma_zamani_ayarlarini_kullanir(config):
    request = session.build_request("selam", config)

    assert request.max_tokens == 32
    assert request.timeout_s == 5.0
    assert request.messages[0].content == "selam"
