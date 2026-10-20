"""Zengin yedek zinciri — kademe yükselten model geçişi (Faz 3, Görev 1, C6).

Bugüne kadar `agent.fallback` yalnız AYNI modelin farklı sağlayıcılardaki
kopyalarını (nemotron-super@NIM → nemotron-super@OpenRouter → gpt-oss@OpenRouter)
deniyordu. Bu, denetimde (17 Eylül) istenen "gerçekten FARKLI bir kademeye
yükselen zincir" değildi. Bu modül iki şeyi doğrular:

1. Zincirde model GÖVDESİ (sağlayıcı önekini saymadan) birden fazla farklı aile
   bulunur — yalnız aynı modelin sağlayıcı kopyaları değil.
2. Zincire eklenen `nemotron-3-ultra-550b-a55b` (22 Eylül'de canlı ölçüldü: NIM
   3.01s / OpenRouter 21.75s, ikisi de doğru araç çağrısı yaptı) hem NIM hem
   OpenRouter kopyasıyla zincirde yer alır — tek nokta arızası kalmaz.

Mevcut davranışın regresyonu (hız sınırında zincir geçişi + bildirim, ardışık
iki modelin hız sınırına takılınca üçüncüye geçiş) `fakes.ScriptedProvider` ile
ayrıca kilitlenir; bunlar canlı ağ GEREKTİRMEZ.
"""

from __future__ import annotations

import asyncio

from fusion_cli.config.loader import load_config
from fusion_cli.core.events import ModelFallbackActivated
from fusion_cli.core.types import CompletionRequest, Message, ModelResult
from fusion_cli.providers.chain import FallbackProvider


def _model_govdesi(model_id: str) -> str:
    """Sağlayıcı önekini ve `:free` sonekini at, geriye model gövdesini bırak.

    `nvidia_nim/nvidia/nemotron-3-super-120b-a12b` ve
    `openrouter/nvidia/nemotron-3-super-120b-a12b:free` AYNI gövdeyi paylaşır;
    test bu ikisini "farklı model" SAYMAMALI, yalnız gerçekten farklı aileleri
    (ör. `nemotron-3-ultra-550b-a55b`, `gpt-oss-120b`) ayrı sayar.
    """
    body = model_id.split("/", 1)[1] if "/" in model_id else model_id
    return body.removesuffix(":free")


def test_agent_zinciri_farkli_kademeye_yukselir():
    config = load_config()

    gövdeler = {_model_govdesi(model) for model in config.agent.models}

    # Yalnız aynı modelin sağlayıcı kopyaları olsaydı tek gövde olurdu; zincir
    # artık en az iki GERÇEKTEN farklı model gövdesi taşımalı.
    assert len(gövdeler) >= 2, f"zincir hâlâ tek model gövdesinden ibaret: {gövdeler}"
    # nemotron-3-ultra 22 Eylül'de canlı ölçülüp zincire eklendi (bkz. defaults.yaml).
    assert any("nemotron-3-ultra" in govde for govde in gövdeler), (
        f"ölçülen kademe-yükselten model zincirde yok: {gövdeler}"
    )


def test_ultra_modelinin_iki_saglayicidan_kopyasi_zincirde_var():
    """Ultra'nın kendisi de tek nokta arızası taşımamalı: NIM VE OpenRouter kopyası
    ikisi de zincirde bulunmalı (mevcut chain deseni — bkz. `nemotron-super` için
    zaten uygulanan aynı ikili kopya kuralı)."""
    config = load_config()

    nim_ultra = "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"
    openrouter_ultra = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"

    assert nim_ultra in config.agent.models
    assert openrouter_ultra in config.agent.models

    low_tier = config.tier_by_name("low")
    assert low_tier is not None
    assert nim_ultra in low_tier.agent.models
    assert openrouter_ultra in low_tier.agent.models


def test_zincirdeki_her_model_config_testinden_gecer():
    """Regresyon kilidi: yeni eklenen modeller de mevcut 'her kademe ücretsizdir'
    kuralına uyar (NIM modeli ya da OpenRouter `:free` soneki)."""
    config = load_config()

    uydurulan = [
        model
        for model in config.agent.models
        if not (model.startswith("nvidia_nim/") or model.endswith(":free"))
    ]

    assert uydurulan == [], f"ücretsiz olmayan model zincire sızdı: {uydurulan}"


def test_hiz_sinirinda_zincir_gecisi_bildirim_yayinlar():
    """Regresyon: ilk model hız sınırına takılınca `ModelFallbackActivated`
    doğru `fallback_model` alanıyla yayınlanır (mevcut davranış, C6'nın
    "kullanıcıya görünür bildirim" şartı)."""

    class _Yayinlayici:
        def __init__(self) -> None:
            self.olaylar: list[object] = []

        def publish(self, event: object) -> None:
            self.olaylar.append(event)

    class _SahteSaglayici:
        def __init__(self, label: str, *, basarili: bool) -> None:
            self.label = label
            self._basarili = basarili

        async def complete(self, request: CompletionRequest) -> ModelResult:
            if self._basarili:
                return ModelResult(
                    name="agent", model=self.label, text="tamam", latency_ms=1, ok=True
                )
            return ModelResult(
                name="agent",
                model=self.label,
                text="",
                latency_ms=1,
                ok=False,
                error="429 hız sınırı",
            )

    yayinlayici = _Yayinlayici()
    zincir = FallbackProvider(
        [
            _SahteSaglayici("model-a", basarili=False),
            _SahteSaglayici("model-b", basarili=True),
        ],
        role="agent",
        publisher=yayinlayici,
    )

    request = CompletionRequest(
        messages=(Message(role="user", content="merhaba"),),
        temperature=0.0,
        max_tokens=16,
        timeout_s=5,
    )
    result = asyncio.run(zincir.complete(request))

    assert result.model == "model-b"
    fallback_olaylari = [
        olay for olay in yayinlayici.olaylar if isinstance(olay, ModelFallbackActivated)
    ]
    assert len(fallback_olaylari) == 1
    assert fallback_olaylari[0].fallback_model == "model-b"
    assert fallback_olaylari[0].requested_model == "model-a"


def test_ust_uste_iki_model_hiz_sinirina_takilinca_ucuncuye_gecer():
    """Zincirde en az 3 basamak varken ikisi art arda 429 dönse bile üçüncü
    denenir (bugünkü 3-4 basamaklı zincirlerde zaten çalışıyor olmalı; yeni
    eklenen basamak için tekrar sınanır)."""

    class _SahteSaglayici:
        def __init__(self, label: str, *, basarili: bool) -> None:
            self.label = label
            self._basarili = basarili

        async def complete(self, request: CompletionRequest) -> ModelResult:
            if self._basarili:
                return ModelResult(
                    name="agent", model=self.label, text="tamam", latency_ms=1, ok=True
                )
            return ModelResult(
                name="agent",
                model=self.label,
                text="",
                latency_ms=1,
                ok=False,
                error="429 hız sınırı",
            )

    zincir = FallbackProvider(
        [
            _SahteSaglayici("model-a", basarili=False),
            _SahteSaglayici("model-b", basarili=False),
            _SahteSaglayici("model-c", basarili=True),
        ],
        role="agent",
        publisher=None,
    )

    request = CompletionRequest(
        messages=(Message(role="user", content="merhaba"),),
        temperature=0.0,
        max_tokens=16,
        timeout_s=5,
    )
    result = asyncio.run(zincir.complete(request))

    assert result.model == "model-c"
