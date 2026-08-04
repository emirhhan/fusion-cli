"""Yerel gateway — OpenAI-uyumlu ASGI uç noktası (gerçek sunucu açmadan test).

Sağlayıcı sahte enjekte edilir; ağ yok. `httpx.ASGITransport` uygulamayı doğrudan sürer.
"""

from __future__ import annotations

import json

import httpx
import pytest

from fusion_cli.gateway.app import GatewayApp
from fusion_cli.gateway.routing import available_models, resolve_spec
from fusion_cli.gateway.translate import GatewayError, to_openai_response, to_request

from .fakes import FakeProvider, make_config


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local")


def _app(reply="Merhaba, ben mock model.", ok=True):
    config = make_config()
    return GatewayApp(
        config, provider_factory=lambda spec: FakeProvider("mock", chunks=(reply,), ok=ok)
    )


# --- temel uçlar ----------------------------------------------------------- #


async def test_health_ok():
    async with _client(_app()) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_models_listeler():
    async with _client(_app()) as client:
        resp = await client.get("/v1/models")
    data = resp.json()
    assert data["object"] == "list"
    ids = {m["id"] for m in data["data"]}
    assert "auto" in ids


# --- sohbet (non-stream) --------------------------------------------------- #


async def test_chat_openai_bicimli_cevap_doner():
    async with _client(_app("Selam!")) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "merhaba"}]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "Selam!"
    assert body["choices"][0]["finish_reason"] == "stop"


async def test_chat_model_alani_zorunlu():
    async with _client(_app()) as client:
        resp = await client.post(
            "/v1/chat/completions", json={"messages": [{"role": "user", "content": "x"}]}
        )
    assert resp.status_code == 400
    assert "model" in resp.json()["error"]["message"]


async def test_chat_bos_messages_hata():
    async with _client(_app()) as client:
        resp = await client.post("/v1/chat/completions", json={"model": "auto", "messages": []})
    assert resp.status_code == 400


async def test_bilinmeyen_yol_404():
    async with _client(_app()) as client:
        resp = await client.get("/v1/olmayan")
    assert resp.status_code == 404


# --- akış (SSE) ------------------------------------------------------------ #


async def test_chat_stream_sse_ve_done():
    async with _client(_app("akan cevap")) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "x"}], "stream": True},
        )
    metin = resp.text
    assert "text/event-stream" in resp.headers["content-type"]
    assert "data: " in metin
    assert "akan cevap" in metin
    assert "[DONE]" in metin


# --- saf çeviri + çözümleme ------------------------------------------------ #


def test_to_request_varsayilanlari_kullanir():
    config = make_config()
    request, model, stream = to_request(
        {"model": "high", "messages": [{"role": "user", "content": "selam"}]}, config.runtime
    )
    assert model == "high"
    assert stream is False
    assert request.max_tokens == config.runtime.max_tokens  # koda gömülü değil, runtime'dan


def test_to_request_gecersiz_model_hata():
    with pytest.raises(GatewayError):
        to_request({"messages": [{"role": "user", "content": "x"}]}, make_config().runtime)


def test_resolve_spec_auto_agenta_cozer():
    config = make_config()
    assert resolve_spec(config, "auto").model == config.agent.model


def test_resolve_spec_ham_kimlik_dogrudan():
    config = make_config()
    spec = resolve_spec(config, "openai/gpt-4o")
    assert spec.model == "openai/gpt-4o"


def test_available_models_auto_icerir():
    assert "auto" in available_models(make_config())


def test_tool_call_cevaba_cevrilir():
    from fusion_cli.core.types import ModelResult, ToolCall

    result = ModelResult(
        name="m",
        model="m",
        text="",
        latency_ms=1,
        ok=True,
        tool_calls=(ToolCall(id="1", name="edit_file", arguments='{"path":"a"}'),),
    )
    body = to_openai_response(result, "auto")
    calls = body["choices"][0]["message"]["tool_calls"]
    assert calls[0]["function"]["name"] == "edit_file"
    assert json.loads(calls[0]["function"]["arguments"]) == {"path": "a"}
    assert body["choices"][0]["finish_reason"] == "tool_calls"


# --- yerel panel (dashboard) ----------------------------------------------- #


async def test_dashboard_html_doner():
    async with _client(_app()) as client:
        resp = await client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # Panelin yüklendiğini başlıktan ve kenar çubuğu markasından doğrula.
    assert "<title>Fusion — Kontrol Paneli</title>" in resp.text
    assert 'class="brand-name">Fusion<' in resp.text


async def test_api_providers_json():
    async with _client(_app()) as client:
        resp = await client.get("/api/providers")
    ids = {p["id"] for p in resp.json()["providers"]}
    assert "openrouter" in ids and "ollama" in ids


async def test_api_health_bos_baslar():
    async with _client(_app()) as client:
        resp = await client.get("/api/health")
    assert resp.json()["models"] == []


# --- interaktif kontrol paneli (yazma uçları) ------------------------------ #


def _app_with_store(tmp_path, key="test-key"):
    from fusion_cli.config.credentials import FernetSecretStore
    from fusion_cli.gateway.app import GatewayApp

    store = FernetSecretStore(tmp_path / "s.enc", secret_key=key)
    app = GatewayApp(
        make_config(),
        provider_factory=lambda spec: FakeProvider("mock", chunks=("ok",), ok=True),
        secret_store=store,
    )
    return app, store


async def test_api_state_her_seyi_dondurur(tmp_path):
    app, _ = _app_with_store(tmp_path)
    async with _client(app) as client:
        d = (await client.get("/api/state")).json()
    assert "providers" in d and "fallback" in d and "health" in d
    assert d["routing"]["current"] == "priority"
    assert "free_first" in d["routing"]["options"]


async def test_api_routing_degistir(tmp_path):
    app, _ = _app_with_store(tmp_path)
    async with _client(app) as client:
        r = await client.post("/api/routing", json={"strategy": "free_first"})
        assert r.json()["strategy"] == "free_first"
        # geçersiz strateji → 400
        assert (await client.post("/api/routing", json={"strategy": "yok"})).status_code == 400


async def test_api_anahtar_kaydet_sifreli_ve_canli(tmp_path, monkeypatch):
    from fusion_cli.config.keys import OPENAI_ENV

    monkeypatch.delenv(OPENAI_ENV, raising=False)
    app, store = _app_with_store(tmp_path)
    async with _client(app) as client:
        r = await client.post("/api/keys", json={"provider": "openai", "value": "sk-yeni"})
    assert r.json()["ok"] is True and r.json()["persisted"] is True
    # Şifreli depoya yazıldı VE canlı ortama uygulandı.
    assert store.get(OPENAI_ENV) == "sk-yeni"
    import os

    assert os.environ.get(OPENAI_ENV) == "sk-yeni"
    monkeypatch.delenv(OPENAI_ENV, raising=False)


async def test_api_anahtar_bilinmeyen_saglayici_400(tmp_path):
    app, _ = _app_with_store(tmp_path)
    async with _client(app) as client:
        r = await client.post("/api/keys", json={"provider": "ollama", "value": "x"})
    assert r.status_code == 400  # yerel: anahtar almaz


async def test_api_fallback_zinciri_duzenle(tmp_path):
    app, _ = _app_with_store(tmp_path)
    async with _client(app) as client:
        r = await client.post("/api/fallback", json={"models": ["p/x", "p/y", "p/z"]})
        d = r.json()
    assert d["ok"] is True
    assert d["chain"] == ["p/x", "p/y", "p/z"]
    # Gateway'in aktif agent zinciri güncellendi.
    assert app._config.agent.model == "p/x"
    assert list(app._config.agent.fallback) == ["p/y", "p/z"]


async def test_api_fallback_strict_secimi_kaydeder(tmp_path):
    app, _ = _app_with_store(tmp_path)
    async with _client(app) as client:
        r = await client.post(
            "/api/fallback",
            json={"models": ["gemini_web/main/auto", "p/y"], "strict": True},
        )
        state = (await client.get("/api/state")).json()

    assert r.json()["strict"] is True
    assert app._config.agent.strict is True
    assert state["strict_model_selection"] is True


async def test_api_fallback_bos_400(tmp_path):
    app, _ = _app_with_store(tmp_path)
    async with _client(app) as client:
        assert (await client.post("/api/fallback", json={"models": []})).status_code == 400
