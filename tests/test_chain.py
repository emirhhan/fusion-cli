"""Yedek zinciri — sıralı deneme, atlama ve toplu başarısızlık davranışı."""

from __future__ import annotations

import pytest

from fusion_cli.core.errors import ProviderError
from fusion_cli.core.events import ModelFallbackActivated
from fusion_cli.core.types import CompletionRequest, Message, ModelResult, StreamDone, TextChunk
from fusion_cli.providers.chain import FallbackProvider

from .fakes import FakeProvider, request


class _Publisher:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event) -> None:
        self.events.append(event)


class SabitProvider:
    """Her çağrıda aynı sonucu döndüren, çağrılıp çağrılmadığını kaydeden sağlayıcı."""

    def __init__(self, sonuc: ModelResult) -> None:
        self._sonuc = sonuc
        self.cagrildi = False

    @property
    def label(self) -> str:
        return self._sonuc.model

    async def complete(self, request: CompletionRequest) -> ModelResult:
        self.cagrildi = True
        return self._sonuc

    async def stream(self, request: CompletionRequest):  # pragma: no cover - complete kullanılır
        raise NotImplementedError


def _istek() -> CompletionRequest:
    return CompletionRequest(
        messages=(Message("user", "x"),), temperature=0.0, max_tokens=16, timeout_s=5
    )


def test_saglayici_verilmezse_hata():
    with pytest.raises(ProviderError):
        FallbackProvider([], role="agent")


async def test_birincil_calisirsa_yedek_hic_denenmez():
    """Zincirin ÖZÜ: yedek, birincil başarısız olmadan hiç çalışmaz."""
    birincil = SabitProvider(
        ModelResult(name="a", model="birincil", text="cevap", latency_ms=1, ok=True)
    )
    yedek = SabitProvider(ModelResult(name="b", model="yedek", text="cevap", latency_ms=1, ok=True))

    sonuc = await FallbackProvider([birincil, yedek], role="agent").complete(_istek())

    assert sonuc.model == "birincil"
    assert not yedek.cagrildi


async def test_yavas_birincil_yarisi_kaybetmez():
    """Regresyon: zincir yarıştırılırken hızlı yedek, seçilen modeli eziyordu.

    Ölçülen sürelerle doğrulanmıştı: premium seçen kullanıcıya glm-5.2 yerine
    nemotron-ultra cevap veriyordu. Sıralı zincir bunu yapısal olarak imkânsız
    kılar — hız artık hangi modelin cevap verdiğini belirleyemez.
    """
    yavas_birincil = FakeProvider("secilen-yavas", chunks=("nitelikli",), delay=0.2)
    hizli_yedek = FakeProvider("yedek-hizli", chunks=("zayif",), delay=0.0)

    sonuc = await FallbackProvider([yavas_birincil, hizli_yedek], role="agent").complete(request())

    assert sonuc.model == "secilen-yavas"
    assert not hizli_yedek.started, "birincil çalışırken yedek hiç başlatılmamalı"


async def test_basarisiz_saglayiciyi_atlar():
    bozuk = FakeProvider("bozuk", ok=False, error="429 rate limit", delay=0.0)
    saglam = FakeProvider("saglam", chunks=("ok",), delay=0.0)

    sonuc = await FallbackProvider([bozuk, saglam], role="agent").complete(request())

    assert sonuc.ok and sonuc.model == "saglam"


async def test_fallback_devreye_girdiginde_nedeni_olay_olarak_yayinlar():
    publisher = _Publisher()
    bozuk = FakeProvider("gemini_web/main/auto", ok=False, error="web oturumu timeout")
    saglam = FakeProvider("nvidia_nim/openai/gpt-oss-120b", chunks=("ok",))

    sonuc = await FallbackProvider([bozuk, saglam], role="secilen", publisher=publisher).complete(
        request()
    )

    assert sonuc.model == "nvidia_nim/openai/gpt-oss-120b"
    (event,) = [item for item in publisher.events if isinstance(item, ModelFallbackActivated)]
    assert event.requested_model == "gemini_web/main/auto"
    assert event.fallback_model == "nvidia_nim/openai/gpt-oss-120b"
    assert "timeout" in event.reason


async def test_bos_cevap_yedegi_tetikler():
    """Boş ama "başarılı" cevap zinciri durdurmamalı.

    Ölçüldü: model bazen `ok=True` ama metinsiz ve araçsız cevap döndürüyor.
    Ölçüt `ok` olsaydı boş sonuç kabul edilir ve agent turu hiçbir şey yapmadan
    biterdi.
    """
    bos = SabitProvider(ModelResult(name="a", model="bos", text="", latency_ms=1, ok=True))
    dolu = SabitProvider(
        ModelResult(name="b", model="dolu", text="gerçek cevap", latency_ms=1, ok=True)
    )

    sonuc = await FallbackProvider([bos, dolu], role="test").complete(_istek())

    assert dolu.cagrildi, "boş cevapta yedek denenmeli"
    assert sonuc.text == "gerçek cevap"


async def test_hiz_siniri_yedegi_tetikler_ve_kullaniciya_yansimaz():
    """429 alan model turu düşürmemeli; zincirdeki sonraki model devralmalı.

    Ölçüldü (2026-07-26): NIM'in hız sınırı MODEL BAŞINADIR. Aynı anahtarla aynı
    saniyede `nemotron-super` 429 verirken `deepseek-v4-flash` çalışıyordu.
    """
    kisitli = SabitProvider(
        ModelResult(
            name="a",
            model="kisitli",
            text="",
            latency_ms=1,
            ok=False,
            error="429 Too Many Requests",
        )
    )
    calisan = SabitProvider(
        ModelResult(name="b", model="calisan", text="cevap", latency_ms=1, ok=True)
    )

    sonuc = await FallbackProvider([kisitli, calisan], role="agent").complete(_istek())

    assert sonuc.ok and sonuc.model == "calisan"
    assert not sonuc.is_rate_limited, "kullanıcı 429 görmemeli; yedek devraldı"


async def test_hepsi_basarisizsa_hata_firlatmaz():
    zincir = FallbackProvider(
        [
            FakeProvider("a", ok=False, error="429 too many requests"),
            FakeProvider("b", ok=False, error="503"),
        ],
        role="agent",
    )

    sonuc = await zincir.complete(request())

    assert not sonuc.ok
    assert "429" in (sonuc.error or "") and "503" in (sonuc.error or "")
    assert sonuc.is_rate_limited


async def test_etiket_birincil_modeldir_zincir_degil():
    """Etiket "bu sağlayıcı hangi modeldir" sorusunun cevabıdır.

    Zincirin tamamı döndürüldüğünde etiket olaya öyle giriyor ve ekranda üç satıra
    sarıyordu; üstelik hangi modelin GERÇEKTEN cevap verdiğini de söylemiyordu.
    """
    zincir = FallbackProvider(
        [FakeProvider("nvidia_nim/z-ai/glm-5.2"), FakeProvider("openrouter/yedek:free")],
        role="agent",
    )

    assert zincir.label == "nvidia_nim/z-ai/glm-5.2"


# --------------------------------------------------------------------------- #
# Akış
# --------------------------------------------------------------------------- #


async def test_stream_birincil_uretirse_yedek_denenmez():
    birincil = FakeProvider("birincil", chunks=("mer", "haba"), delay=0.0)
    yedek = FakeProvider("yedek", chunks=("baska",), delay=0.0)
    zincir = FallbackProvider([birincil, yedek], role="agent")

    metin = ""
    sonuc = None
    async for item in zincir.stream(request()):
        if isinstance(item, TextChunk):
            metin += item.text
        elif isinstance(item, StreamDone):
            sonuc = item.result

    assert metin == "merhaba"
    assert sonuc is not None and sonuc.model == "birincil"
    assert not yedek.started


async def test_stream_basarisiz_acilisi_atlayip_saglama_gecer():
    bozuk = FakeProvider("bozuk", ok=False, error="429", delay=0.0)
    saglam = FakeProvider("saglam", chunks=("iyi",), delay=0.0)
    zincir = FallbackProvider([bozuk, saglam], role="agent")

    parcalar = [item.text async for item in zincir.stream(request()) if isinstance(item, TextChunk)]

    assert parcalar == ["iyi"]


async def test_gecici_akil_yurutme_parcalari_yedegi_engellemez():
    class ReasoningFailure(FakeProvider):
        async def stream(self, request):
            yield TextChunk("düşünce", provisional=True)
            async for item in super().stream(request):
                yield item

    bozuk = ReasoningFailure("bozuk", ok=False, error="çıktı bütçesi doldu")
    saglam = FakeProvider("saglam", chunks=("iyi",))
    zincir = FallbackProvider([bozuk, saglam], role="agent")
    items = [item async for item in zincir.stream(request())]

    assert [item.text for item in items if isinstance(item, TextChunk)] == ["iyi"]
    assert isinstance(items[-1], StreamDone) and items[-1].result.model == "saglam"


async def test_secilen_model_yanit_uretemeden_butcesini_tuketirse_yedek_denenir():
    saglam = FakeProvider("yedek", chunks=("cevap",))

    class TruncatedProvider(FakeProvider):
        async def stream(self, request):
            yield StreamDone(
                ModelResult(
                    name="secilen",
                    model="secilen",
                    text="",
                    latency_ms=1,
                    ok=False,
                    truncated=True,
                    error="çıktı bütçesi doldu",
                )
            )

    zincir = FallbackProvider(
        [TruncatedProvider("secilen"), saglam], role="agent", only_when_unavailable=True
    )
    items = [item async for item in zincir.stream(request())]

    assert isinstance(items[-1], StreamDone) and items[-1].result.model == "yedek"


async def test_eksiksiz_cagri_da_butce_hatasindan_yedege_gecer():
    secilen = SabitProvider(
        ModelResult(
            name="secilen", model="secilen", text="", latency_ms=1, ok=False, truncated=True
        )
    )
    yedek = SabitProvider(
        ModelResult(name="yedek", model="yedek", text="cevap", latency_ms=1, ok=True)
    )

    sonuc = await FallbackProvider(
        [secilen, yedek], role="agent", only_when_unavailable=True
    ).complete(_istek())

    assert sonuc.model == "yedek"


async def test_stream_hepsi_basarisizsa_tek_streamdone_ile_biter():
    zincir = FallbackProvider(
        [FakeProvider("a", ok=False, error="429"), FakeProvider("b", ok=False, error="500")],
        role="agent",
    )

    items = [item async for item in zincir.stream(request())]

    assert len(items) == 1
    assert isinstance(items[0], StreamDone)
    assert not items[0].result.ok


async def test_stream_tek_saglayici_dogrudan_gecirilir():
    tek = FakeProvider("tek", chunks=("a", "b"), delay=0.0)
    zincir = FallbackProvider([tek], role="agent")

    items = [item async for item in zincir.stream(request())]

    assert [item.text for item in items if isinstance(item, TextChunk)] == ["a", "b"]
    assert isinstance(items[-1], StreamDone)


class _TakilanProvider:
    """Hiç cevap üretmeyen sağlayıcı (ölçüldü: Gemini "3.1 Pro" web oturumu)."""

    label = "gemini_web/main/auto"

    async def complete(self, request: CompletionRequest) -> ModelResult:
        import asyncio

        await asyncio.sleep(3600)
        raise AssertionError("ulaşılmamalı")

    async def stream(self, request: CompletionRequest):
        import asyncio

        await asyncio.sleep(3600)
        yield TextChunk("ulaşılmamalı")


def _kisa_istek() -> CompletionRequest:
    return CompletionRequest(
        messages=(Message("user", "x"),), temperature=0.0, max_tokens=16, timeout_s=0.05
    )


async def test_takilan_birincil_suresi_dolunca_yedege_gecer_akista():
    """Ölçüldü (27 Eylül): takılan web modeli turun bütün süresini yiyordu; yedek
    hiç denenmeden "120 saniyede tamamlanmadı" ile tur düşüyordu."""
    yayinci = _Publisher()
    yedek = FakeProvider("nvidia_nim/yedek", chunks=("yedekten ", "cevap"))
    zincir = FallbackProvider(
        [_TakilanProvider(), yedek], role="agent", publisher=yayinci, only_when_unavailable=True
    )
    parcalar = [item async for item in zincir.stream(_kisa_istek())]
    son = parcalar[-1]
    assert isinstance(son, StreamDone) and son.result.ok
    assert son.result.text == "yedekten cevap"
    gecis = [e for e in yayinci.events if isinstance(e, ModelFallbackActivated)]
    assert gecis and "yanıt vermedi" in gecis[0].reason


async def test_surekli_gecici_parca_gonderen_model_yedegi_engellemez():
    class ReasoningOnlyProvider:
        label = "dusunen"

        async def stream(self, request):
            import asyncio

            while True:
                yield TextChunk("düşünce", provisional=True)
                await asyncio.sleep(0.01)

    yedek = FakeProvider("yedek", chunks=("cevap",))
    zincir = FallbackProvider([ReasoningOnlyProvider(), yedek], role="agent")
    items = [item async for item in zincir.stream(_kisa_istek())]

    assert isinstance(items[-1], StreamDone) and items[-1].result.model == "yedek"


async def test_takilan_birincil_complete_yolunda_da_yedege_gecer():
    yedek = FakeProvider("nvidia_nim/yedek", chunks=("yedekten ", "cevap"))
    sonuc = await FallbackProvider([_TakilanProvider(), yedek], role="agent").complete(
        _kisa_istek()
    )
    assert sonuc.ok and sonuc.text == "yedekten cevap"
