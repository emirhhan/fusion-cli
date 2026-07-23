"""Hedged sağlayıcı — yarıştırma, iptal ve toplu başarısızlık davranışı."""

from __future__ import annotations

import pytest

from fusion_cli.core.errors import ProviderError
from fusion_cli.core.types import StreamDone, TextChunk
from fusion_cli.providers.hedged import HedgedProvider

from .fakes import FakeProvider, request


def test_saglayici_verilmezse_hata():
    with pytest.raises(ProviderError):
        HedgedProvider([], role="agent")


async def test_complete_ilk_basarili_yaniti_dondurur():
    hizli = FakeProvider("hizli", chunks=("h",), delay=0.0)
    yavas = FakeProvider("yavas", chunks=("y",), delay=0.5)
    hedged = HedgedProvider([yavas, hizli], role="agent")

    result = await hedged.complete(request())

    assert result.ok
    assert result.model == "hizli"


async def test_complete_kazanan_disindakileri_iptal_eder():
    hizli = FakeProvider("hizli", delay=0.0)
    yavas = FakeProvider("yavas", delay=5.0)
    hedged = HedgedProvider([yavas, hizli], role="agent")

    await hedged.complete(request())

    assert yavas.cancelled


async def test_complete_basarisiz_saglayiciyi_atlar():
    bozuk = FakeProvider("bozuk", ok=False, error="429 rate limit", delay=0.0)
    saglam = FakeProvider("saglam", chunks=("ok",), delay=0.05)
    hedged = HedgedProvider([bozuk, saglam], role="agent")

    result = await hedged.complete(request())

    assert result.ok
    assert result.model == "saglam"


async def test_complete_hepsi_basarisizsa_hata_firlatmaz():
    hedged = HedgedProvider(
        [
            FakeProvider("a", ok=False, error="429 too many requests"),
            FakeProvider("b", ok=False, error="503"),
        ],
        role="agent",
    )

    result = await hedged.complete(request())

    assert not result.ok
    assert "429" in (result.error or "") and "503" in (result.error or "")
    assert result.is_rate_limited


async def test_stream_ilk_cikti_ureten_akis_kazanir():
    hizli = FakeProvider("hizli", chunks=("mer", "haba"), delay=0.0)
    yavas = FakeProvider("yavas", chunks=("gec",), delay=0.5)
    hedged = HedgedProvider([yavas, hizli], role="agent")

    metin = ""
    sonuc = None
    async for item in hedged.stream(request()):
        if isinstance(item, TextChunk):
            metin += item.text
        elif isinstance(item, StreamDone):
            sonuc = item.result

    assert metin == "merhaba"
    assert sonuc is not None and sonuc.model == "hizli"


async def test_stream_basarisiz_acilisi_atlayip_saglama_gecer():
    bozuk = FakeProvider("bozuk", ok=False, error="429", delay=0.0)
    saglam = FakeProvider("saglam", chunks=("iyi",), delay=0.05)
    hedged = HedgedProvider([bozuk, saglam], role="agent")

    parcalar = [item.text async for item in hedged.stream(request()) if isinstance(item, TextChunk)]

    assert parcalar == ["iyi"]


async def test_stream_hepsi_basarisizsa_tek_streamdone_ile_biter():
    hedged = HedgedProvider(
        [FakeProvider("a", ok=False, error="429"), FakeProvider("b", ok=False, error="500")],
        role="agent",
    )

    items = [item async for item in hedged.stream(request())]

    assert len(items) == 1
    assert isinstance(items[0], StreamDone)
    assert not items[0].result.ok


async def test_tek_saglayicida_yaristirma_yapilmaz():
    tek = FakeProvider("tek", chunks=("a", "b"))
    hedged = HedgedProvider([tek], role="agent")

    items = [item async for item in hedged.stream(request())]

    assert [i.text for i in items if isinstance(i, TextChunk)] == ["a", "b"]
