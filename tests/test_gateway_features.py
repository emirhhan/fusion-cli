"""Gateway ek özellikleri — analytics, önbellek, sıkıştırma, maskeleme, yeni uçlar."""

from __future__ import annotations

import httpx

from fusion_cli.core.compression import compress_messages, compress_text, saved_chars
from fusion_cli.core.routing_strategy import RoutingStrategy, order_models
from fusion_cli.core.types import Message
from fusion_cli.gateway.analytics import Analytics, RequestRecord
from fusion_cli.gateway.app import GatewayApp
from fusion_cli.gateway.cache import PromptCache

from .fakes import FakeProvider, make_config, request


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local")


def _store(tmp_path):
    from fusion_cli.config.credentials import FernetSecretStore

    return FernetSecretStore(tmp_path / "s.enc", secret_key="k")


def _app(tmp_path, reply="cevap", ok=True):
    return GatewayApp(
        make_config(),
        provider_factory=lambda spec: FakeProvider("nvidia_nim/m", chunks=(reply,), ok=ok),
        secret_store=_store(tmp_path),
    )


# --- analytics ------------------------------------------------------------- #


def test_analytics_sayar_ve_ozetler():
    a = Analytics()
    a.record(RequestRecord("auto", "m1", 10, 20, 100, True))
    a.record(RequestRecord("auto", "m1", 5, 5, 300, True, cached=True))
    snap = a.snapshot()
    assert snap["requests"] == 2
    assert snap["total_tokens"] == 40
    assert snap["cache_hits"] == 1
    assert snap["avg_latency_ms"] == 200
    assert snap["per_model"][0]["model"] == "m1"


# --- önbellek -------------------------------------------------------------- #


def test_cache_ayni_istek_hit():
    from fusion_cli.core.types import ModelResult

    cache = PromptCache()
    req = request()
    result = ModelResult(name="m", model="m", text="cevap", latency_ms=1, ok=True)
    assert cache.get("auto", req) is None
    cache.put("auto", req, result)
    assert cache.get("auto", req) is result


def test_cache_arac_cagrisi_onbelleklemez():
    from fusion_cli.core.types import ModelResult, ToolCall

    cache = PromptCache()
    req = request()
    result = ModelResult(
        name="m",
        model="m",
        text="",
        latency_ms=1,
        ok=True,
        tool_calls=(ToolCall(id="1", name="x", arguments="{}"),),
    )
    cache.put("auto", req, result)
    assert cache.get("auto", req) is None  # araç çağrısı önbelleğe girmez


# --- güvenli sıkıştırma ---------------------------------------------------- #


def test_compress_girintiyi_korur():
    kod = "def f():\n    x = 1   \n\n\n\n    return x\n"
    out = compress_text(kod)
    assert "    x = 1\n" in out  # satır sonu boşluğu kırpıldı, girinti korundu
    assert "\n\n\n" not in out  # 3+ boş satır 2'ye indi
    assert "    return x" in out


def test_saved_chars_pozitif():
    before = (Message("user", "a   \n\n\n\nb"),)
    after = compress_messages(before)
    assert saved_chars(before, after) > 0


# --- routing stratejileri (yeni) ------------------------------------------- #


def test_cost_optimized_ucretsizi_one_alir():
    models = ("nvidia_nim/a", "openrouter/b:free")
    assert order_models(models, strategy=RoutingStrategy.COST_OPTIMIZED)[0] == "openrouter/b:free"


def test_latency_saglik_yoksa_priority():
    models = ("a", "b")
    assert order_models(models, strategy=RoutingStrategy.LATENCY, health=None) == models


# --- yeni uçlar ------------------------------------------------------------ #


async def test_api_analytics_ucu(tmp_path):
    async with _client(_app(tmp_path)) as client:
        # bir istek gönder ki telemetri dolsun
        await client.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "x"}]},
        )
        d = (await client.get("/api/analytics")).json()
    assert d["requests"] >= 1


async def test_api_ready_ucu(tmp_path, monkeypatch):
    from fusion_cli.config.keys import OPENROUTER_ENV

    monkeypatch.setenv(OPENROUTER_ENV, "sk-x")
    async with _client(_app(tmp_path)) as client:
        d = (await client.get("/api/ready")).json()
    assert d["ready"] is True and "openrouter" in d["configured_providers"]


async def test_route_candidates_ucu(tmp_path):
    async with _client(_app(tmp_path)) as client:
        d = (await client.get("/v1/route/candidates?model=auto")).json()
    assert "candidates" in d and d["strategy"] == "priority"


async def test_health_reset_ucu(tmp_path):
    async with _client(_app(tmp_path)) as client:
        assert (await client.post("/api/health/reset")).json()["ok"] is True


async def test_config_export_ucu(tmp_path):
    async with _client(_app(tmp_path)) as client:
        d = (await client.get("/api/config/export")).json()
    assert "config" in d


async def test_hakem_modeli_duzenle(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as client:
        r = await client.post("/api/model", json={"role": "judge", "models": ["p/j1", "p/j2"]})
    assert r.json()["ok"] is True
    assert app._config.judge.model == "p/j1"


async def test_onbellek_ikinci_istekte_hit(tmp_path):
    app = _app(tmp_path, reply="önbellekli")
    payload = {"model": "auto", "messages": [{"role": "user", "content": "aynı soru"}]}
    async with _client(app) as client:
        r1 = await client.post("/v1/chat/completions", json=payload)
        r2 = await client.post("/v1/chat/completions", json=payload)
    assert r1.headers["x-fusion-cache"] == "MISS"
    assert r2.headers["x-fusion-cache"] == "HIT"


async def test_maskeleme_yanittaki_siri_gizler(tmp_path):
    # Model yanıtında bir API anahtarı deseni sızarsa maskelenir.
    app = _app(tmp_path, reply="anahtarın sk-abcdef0123456789ABCDEF budur")
    async with _client(app) as client:
        r = await client.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "x"}]},
        )
    content = r.json()["choices"][0]["message"]["content"]
    assert "sk-abcdef0123456789ABCDEF" not in content
