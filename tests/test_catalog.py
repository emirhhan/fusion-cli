"""Model kataloğu — ağsız, sahte yanıtlarla."""

from __future__ import annotations

import httpx
import pytest

from fusion_cli.providers import catalog


def _sahte_yanit(monkeypatch, payload, *, hata=None):
    class _Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            if hata is not None:
                raise hata
            return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(catalog.httpx, "Client", _Client)


def test_yalnizca_ucretsiz_modeller_dondurulur(monkeypatch):
    _sahte_yanit(
        monkeypatch,
        {
            "data": [
                {"id": "a/free", "pricing": {"prompt": "0"}, "context_length": 1000},
                {"id": "b/paid", "pricing": {"prompt": "0.002"}},
                {"id": "c/free", "pricing": {"prompt": "0.00"}},
            ]
        },
    )

    entries = catalog.fetch_openrouter_free()

    assert [entry.model_id for entry in entries] == ["openrouter/a/free", "openrouter/c/free"]


def test_litellm_kimlik_onekleri_eklenir(monkeypatch):
    _sahte_yanit(monkeypatch, {"data": [{"id": "x/y", "pricing": {"prompt": "0"}}]})

    assert catalog.fetch_openrouter_free()[0].model_id.startswith("openrouter/")


def test_baglam_uzunlugu_okunur(monkeypatch):
    _sahte_yanit(
        monkeypatch,
        {"data": [{"id": "a/b", "pricing": {"prompt": "0"}, "context_length": 262144}]},
    )

    assert catalog.fetch_openrouter_free()[0].context_length == 262144


def test_bozuk_baglam_uzunlugu_sifira_duser(monkeypatch):
    _sahte_yanit(
        monkeypatch,
        {"data": [{"id": "a/b", "pricing": {"prompt": "0"}, "context_length": "cok"}]},
    )

    assert catalog.fetch_openrouter_free()[0].context_length == 0


def test_ag_hatasi_bos_liste_dondurur(monkeypatch):
    _sahte_yanit(monkeypatch, {}, hata=httpx.ConnectError("ag yok"))

    assert catalog.fetch_openrouter_free() == ()


def test_beklenmedik_govde_bos_liste_dondurur(monkeypatch):
    _sahte_yanit(monkeypatch, {"beklenmedik": "yapi"})

    assert catalog.fetch_openrouter_free() == ()


def test_fiyat_bilgisi_olmayan_model_ucretsiz_sayilmaz(monkeypatch):
    _sahte_yanit(monkeypatch, {"data": [{"id": "a/b"}]})

    assert catalog.fetch_openrouter_free() == ()


def test_nim_anahtarsiz_bos_doner(monkeypatch):
    monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)

    assert catalog.fetch_nim() == ()


def test_nim_anahtarla_katalog_getirir(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nvapi-test")
    _sahte_yanit(monkeypatch, {"data": [{"id": "meta/llama"}]})

    assert catalog.fetch_nim()[0].model_id == "nvidia_nim/meta/llama"


@pytest.mark.parametrize("fiyat", ["0", "0.0", "0.00"])
def test_ucretsiz_fiyat_bicimleri_taninir(monkeypatch, fiyat):
    _sahte_yanit(monkeypatch, {"data": [{"id": "a/b", "pricing": {"prompt": fiyat}}]})

    assert len(catalog.fetch_openrouter_free()) == 1
