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


# P1-20 — Ölçüldü (30 Ekim): Ollama `num_ctx` her makinede ve her modelde sabit 64k idi. 8 GB
# makinede bellek baskısı, bağlamı 8k olan modelde (kırpma) yanlış pencere göstergesi üretiyordu.
GIB = 1024**3


@pytest.fixture
def _ollama(monkeypatch):
    state = {"ram": 16 * GIB, "model_max": None}
    monkeypatch.setattr(context_window, "_total_ram_bytes", lambda: state["ram"])
    monkeypatch.setattr(
        context_window, "_ollama_context_length", lambda _m, _base: state["model_max"]
    )
    context_window.ollama_num_ctx.cache_clear()
    yield state
    context_window.ollama_num_ctx.cache_clear()


def test_ollama_baglami_ram_kademesine_gore_secilir(_ollama):
    cases = {8: 32_768, 16: 65_536, 24: 65_536, 32: 131_072, 64: 131_072}
    for ram_gib, beklenen in cases.items():
        _ollama["ram"] = ram_gib * GIB
        context_window.ollama_num_ctx.cache_clear()
        assert context_window.ollama_num_ctx("ollama_chat/m") == beklenen, ram_gib


def test_ollama_baglami_modelin_gercek_penceresini_asmaz(_ollama):
    _ollama["ram"] = 64 * GIB
    _ollama["model_max"] = 40_960

    assert context_window.ollama_num_ctx("ollama_chat/qwen3:8b") == 40_960
    assert context_window.input_window_tokens("ollama_chat/qwen3:8b") == 40_960


def test_ram_ve_model_bilinmiyorsa_olculmus_varsayilana_donulur(_ollama):
    _ollama["ram"] = None

    assert context_window.ollama_num_ctx("ollama/m") == context_window.OLLAMA_NUM_CTX


def test_ollama_show_cevabindan_baglam_uzunlugu_okunur():
    show = {"model_info": {"general.architecture": "qwen3", "qwen3.context_length": 40_960}}

    assert context_window._context_length_from_show(show) == 40_960
    assert context_window._context_length_from_show({"model_info": {}}) is None
    assert (
        context_window._context_length_from_show({"model_info": {"x.context_length": True}}) is None
    )
    assert context_window._context_length_from_show("bozuk") is None


def test_ollama_ulasilamazsa_none_doner_ve_hata_yutulur():
    # Hiçbir şeyin dinlemediği yerel port: bağlantı reddedilir.
    assert context_window._ollama_context_length("m", "http://127.0.0.1:9") is None
