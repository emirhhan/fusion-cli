"""Gateway ek özellikleri — analytics, önbellek, sıkıştırma, maskeleme, yeni uçlar."""

from __future__ import annotations

import os
from dataclasses import replace as _dc_replace

import httpx

from fusion_cli.core.compression import compress_messages, compress_text, saved_chars
from fusion_cli.core.routing_strategy import RoutingStrategy, order_models
from fusion_cli.core.types import Message
from fusion_cli.gateway import app as gateway_app
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


# --- web-session ekleme/silme (panelden kendi ucun) ------------------------ #


async def test_web_session_eklenir_ve_durumda_gorunur(tmp_path, monkeypatch):
    """Panelden eklenen web ucu config'e yazılır ve /api/state'te listelenir."""
    app = _app(tmp_path)
    async with _client(app) as client:
        resp = await client.post(
            "/api/web_sessions",
            json={
                "model": "benim-chat",
                "endpoint": "http://localhost:3000/v1/chat/completions",
                "token": "gizli",
            },
        )
        assert resp.json()["ok"] is True
        state = (await client.get("/api/state")).json()

    models = [s["model"] for s in state["web_sessions"]]
    assert "benim-chat" in models
    # Token model adından türetilen env değişkenine CANLI yazılır (API anahtarı gibi).
    import os

    assert os.environ.get("FUSION_WEB_BENIM_CHAT") == "gizli"


async def test_web_session_endpoint_dogrulanir(tmp_path):
    async with _client(_app(tmp_path)) as client:
        resp = await client.post(
            "/api/web_sessions", json={"model": "x", "endpoint": "ftp://kotu"}
        )
    assert resp.status_code == 400
    assert "http" in resp.json()["error"]["message"]


async def test_web_session_model_zorunlu(tmp_path):
    async with _client(_app(tmp_path)) as client:
        resp = await client.post("/api/web_sessions", json={"endpoint": "http://x/v1"})
    assert resp.status_code == 400


async def test_web_session_silinir(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as client:
        await client.post(
            "/api/web_sessions", json={"model": "sil-beni", "endpoint": "http://x/v1"}
        )
        resp = await client.post("/api/web_sessions/delete", json={"model": "sil-beni"})
        assert resp.json()["ok"] is True
        state = (await client.get("/api/state")).json()

    assert "sil-beni" not in [s["model"] for s in state["web_sessions"]]


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


# --- model kataloğu (otomatik listeleme) ---------------------------------- #


def test_catalog_aggregate_tekiller_ve_ucretsizi_isaretler():
    from fusion_cli.gateway.catalog_cache import CatalogModel, aggregate
    from fusion_cli.providers.catalog import CatalogEntry

    def free():
        return (CatalogEntry("openrouter/a:free", "openrouter", 128000),)

    def paid():
        return (
            CatalogEntry("openrouter/b", "openrouter", 200000),
            CatalogEntry("openrouter/a:free", "openrouter", 128000),  # çift kayıt
        )

    out = aggregate(sources=((True, free), (False, paid)))
    assert [m.id for m in out] == ["openrouter/a:free", "openrouter/b"]  # sıralı + tekil
    ucretsiz = next(m for m in out if m.id == "openrouter/a:free")
    assert isinstance(ucretsiz, CatalogModel) and ucretsiz.free is True


def test_catalog_cache_ttl_ve_zorla_tazele():
    from fusion_cli.gateway.catalog_cache import CatalogCache, CatalogModel

    calls = {"n": 0}
    now = {"t": 1000.0}

    def agg():
        calls["n"] += 1
        return (CatalogModel("p/x", "p", True, 0),)

    cache = CatalogCache(aggregator=agg, ttl_s=300.0, clock=lambda: now["t"])
    cache.get()
    cache.get()  # TTL içinde: tek çekim
    assert calls["n"] == 1
    now["t"] += 301
    cache.get()  # TTL doldu: yeniden çekilir
    assert calls["n"] == 2
    cache.get(refresh=True)  # zorla tazele
    assert calls["n"] == 3


async def test_api_models_catalog_ucu(tmp_path):
    from fusion_cli.gateway.catalog_cache import CatalogCache, CatalogModel

    cache = CatalogCache(
        aggregator=lambda: (CatalogModel("openrouter/x:free", "openrouter", True, 128000),)
    )
    app = GatewayApp(
        make_config(),
        provider_factory=lambda spec: FakeProvider("nvidia_nim/m", chunks=("x",)),
        secret_store=_store(tmp_path),
        catalog=cache,
    )
    async with _client(app) as client:
        d = (await client.get("/api/models/catalog")).json()
    assert d["count"] == 1
    assert d["models"][0]["id"] == "openrouter/x:free" and d["models"][0]["free"] is True


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

# --- native web subscriptions --------------------------------------------- #


async def test_native_web_session_cookie_sifreli_kaydedilir_ve_model_listesine_girer(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    monkeypatch.setattr(
        "fusion_cli.config.writer.user_config_candidates", lambda: (tmp_path / "config.yaml",)
    )
    monkeypatch.setattr(
        "fusion_cli.config.writer.user_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr(
        "fusion_cli.providers.web_browser.user_data_dir", lambda: tmp_path / "data"
    )
    app = _app(tmp_path)
    app._config = replace(app._config, source=tmp_path / "config.yaml")
    async with _client(app) as client:
        response = await client.post(
            "/api/web_sessions",
            json={
                "provider": "chatgpt_web",
                "account": "main",
                "model": "chatgpt_web/main/auto",
                "cookie": "session=very-secret",
                "headless": True,
                "tool_support": "emulated",
            },
        )
        assert response.status_code == 200, response.text
        state = (await client.get("/api/state")).json()
        models = (await client.get("/v1/models")).json()

    session = next(item for item in state["web_sessions"] if item["provider"] == "chatgpt_web")
    assert session["secret_saved"] is True
    assert session["connected"] is True
    assert "chatgpt_web/main/auto" in {item["id"] for item in models["data"]}
    encrypted_path = tmp_path / "s.enc"
    encrypted = encrypted_path.read_bytes()
    assert b"very-secret" not in encrypted
    if os.name == "posix":
        assert encrypted_path.stat().st_mode & 0o077 == 0
    config_text = (tmp_path / "config.yaml").read_text()
    assert "very-secret" not in config_text
    assert "WEB_SECRET::chatgpt_web::main" in config_text


async def test_api_ready_native_web_oturumuyla_true(tmp_path):
    from dataclasses import replace

    from fusion_cli.config.models import WebSessionConfig

    app = _app(tmp_path)
    app._config = replace(
        app._config,
        web_sessions=(
            WebSessionConfig(
                model="claude_web/main/auto",
                provider="claude_web",
                transport="browser",
                account="main",
                tool_support="emulated",
            ),
        ),
    )
    async with _client(app) as client:
        data = (await client.get("/api/ready")).json()
    assert data["ready"] is True
    assert "claude_web" in data["configured_providers"]


# --- Giriş penceresi yoklaması ---------------------------------------------- #
#
# Panel bu uç noktayı yoklar: kullanıcı giriş penceresini kapattığı anda bağlantı
# testi kendiliğinden çalışır. Böylece cookie'yi elle kopyalamak gerekmez.


async def test_giris_penceresi_yasayan_sureci_calisiyor_bildirir(tmp_path):
    async with _client(_app(tmp_path)) as client:
        resp = await client.post("/api/web_sessions/login_state", json={"pid": os.getpid()})

    assert resp.status_code == 200
    assert resp.json()["running"] is True


async def test_giris_penceresi_kapandiginda_bitti_bildirir(tmp_path, monkeypatch):
    def _yok(pid, signal):
        raise ProcessLookupError

    monkeypatch.setattr(gateway_app.os, "kill", _yok)
    async with _client(_app(tmp_path)) as client:
        resp = await client.post("/api/web_sessions/login_state", json={"pid": 424242})

    assert resp.json()["running"] is False


async def test_gecersiz_surec_kimligi_reddedilir(tmp_path):
    async with _client(_app(tmp_path)) as client:
        resp = await client.post("/api/web_sessions/login_state", json={"pid": 0})

    assert resp.status_code == 400


# --- Ölçüm sonucu kayıt sırasında korunur ------------------------------------- #
#
# Gerçek kullanım: kullanıcı araç yeteneği ölçümünü geçti, sonra panelde başka bir
# düğmeye bastı ve model sessizce salt-okunur kipe döndü. Sebep: oturum kaydı
# `tool_eval_passed` alanını taşımıyor, varsayılan False'a düşürüyordu.


async def test_oturum_yeniden_kaydedilince_olcum_silinmez(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as client:
        await client.post(
            "/api/web_sessions",
            json={"provider": "gemini_web", "account": "test", "tool_support": "emulated"},
        )
        # Ölçüm geçmiş gibi işaretle (gerçek ölçüm ağ ister).
        app._config = _dc_replace(
            app._config,
            web_sessions=tuple(
                _dc_replace(s, tool_eval_passed=True) for s in app._config.web_sessions
            ),
        )
        # Kullanıcı panelde başka bir düğmeye basıyor → oturum yeniden kaydediliyor.
        await client.post(
            "/api/web_sessions",
            json={"provider": "gemini_web", "account": "test", "tool_support": "emulated"},
        )

    oturum = next(s for s in app._config.web_sessions if s.account == "test")
    assert oturum.tool_eval_passed is True


async def test_arac_destegi_degisirse_olcum_tasinmaz(tmp_path):
    """Ölçüm o kipe özgüdür; araç desteği değişince yeniden ölçülmelidir."""
    app = _app(tmp_path)
    async with _client(app) as client:
        await client.post(
            "/api/web_sessions",
            json={"provider": "gemini_web", "account": "test", "tool_support": "emulated"},
        )
        app._config = _dc_replace(
            app._config,
            web_sessions=tuple(
                _dc_replace(s, tool_eval_passed=True) for s in app._config.web_sessions
            ),
        )
        await client.post(
            "/api/web_sessions",
            json={"provider": "gemini_web", "account": "test", "tool_support": "none"},
        )

    oturum = next(s for s in app._config.web_sessions if s.account == "test")
    assert oturum.tool_eval_passed is False
