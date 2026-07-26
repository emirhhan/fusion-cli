"""Çekirdek değer nesneleri."""

from __future__ import annotations

import pytest

from fusion_cli.core.errors import ConfigError, FusionError, ProviderError
from fusion_cli.core.types import ModelResult, TokenUsage, is_rate_limit_error


def test_token_toplami_hesaplanir():
    assert TokenUsage(prompt_tokens=3, completion_tokens=4).total_tokens == 7


@pytest.mark.parametrize(
    "error", ["429 Too Many Requests", "RateLimitError", "quota exceeded", "rate limit"]
)
def test_hiz_siniri_farkli_ifadelerde_taninir(error):
    result = ModelResult(name="a", model="m", text="", latency_ms=1, ok=False, error=error)

    assert result.is_rate_limited


def test_basarili_sonuc_hiz_siniri_sayilmaz():
    result = ModelResult(name="a", model="m", text="x", latency_ms=1, ok=True)

    assert not result.is_rate_limited


def test_hiz_siniri_disi_hata_ayirt_edilir():
    result = ModelResult(name="a", model="m", text="", latency_ms=1, ok=False, error="503")

    assert not result.is_rate_limited


def test_hiz_siniri_ham_metinden_de_taninir():
    """Agent motoru `ModelResult` değil yalnızca hata METNİ taşır; o yol da tanınmalı."""
    assert is_rate_limit_error("litellm.RateLimitError: ... 429 Too Many Requests")
    assert is_rate_limit_error("free-models-per-day quota exceeded")
    assert not is_rate_limit_error("503 Service Unavailable")
    assert not is_rate_limit_error("")
    assert not is_rate_limit_error(None)


def test_tum_proje_hatalari_tek_kokten_turer():
    assert issubclass(ConfigError, FusionError)
    assert issubclass(ProviderError, FusionError)
