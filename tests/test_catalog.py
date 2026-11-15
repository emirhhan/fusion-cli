"""Model kataloğu — ağsız, sahte yanıtlarla."""

from __future__ import annotations

import httpx
import pytest

from fusion_cli.providers import catalog


def test_ollama_installed_models_are_discovered(monkeypatch):
    _sahte_yanit(
        monkeypatch, {"models": [{"name": "huihui_ai/qwen3.5-abliterated:9b"}, {"name": 123}, {}]}
    )
    result = catalog.fetch_ollama()
    assert [entry.model_id for entry in result] == ["ollama_chat/huihui_ai/qwen3.5-abliterated:9b"]


@pytest.mark.parametrize(
    ("status", "tool_calls", "expected"),
    [
        (200, [{"function": {"name": "sum", "arguments": '{"a":2,"b":3}'}}], True),
        (200, [], False),
        (404, [], False),
    ],
)
def test_nim_modeli_secmeden_once_arac_cagrisi_dogrulanir(
    monkeypatch, status, tool_calls, expected
):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-key")

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, *, headers, json):
            assert headers == {"Authorization": "Bearer test-key"}
            assert json["model"] == "z-ai/glm-5.3"
            return httpx.Response(
                status,
                json={"choices": [{"message": {"tool_calls": tool_calls}}]},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(catalog.httpx, "Client", Client)
    ok, reason = catalog.probe_nim_tools("nvidia_nim/z-ai/glm-5.3")

    assert ok is expected
    assert bool(reason) is not expected


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (
            404,
            {"detail": "Function 'abc': Not found for account 'GIZLI-HESAP'"},
            ["z-ai/glm-5.3 NIM'de bu hesap için sunulmuyor (404)", "Function 'abc': Not found"],
        ),
        (401, {}, ["anahtarı reddedildi (401)"]),
        (500, {}, ["NIM doğrulaması başarısız (500)."]),
    ],
)
def test_nim_sondasi_hatasi_nedenini_soyler_hesap_kimligini_sizdirmaz(
    monkeypatch, status, body, expected
):
    """Ölçüldü (2 Kasım 2026): yalın "NIM doğrulaması başarısız (404)" nedeni söylemiyordu."""
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-key")

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, *, headers, json):
            return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(catalog.httpx, "Client", Client)
    ok, reason = catalog.probe_nim_tools("nvidia_nim/z-ai/glm-5.3")

    assert ok is False
    assert all(part in reason for part in expected)
    assert "GIZLI-HESAP" not in reason


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
                {
                    "id": "a/free",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "context_length": 1000,
                },
                {"id": "b/paid", "pricing": {"prompt": "0.002"}},
                {"id": "c/free", "pricing": {"prompt": "0.00", "completion": "0.00"}},
            ]
        },
    )

    entries = catalog.fetch_openrouter_free()

    assert [entry.model_id for entry in entries] == ["openrouter/a/free", "openrouter/c/free"]


def test_litellm_kimlik_onekleri_eklenir(monkeypatch):
    _sahte_yanit(
        monkeypatch, {"data": [{"id": "x/y", "pricing": {"prompt": "0", "completion": "0"}}]}
    )

    assert catalog.fetch_openrouter_free()[0].model_id.startswith("openrouter/")


def test_baglam_uzunlugu_okunur(monkeypatch):
    _sahte_yanit(
        monkeypatch,
        {
            "data": [
                {
                    "id": "a/b",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "context_length": 262144,
                }
            ]
        },
    )

    assert catalog.fetch_openrouter_free()[0].context_length == 262144


def test_bozuk_baglam_uzunlugu_sifira_duser(monkeypatch):
    _sahte_yanit(
        monkeypatch,
        {
            "data": [
                {
                    "id": "a/b",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "context_length": "cok",
                }
            ]
        },
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


def test_sadece_girdisi_ucretsiz_olan_model_ucretsiz_sayilmaz(monkeypatch):
    _sahte_yanit(
        monkeypatch,
        {"data": [{"id": "a/b", "pricing": {"prompt": "0", "completion": "0.01"}}]},
    )

    assert catalog.fetch_openrouter_free() == ()
    assert catalog.fetch_openrouter_paid()[0].model_id == "openrouter/a/b"


def test_nim_anahtarsiz_bos_doner(monkeypatch):
    monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)

    assert catalog.fetch_nim() == ()


def test_nim_anahtarla_katalog_getirir(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nvapi-test")
    _sahte_yanit(monkeypatch, {"data": [{"id": "meta/llama"}]})

    assert catalog.fetch_nim()[0].model_id == "nvidia_nim/meta/llama"


@pytest.mark.parametrize("fiyat", ["0", "0.0", "0.00"])
def test_ucretsiz_fiyat_bicimleri_taninir(monkeypatch, fiyat):
    _sahte_yanit(
        monkeypatch, {"data": [{"id": "a/b", "pricing": {"prompt": fiyat, "completion": fiyat}}]}
    )

    assert len(catalog.fetch_openrouter_free()) == 1


def test_ucretli_liste_ucretsizlerin_tumleyenidir(monkeypatch):
    """`/development` ücretli kaynağı, ücretsiz süzgecin tersini göstermeli."""
    _sahte_yanit(
        monkeypatch,
        {
            "data": [
                {
                    "id": "a/free",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "context_length": 1000,
                },
                {"id": "b/paid", "pricing": {"prompt": "0.5"}, "context_length": 2000},
            ]
        },
    )

    ucretli = catalog.fetch_openrouter_paid()

    assert [giris.model_id for giris in ucretli] == ["openrouter/b/paid"]


def test_ucretli_listede_baglam_uzunlugu_okunur(monkeypatch):
    _sahte_yanit(
        monkeypatch,
        {"data": [{"id": "b/paid", "pricing": {"prompt": "0.5"}, "context_length": 200000}]},
    )

    assert catalog.fetch_openrouter_paid()[0].context_length == 200000


def test_ucretli_listede_ag_hatasi_bos_doner(monkeypatch):
    _sahte_yanit(monkeypatch, {}, hata=httpx.ConnectError("yok"))

    assert catalog.fetch_openrouter_paid() == ()


def test_ollama_adresi_ortamdan_okunur(monkeypatch):
    """Ölçüldü (30 Ekim): `fetch_ollama` 127.0.0.1:11434'e sabitti; LiteLLM ise
    `OLLAMA_API_BASE`'i okuyordu → başka portta/uzak makinede katalog boş görünüyordu
    (P1-21)."""
    from fusion_cli.providers.catalog import ollama_base_url

    monkeypatch.delenv("OLLAMA_API_BASE", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert ollama_base_url() == "http://127.0.0.1:11434"

    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0:11500")
    assert ollama_base_url() == "http://127.0.0.1:11500"  # bağlanma adresi 0.0.0.0 değildir

    monkeypatch.setenv("OLLAMA_HOST", "gpu-kutusu:11434")
    assert ollama_base_url() == "http://gpu-kutusu:11434"

    monkeypatch.setenv("OLLAMA_API_BASE", "http://yerel:9999/")
    assert ollama_base_url() == "http://yerel:9999"


def test_nim_sonda_cagrisi_sayilari_metin_dondurse_de_gecerli_sayar():
    """`2`/`3` yerine "2"/"3" döndüren model gerçekte araç çağırabiliyordur (P1-23)."""
    from fusion_cli.providers.catalog import _valid_sum_call

    cagri = {"function": {"name": "sum", "arguments": '{"a": "2", "b": "3"}'}}
    yanlis = {"function": {"name": "sum", "arguments": '{"a": 2, "b": 4}'}}

    assert _valid_sum_call(cagri) is True
    assert _valid_sum_call(yanlis) is False
