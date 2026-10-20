"""Model girdi penceresi okuması."""

from __future__ import annotations

import pytest

from fusion_cli.providers import context_window


@pytest.fixture(autouse=True)
def _temiz_onbellek():
    context_window.input_window_tokens.cache_clear()
    yield
    context_window.input_window_tokens.cache_clear()


def _katalog(monkeypatch, pencereler):
    monkeypatch.setattr(context_window, "_catalog_window", pencereler.get)


def test_nim_modeli_katalogda_yoksa_openrouter_kaydindan_en_dar_pencere_okunur(monkeypatch):
    """Ölçüldü (28 Eylül): bilinmeyen pencere en dar varsayılana düşüyor, gösterge
    birkaç okumada "Yakında özetlenecek" diyordu."""
    _katalog(
        monkeypatch,
        {
            "openrouter/nvidia/ornek-model": 262_144,
            "openrouter/nvidia/ornek-model:free": 1_000_000,
        },
    )

    assert context_window.input_window_tokens("nvidia_nim/nvidia/ornek-model") == 262_144


def test_kendi_katalog_kaydi_varsa_o_kullanilir(monkeypatch):
    _katalog(
        monkeypatch,
        {"nvidia_nim/nvidia/ornek-model": 32_000, "openrouter/nvidia/ornek-model": 262_144},
    )

    assert context_window.input_window_tokens("nvidia_nim/nvidia/ornek-model") == 32_000


def test_hicbir_kayit_yoksa_pencere_uydurulmaz(monkeypatch):
    _katalog(monkeypatch, {})

    assert context_window.input_window_tokens("nvidia_nim/nvidia/ornek-model") is None
    assert context_window.input_window_tokens("gemini_web/main/auto") is None
