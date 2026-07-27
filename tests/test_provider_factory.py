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
