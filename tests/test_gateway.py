"""Yerel gateway — OpenAI-uyumlu ASGI uç noktası (gerçek sunucu açmadan test).

Sağlayıcı sahte enjekte edilir; ağ yok. `httpx.ASGITransport` uygulamayı doğrudan sürer.
"""

from __future__ import annotations

import json
import re

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


async def test_dashboard_stil_ve_betik_ayri_dosyadan_gelir():
    """Panel tek dosya değildir; stil ve davranış statik varlıklardan yüklenir."""
    async with _client(_app()) as client:
        resp = await client.get("/dashboard")
    assert "<style>" not in resp.text
    assert "/dashboard/static/tokens.css" in resp.text
    assert "/dashboard/static/panel.js" in resp.text


@pytest.mark.parametrize(
    ("name", "content_type"),
    [
        ("tokens.css", "text/css"),
        ("shell.css", "text/css"),
        ("components.css", "text/css"),
        ("surfaces.css", "text/css"),
        ("states.css", "text/css"),
        ("panel.js", "text/javascript"),
        ("web-sessions.js", "text/javascript"),
        ("fonts/inter-latin.woff2", "font/woff2"),
    ],
)
async def test_dashboard_statik_varlik_servis_edilir(name, content_type):
    async with _client(_app()) as client:
        resp = await client.get(f"/dashboard/static/{name}")
    assert resp.status_code == 200
    assert content_type in resp.headers["content-type"]
    assert resp.content


async def test_dashboard_tokenlarinda_marka_ve_font_tanimli():
    """Marka gradyanı ve paketle gelen Inter token dosyasında olmalı."""
    async with _client(_app()) as client:
        resp = await client.get("/dashboard/static/tokens.css")
    assert "--brand-grad" in resp.text
    assert "@font-face" in resp.text
    assert "fonts/inter-latin.woff2" in resp.text


async def test_dashboard_statik_olmayan_dosya_404():
    async with _client(_app()) as client:
        resp = await client.get("/dashboard/static/yok.css")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "name",
    [
        "../dashboard.html",  # bir üst dizine çık
        "../../config/defaults.yaml",  # paketin başka bir katmanına in
        "/etc/hosts",  # mutlak yol
        "fonts/../../app.py",  # alt dizinden geri tırman
        "app.py",  # kök dışında ama uzantısı bilinmiyor
        "",  # dizinin kendisi
    ],
)
def test_statik_varlik_kok_disina_cikamaz(name):
    """Doğrulama HTTP katmanında değil fonksiyonun kendisinde olmalı.

    İstemcinin `..` dizilerini normalleştirmesine güvenilmez; yol çözümlenip
    kökün altında kaldığı doğrudan sınanır.
    """
    from fusion_cli.gateway.app import read_dashboard_asset

    assert read_dashboard_asset(name) is None


def test_statik_varlik_bilinen_uzantiyi_okur():
    from fusion_cli.gateway.app import read_dashboard_asset

    okundu = read_dashboard_asset("fonts/inter-latin-ext.woff2")
    assert okundu is not None
    body, content_type = okundu
    assert content_type == "font/woff2"
    assert body[:4] == b"wOF2"  # woff2 imzası


# --- panel erişilebilirliği (klavye + ekran okuyucu) ----------------------- #


def _varlik(name: str) -> str:
    from fusion_cli.gateway.app import read_dashboard_asset

    okundu = read_dashboard_asset(name)
    assert okundu is not None, name
    return okundu[0].decode("utf-8")


def _dashboard() -> str:
    from fusion_cli.gateway.app import _dashboard_html

    return _dashboard_html()


def test_tiklanabilir_eleman_gercek_dugmedir():
    """`<div onclick>` klavyeyle odaklanamaz ve ekran okuyucuya düğme demez.

    Ölçüldü: panel bu yüzden yalnız uç nokta düğmesine kadar gezilebiliyordu;
    altı gezinme öğesi, kategori çipleri ve 41 sağlayıcı kartı erişilemezdi.
    """
    assert re.search(r"<div[^>]*onclick", _dashboard()) is None
    # Betikle üretilen işaretleme de aynı kurala tabidir. Ölçüt "her kart başlığı
    # düğmedir" değil — tıklanamayan statik kart (adaptör yok / yerel) div kalır.
    # Ölçüt: TIKLANABİLİR hiçbir şey div olamaz.
    for dosya in ("panel.js", "web-sessions.js"):
        assert re.search(r"<div[^>]*onclick", _varlik(dosya)) is None, dosya
    panel_js = _varlik("panel.js")
    assert '<button type="button" class="cat-chip' in panel_js
    assert '<button type="button" class="pcard-head' in panel_js


def test_gezinme_ogeleri_aria_current_tasir():
    govde = _dashboard()
    assert govde.count('<button type="button" class="nav-item') == 6
    # Açılışta yalnız bir öğe geçerli sayfa olarak işaretli olmalı.
    assert govde.count('aria-current="page"') == 1
    # Sınıf ve aria birlikte güncellenmezse kart klavye kullanıcısına yalan söyler.
    assert 't.setAttribute("aria-current", "page")' in _varlik("panel.js")


def test_modal_rol_ve_kapanma_yollari_tanimli():
    govde = _dashboard()
    assert govde.count('role="dialog"') == 2
    assert govde.count('aria-modal="true"') == 2
    assert govde.count("aria-labelledby=") == 2
    web = _varlik("web-sessions.js")
    assert 'e.key !== "Escape"' in web  # Escape kapatır
    assert "e.target === backdrop" in web  # arka plana tıklamak kapatır
    assert "modalOncesiOdak" in web  # odak açan elemana döner


def test_bildirim_ekran_okuyucuya_duyurulur():
    assert 'id="toast" role="status" aria-live="polite"' in _dashboard()


def test_acilir_kapanir_kartlar_aria_expanded_tasir():
    assert 'aria-expanded="false" aria-controls="webAddBody"' in _dashboard()
    assert 'head.setAttribute("aria-expanded", String(open))' in _varlik("panel.js")


def test_odak_ve_devre_disi_stilleri_tanimli():
    """Odak halkası tek yerde; `:focus` değil `:focus-visible` kullanılır."""
    kabuk = _varlik("shell.css")
    assert ":focus-visible" in kabuk
    assert "outline: 2px solid var(--brand-ink)" in kabuk
    bilesen = _varlik("components.css")
    assert "button:disabled" in bilesen
    assert "input:disabled" in bilesen


# --- panel durumları ve hareket -------------------------------------------- #


def test_ilk_boyamada_iskelet_ve_mesgul_isareti_var():
    """Veri gelene kadar "–" göstermek "veri yok" ile aynı görünüyordu.

    İskelet gelecek içeriğin şeklini gösterir; `aria-busy` ekran okuyucuya
    yarı dolu tabloyu okumamasını söyler.
    """
    govde = _dashboard()
    assert '<div class="content" aria-busy="true">' in govde
    assert govde.count("skeleton") >= 7  # dört sayı + üç yapılandırma alanı
    panel_js = _varlik("panel.js")
    # Veri gelince ikisi de kalkar.
    assert 'el.classList.remove("skeleton")' in panel_js
    assert 'setAttribute("aria-busy", "false")' in panel_js


def test_bos_durumlar_tek_bilesenden_uretilir():
    """Her ekranda ayrı bir "veri yok" cümlesi yerine tek bileşen, farklı metin."""
    panel_js = _varlik("panel.js")
    assert "function emptyState(" in panel_js
    assert "function emptyRow(" in panel_js
    # Eski tek satırlık gri metinler kalmamalı.
    assert '<div class="hint">zincir boş</div>' not in panel_js
    assert '<tr><td class="hint">veri yok</td></tr>' not in panel_js
    # Tablo boş durumu tüm sütunlara yayılır; yoksa hizayı bozuyordu.
    assert 'colspan="${cols}"' in panel_js


def test_mesgul_dugme_her_durumda_serbest_birakilir():
    """Hata dönse bile düğme kilitli kalmamalı — `finally` bunu garanti eder."""
    panel_js = _varlik("panel.js")
    assert "async function withBusy(" in panel_js
    govde_baslangic = panel_js.index("async function withBusy(")
    govde_bitis = panel_js.index("\n}", govde_baslangic)
    govde = panel_js[govde_baslangic:govde_bitis]
    assert "finally {" in govde
    assert 'classList.remove("busy")' in govde
    assert "el.disabled = false" in govde


def test_hareket_azaltilinca_sonsuz_animasyonlar_kapanir():
    """Süre token'ları 0'a düşer ama SONSUZ animasyonların süresi token'dan
    gelmez; 0ms'lik sonsuz döngü iskeleti titretirdi. Ayrıca kapatılır."""
    durumlar = _varlik("states.css")
    assert "@media (prefers-reduced-motion: reduce)" in durumlar
    azalt = durumlar[durumlar.index("@media (prefers-reduced-motion: reduce)") :]
    assert ".skeleton" in azalt and "animation: none" in azalt
    assert "button.busy::after" in azalt


def test_hareket_sureleri_token_uzerinden_gelir():
    """Animasyon süresi koda gömülmez; `prefers-reduced-motion` ancak böyle çalışır."""
    durumlar = _varlik("states.css")
    assert "var(--duration-normal)" in durumlar
    assert "var(--duration-fast)" in durumlar


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


# --------------------------------------------------------------------------- #
# Model seçicileri — kullanıcının KENDİ web oturumu seçilebilmeli
# --------------------------------------------------------------------------- #


def test_available_models_web_oturumunu_icerir():
    """Sunucu tarafı: yapılandırılmış web oturumu model listesinde olmalı."""
    from fusion_cli.config.models import WebSessionConfig
    from fusion_cli.gateway.routing import available_models

    from .fakes import make_config

    config = make_config(
        web_sessions=(
            WebSessionConfig(model="gemini_web/yeni/auto", transport="browser", enabled=True),
        )
    )
    assert "gemini_web/yeni/auto" in available_models(config)


def test_available_models_kapali_oturumu_gizler():
    from fusion_cli.config.models import WebSessionConfig
    from fusion_cli.gateway.routing import available_models

    from .fakes import make_config

    config = make_config(
        web_sessions=(
            WebSessionConfig(model="gemini_web/kapali/auto", transport="browser", enabled=False),
        )
    )
    assert "gemini_web/kapali/auto" not in available_models(config)


def _panel_js() -> str:
    from pathlib import Path

    import fusion_cli.gateway as gateway

    return (Path(gateway.__file__).parent / "static" / "panel.js").read_text(encoding="utf-8")


def test_panel_model_seciciler_yerel_modelleri_de_listeler():
    """Ölçülen hata: seçiciler YALNIZCA uzak katalogdan doldurulunca kullanıcının
    panelden eklediği web oturumu hiçbir model seçicisinde görünmüyordu; yalnızca
    Playground'a düşüyor ve baş model / yedek yapılamıyordu."""
    js = _panel_js()

    assert "function localModelOptions" in js, "yerel model seçenekleri üretilmiyor"
    assert "STATE.web_sessions" in js, "web oturumları seçiciye girmiyor"
    # Yerel seçenekler datalist'e YAZILMALI, sadece hesaplanmamalı.
    katalog_bloku = js.split("function renderCatalog")[1].split("\n}")[0]
    assert "localModelOptions()" in katalog_bloku
    assert "catalogList" in katalog_bloku


def test_panel_durum_yenilendiginde_secicileri_tazeler():
    """Yeni eklenen oturum, panel yeniden yüklenmeden seçilebilir olmalı."""
    js = _panel_js()
    render_bloku = js.split("function render()")[1].split("\nfunction ")[0]
    assert "renderCatalog()" in render_bloku
