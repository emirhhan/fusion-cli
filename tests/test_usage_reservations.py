"""Paralel model istekleri ortak bütçeyi aşmaz; iptal edilen çağrı SIFIR sayılmaz (WP20 madde 2).

Zaten karşılanan kısımlar mevcut testlerde kilitli:
- ortak hak, çağrı başlamadan atomik tüketilir:
  `test_turn_budget.py::test_parallel_model_admission_reserves_only_remaining_slot`
- rezervasyon yapılıp yanıt gelmeyen çağrı "bilinmeyen" kalır, sıfır olmaz:
  `test_usage_ledger.py::test_duplicate_response_does_not_double_count_and_unknown_is_visible`

Bu dosya Ölçülen açığı kapatır (29 Ekim): `EventingProvider`, çağrı başlarken
`ModelCallStarted` yayınlıyor ama iptalde (yavaş aday `gather_with_cutoff` ile
kesildi, ya da çağrı zaman aşımına uğradı) hiçbir bitiş olayı yoktu. Böyle bir
çağrı `CostTracker` ve `UsageMeter` için hiç var olmamış gibiydi: maliyeti
bilinmiyor olduğu hâlde toplam "tam" görünüyordu.
"""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.appserver.usage import UsageMeter
from fusion_cli.core.budget import TurnBudget
from fusion_cli.core.concurrency import gather_with_cutoff
from fusion_cli.core.events import ModelCallAbandoned, ModelCallFinished, ModelCallStarted
from fusion_cli.core.types import CompletionRequest, Message, ModelResult, StreamDone, TokenUsage
from fusion_cli.observability.cost import CostTracker
from fusion_cli.providers.eventing import EventingProvider


class _Clock:
    def monotonic(self) -> float:
        return 0.0

    def now(self) -> float:
        return 0.0


class _Yayin:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class _Yavas:
    """Yanıtı hiç gelmeyen sağlayıcı."""

    label = "yavas/model"

    async def complete(self, request: CompletionRequest) -> ModelResult:
        await asyncio.sleep(3600)
        raise AssertionError("ulaşılamaz")

    async def stream(self, request: CompletionRequest):
        await asyncio.sleep(3600)
        yield StreamDone(  # pragma: no cover - ulaşılamaz
            ModelResult(name="x", model="x", text="", latency_ms=0, ok=True)
        )


class _Hizli:
    label = "hizli/model"

    async def complete(self, request: CompletionRequest) -> ModelResult:
        return ModelResult(
            name="hizli",
            model="hizli/model",
            text="tamam",
            latency_ms=1,
            ok=True,
            usage=TokenUsage(
                10, 5, 0.001, prompt_measured=True, completion_measured=True, cost_known=True
            ),
        )


def _istek() -> CompletionRequest:
    return CompletionRequest(
        messages=(Message("user", "merhaba"),),
        temperature=0.0,
        max_tokens=16,
        timeout_s=5.0,
        max_retries=0,
    )


async def test_zaman_asimina_ugrayan_complete_iptal_olayi_yayinlar() -> None:
    yayin = _Yayin()
    saglayici = EventingProvider(_Yavas(), publisher=yayin, role="aday")

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(saglayici.complete(_istek()), timeout=0.01)

    baslayan = [e for e in yayin.events if isinstance(e, ModelCallStarted)]
    iptal = [e for e in yayin.events if isinstance(e, ModelCallAbandoned)]
    assert len(baslayan) == len(iptal) == 1
    assert iptal[0].call_id == baslayan[0].call_id
    assert iptal[0].model == "yavas/model"
    assert not any(isinstance(e, ModelCallFinished) for e in yayin.events)


async def test_akis_iptalinde_de_iptal_olayi_yayinlanir() -> None:
    yayin = _Yayin()
    saglayici = EventingProvider(_Yavas(), publisher=yayin, role="agent")

    async def tuket() -> None:
        async for _ in saglayici.stream(_istek()):
            pass

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(tuket(), timeout=0.01)

    assert len([e for e in yayin.events if isinstance(e, ModelCallAbandoned)]) == 1


async def test_tamamlanan_cagri_iptal_olayi_yayinlamaz() -> None:
    yayin = _Yayin()
    await EventingProvider(_Hizli(), publisher=yayin, role="aday").complete(_istek())
    assert not any(isinstance(e, ModelCallAbandoned) for e in yayin.events)


async def test_kesilen_yavas_aday_maliyeti_bilinmiyor_olarak_sayilir() -> None:
    """Fusion adayları: hızlı biter, yavaş grace/hard cap ile kesilir."""
    yayin = _Yayin()
    maliyet = CostTracker()
    olcer = UsageMeter()

    def dinle(olay: object) -> None:
        maliyet.handle(olay)  # type: ignore[arg-type]
        olcer.observe(olay)  # type: ignore[arg-type]

    hizli = EventingProvider(_Hizli(), publisher=yayin, role="aday")
    yavas = EventingProvider(_Yavas(), publisher=yayin, role="aday")
    sonuclar = await gather_with_cutoff(
        [lambda: hizli.complete(_istek()), lambda: yavas.complete(_istek())],
        is_success=lambda sonuc: sonuc.ok,
        enough_success=1,
        grace_s=0.01,
        hard_cap_s=0.05,
    )
    for olay in yayin.events:
        dinle(olay)

    assert len(sonuclar) == 1
    assert maliyet.abandoned_calls == 1
    assert maliyet.cost_complete is False
    yuk = olcer.payload()
    assert yuk["cagri"] == 1
    assert yuk["belirsiz_cagri"] == 1
    assert yuk["maliyet_tam"] is False
    # Ölçülen kısım korunur: bilinmeyen çağrı toplamı sıfırlamaz ya da şişirmez.
    assert yuk["toplam_token"] == 15


def test_hic_iptal_yoksa_maliyet_tam_gorunur() -> None:
    olcer = UsageMeter()
    olcer.observe(
        ModelCallFinished(
            role="agent",
            result=ModelResult(
                name="a",
                model="a/b",
                text="x",
                latency_ms=1,
                ok=True,
                usage=TokenUsage(1, 1, prompt_measured=True, completion_measured=True),
            ),
        )
    )
    assert olcer.payload()["maliyet_tam"] is True
    assert olcer.payload()["belirsiz_cagri"] == 0


def test_paralel_cagri_ortak_hakki_asmaz_ve_reddedilen_rezervasyon_olusturmaz() -> None:
    butce = TurnBudget(
        clock=_Clock(),  # type: ignore[arg-type]
        max_model_calls=3,
        max_verify_rounds=1,
        max_empty_retries=1,
        max_contract_repairs=1,
        max_auto_continues=1,
        max_idle_rounds=1,
    )
    kabul = [butce.reserve_model_call() for _ in range(8)]
    assert kabul.count(True) == 3
    anlik = butce.usage.snapshot()
    # Reddedilen 5 deneme deftere GİRMEZ; kabul edilen 3'ü yanıt gelmediği için bilinmiyor.
    assert anlik.total_calls == 3
    assert anlik.unknown_calls == 3
    assert anlik.cost_known is False


def test_ozet_satiri_iptal_edilen_cagriyi_alt_sinir_olarak_gosterir() -> None:
    from fusion_cli.ui.tables import cost_summary

    izleyici = CostTracker()
    assert "bilinmiyor" not in cost_summary(izleyici)
    izleyici.handle(ModelCallAbandoned(role="aday", model="yavas/model", call_id="1"))
    assert "+1 çağrının tüketimi bilinmiyor" in cost_summary(izleyici)
    izleyici.reset()
    assert izleyici.abandoned_calls == 0
