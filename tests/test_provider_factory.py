"""Sağlayıcı kurma — katman sırası.

Sıra ürünün davranışını belirler: yeniden deneme her modelin KENDİ içinde olmalı,
zincire geçiş ancak o model tükendiğinde. Katmanlar ters sırada kurulsaydı "her
modele iki deneme" kuralı, zincirin TAMAMINA iki deneme anlamına gelirdi.
"""

from __future__ import annotations

from fusion_cli.core.types import ModelSpec
from fusion_cli.providers.chain import FallbackProvider
from fusion_cli.providers.factory import build_provider
from fusion_cli.providers.retrying import RetryingProvider

GECIKMELER = (34.0, 68.0)

SPEC = ModelSpec(
    name="test",
    model="nvidia_nim/z-ai/glm-5.2",
    fallback=("openrouter/openai/gpt-oss-20b:free",),
)


def _halkalar(spec: ModelSpec, delays: tuple[float, ...]) -> tuple[object, ...]:
    """Kurulan yığındaki zincir halkalarını oku."""
    provider = build_provider(spec, publisher=None, retry_delays_s=delays)
    assert isinstance(provider, FallbackProvider)
    return provider._providers  # type: ignore[attr-defined]


def test_yeniden_deneme_zincirin_icinde_her_modele_ayri_uygulanir():
    halkalar = _halkalar(SPEC, GECIKMELER)

    assert len(halkalar) == 2, "zincirde birincil ve yedek olmalı"
    assert all(isinstance(halka, RetryingProvider) for halka in halkalar)


def test_gecikme_yoksa_yeniden_deneme_katmani_hic_kurulmaz():
    halkalar = _halkalar(SPEC, ())

    assert not any(isinstance(halka, RetryingProvider) for halka in halkalar)


def test_zincir_spec_sirasini_korur():
    """Birincil daima ilk sıradadır: sıralı zincirde sıra DAVRANIŞTIR."""
    provider = build_provider(SPEC, publisher=None, retry_delays_s=())

    assert provider.label == "nvidia_nim/z-ai/glm-5.2"


def test_strict_spec_fallback_tanimli_olsa_da_tek_yaprak_kurar():
    """Tek-model seçimi config'te kalmış yedek yüzünden sessizce değişmemeli."""
    strict = ModelSpec(
        name="secilen",
        model="gemini_web/main/auto",
        fallback=("openrouter/openai/gpt-oss-20b:free",),
        tags=("strict",),
    )

    halkalar = _halkalar(strict, ())

    assert len(halkalar) == 1


def test_web_session_modeli_api_yerine_web_adaptoruyle_kurulur():
    """Model bir web ucuyla eşleşiyorsa yaprak, LiteLLM yerine web adaptörüdür."""
    from fusion_cli.config.models import WebSessionConfig
    from fusion_cli.providers.web_registry import WebSessionRegistry
    from fusion_cli.providers.web_session import WebProviderAdapter

    async def _fake_transport(credential, messages, model):
        return "ok"

    sessions = (WebSessionConfig(model="benim-uc", endpoint="http://x/v1"),)
    registry = WebSessionRegistry(sessions, environ={})
    spec = ModelSpec(name="agent", model="benim-uc")

    provider = build_provider(
        spec,
        publisher=None,
        retry_delays_s=(),
        web_sessions=registry,
    )

    # Yaprağa (fallback zincirinin tek halkasına) kadar in: web adaptörü olmalı.
    assert isinstance(provider, FallbackProvider)
    (leaf,) = provider._providers  # type: ignore[attr-defined]
    assert isinstance(leaf, WebProviderAdapter)


def test_web_session_eslesmezse_normal_api_yolu_kullanilir():
    """Eşleşmeyen model web adaptörü kurmaz; mevcut LiteLLM yolu korunur."""
    from fusion_cli.providers.web_registry import WebSessionRegistry
    from fusion_cli.providers.web_session import WebProviderAdapter

    registry = WebSessionRegistry((), environ={})
    provider = build_provider(SPEC, publisher=None, retry_delays_s=(), web_sessions=registry)

    assert isinstance(provider, FallbackProvider)
    assert not any(
        isinstance(p, WebProviderAdapter)
        for p in provider._providers  # type: ignore[attr-defined]
    )


def test_kayitsiz_native_web_modeli_litellm_yerine_acik_hata_verir():
    """Silinmiş/kurulmamış web model id'si yanlışlıkla LiteLLM'e gitmez."""
    import asyncio

    from fusion_cli.core.types import CompletionRequest, Message

    spec = ModelSpec(name="agent", model="chatgpt_web/main/auto")
    provider = build_provider(spec, publisher=None, retry_delays_s=())
    result = asyncio.run(
        provider.complete(
            CompletionRequest(
                messages=(Message("user", "merhaba"),),
                temperature=0.0,
                max_tokens=16,
                timeout_s=1.0,
            )
        )
    )
    assert result.ok is False
    assert "etkin web oturumu yok" in (result.error or "")
