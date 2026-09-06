"""Canlı bir koşu ağsız yeniden üretilebilir.

Blueprint'in kuralı: tekrar oynatma deterministik olmalı. Ajan hataları aksi
hâlde tahminle ayıklanır — 5-6 Eylül koşularında bir başarısızlığı anlamak için
transkriptleri elle okumak zorunda kaldık ve o koşuyu bir daha aynen üretemedik.

Kayıttan çalan sağlayıcı, izdeki model yanıtlarını SIRASIYLA döndürür; kayıt
bittiğinde uydurmaz, açıkça "kayıt tükendi" der.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.events import ModelCallFinished, ToolExecuted, ToolOutcome
from fusion_cli.core.types import CompletionRequest, Message, ModelResult
from fusion_cli.observability.trace_store import TraceStore
from fusion_cli.providers.replay import ReplayProvider, recorded_results


def _sonuc(text: str) -> ModelResult:
    return ModelResult(name="secilen", model="test/model", text=text, latency_ms=5, ok=True)


def _istek() -> CompletionRequest:
    return CompletionRequest(
        messages=(Message("user", "merhaba"),), temperature=0.0, max_tokens=100, timeout_s=10.0
    )


@pytest.mark.asyncio
async def test_kayitli_yanitlar_sirayla_donulur():
    saglayici = ReplayProvider((_sonuc("bir"), _sonuc("iki")))

    assert (await saglayici.complete(_istek())).text == "bir"
    assert (await saglayici.complete(_istek())).text == "iki"


@pytest.mark.asyncio
async def test_kayit_bitince_uydurmaz():
    saglayici = ReplayProvider((_sonuc("tek"),))
    await saglayici.complete(_istek())

    sonuc = await saglayici.complete(_istek())

    assert not sonuc.ok
    assert "kayıt" in (sonuc.error or "").casefold()


@pytest.mark.asyncio
async def test_akis_tek_stream_done_ile_biter():
    from fusion_cli.core.types import StreamDone

    saglayici = ReplayProvider((_sonuc("metin"),))

    parcalar = [item async for item in saglayici.stream(_istek())]

    assert isinstance(parcalar[-1], StreamDone)
    assert sum(isinstance(item, StreamDone) for item in parcalar) == 1


def test_izden_model_yanitlari_cikarilir(tmp_path):
    store = TraceStore(tmp_path)
    yazici = store.writer("kosu")
    yazici.handle(ModelCallFinished(role="secilen", result=_sonuc("ilk")))
    yazici.handle(ToolExecuted(name="read_file", args={}, outcome=ToolOutcome.OK, output=""))
    yazici.handle(ModelCallFinished(role="secilen", result=_sonuc("ikinci")))
    yazici.close()

    sonuclar = recorded_results(store.read("kosu"))

    assert [item.text for item in sonuclar] == ["ilk", "ikinci"]
