"""Gateway rota paritesi (P-074): `/v1/responses`, `/v1/messages`, `/v1/embeddings`.

Ölçüldü (31 Ekim): gateway yalnız `/v1/chat/completions` ve `/v1/models` sunuyordu; Codex
(Responses) ve Claude SDK (Messages) istemcileri 404 alıyordu.
"""

from __future__ import annotations

import json

import httpx

from fusion_cli.core.types import ModelResult, TokenUsage, ToolCall
from fusion_cli.gateway import embeddings as gomme
from fusion_cli.gateway import translate_anthropic as anthropic
from fusion_cli.gateway import translate_responses as responses
from fusion_cli.gateway.app import GatewayApp

from .fakes import FakeProvider, make_config


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost")


def _app(reply="Selam!", ok=True):
    config = make_config()
    return GatewayApp(
        config, provider_factory=lambda spec: FakeProvider("mock", chunks=(reply,), ok=ok)
    )


def _events(text: str) -> list[tuple[str, dict]]:
    olaylar = []
    for blok in text.strip().split("\n\n"):
        satirlar = dict(
            satir.split(": ", 1)
            for satir in blok.splitlines()
            if ": " in satir and not satir.startswith("data: [DONE]")
        )
        if "event" in satirlar and "data" in satirlar:
            olaylar.append((satirlar["event"], json.loads(satirlar["data"])))
    return olaylar


# --- Responses ---------------------------------------------------------------------------- #


def test_responses_istegi_input_ve_instructions_cevrilir():
    runtime = make_config().runtime
    request, model, stream = responses.to_request(
        {
            "model": "auto",
            "instructions": "Kısa yaz.",
            "input": [
                {"role": "user", "content": [{"type": "input_text", "text": "merhaba"}]},
                {"type": "function_call", "call_id": "c1", "name": "oku", "arguments": "{}"},
                {"type": "function_call_output", "call_id": "c1", "output": "dosya içeriği"},
            ],
            "tools": [{"type": "function", "name": "oku", "parameters": {"type": "object"}}],
        },
        runtime,
    )

    assert (model, stream) == ("auto", False)
    assert [m.role for m in request.messages] == ["system", "user", "assistant", "tool"]
    assert request.messages[2].tool_calls[0].name == "oku"
    assert request.messages[3].tool_call_id == "c1"
    assert request.tools[0]["function"]["name"] == "oku"


async def test_responses_rotasi_output_text_doner():
    async with _client(_app("Selam!")) as client:
        resp = await client.post("/v1/responses", json={"model": "auto", "input": "merhaba"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["object"] == "response" and body["status"] == "completed"
    assert body["output"][0]["content"][0]["text"] == "Selam!"
    assert body["output_text"] == "Selam!"
    assert resp.headers["x-fusion-route"].endswith("mock") or resp.headers["x-fusion-route"]


async def test_responses_input_zorunlu():
    async with _client(_app()) as client:
        resp = await client.post("/v1/responses", json={"model": "auto"})
    assert resp.status_code == 400 and "input" in resp.json()["error"]["message"]


async def test_responses_akisi_delta_ve_completed_olaylari():
    async with _client(_app("Selam!")) as client:
        resp = await client.post(
            "/v1/responses", json={"model": "auto", "input": "merhaba", "stream": True}
        )

    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
    olaylar = _events(resp.text)
    adlar = [ad for ad, _ in olaylar]
    assert adlar[0] == "response.created" and adlar[-1] == "response.completed"
    assert "response.output_text.delta" in adlar and "response.output_text.done" in adlar
    delta = next(veri for ad, veri in olaylar if ad == "response.output_text.delta")
    assert delta["delta"] == "Selam!" and delta["type"] == "response.output_text.delta"
    assert resp.text.rstrip().endswith("data: [DONE]")


def test_responses_arac_cagrisi_function_call_ogesi_olur():
    sonuc = ModelResult(
        name="m",
        model="m",
        text="",
        latency_ms=1,
        ok=True,
        tool_calls=(ToolCall(id="c1", name="oku", arguments='{"yol": "a"}'),),
    )
    body = responses.to_response(sonuc, "auto")
    assert body["output"][0]["type"] == "function_call"
    assert body["output"][0]["call_id"] == "c1" and body["output"][0]["name"] == "oku"


# --- Anthropic Messages ------------------------------------------------------------------- #


def test_messages_istegi_system_tool_use_ve_tool_result_cevrilir():
    request, model, stream = anthropic.to_request(
        {
            "model": "auto",
            "max_tokens": 64,
            "system": [{"type": "text", "text": "Türkçe konuş."}],
            "messages": [
                {"role": "user", "content": "dosyayı oku"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "oku", "input": {"yol": "a"}}
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "içerik"}],
                },
            ],
            "tools": [{"name": "oku", "description": "okur", "input_schema": {"type": "object"}}],
        },
        make_config().runtime,
    )

    assert request.max_tokens == 64 and model == "auto" and stream is False
    assert [m.role for m in request.messages] == ["system", "user", "assistant", "tool"]
    assert json.loads(request.messages[2].tool_calls[0].arguments) == {"yol": "a"}
    assert request.messages[3].tool_call_id == "t1" and request.messages[3].content == "içerik"
    assert request.tools[0]["function"]["parameters"] == {"type": "object"}


async def test_messages_rotasi_anthropic_mesaji_doner():
    async with _client(_app("Selam!")) as client:
        resp = await client.post(
            "/v1/messages",
            json={
                "model": "auto",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "hey"}],
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"] == "message" and body["role"] == "assistant"
    assert body["content"] == [{"type": "text", "text": "Selam!"}]
    assert body["stop_reason"] == "end_turn" and "input_tokens" in body["usage"]


async def test_messages_hatasi_anthropic_zarfinda():
    async with _client(_app()) as client:
        resp = await client.post("/v1/messages", json={"model": "auto", "messages": []})
    assert resp.status_code == 400
    assert (
        resp.json()["type"] == "error" and resp.json()["error"]["type"] == "invalid_request_error"
    )


async def test_messages_basarisiz_model_502_api_error():
    async with _client(_app("", ok=False)) as client:
        resp = await client.post(
            "/v1/messages", json={"model": "auto", "messages": [{"role": "user", "content": "x"}]}
        )
    assert resp.status_code == 502 and resp.json()["error"]["type"] == "api_error"


async def test_messages_akisi_anthropic_olay_sirasi():
    async with _client(_app("Selam!")) as client:
        resp = await client.post(
            "/v1/messages",
            json={"model": "auto", "messages": [{"role": "user", "content": "x"}], "stream": True},
        )

    adlar = [ad for ad, _ in _events(resp.text)]
    assert adlar == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    delta = next(veri for ad, veri in _events(resp.text) if ad == "content_block_delta")
    assert delta["delta"] == {"type": "text_delta", "text": "Selam!"}


def test_messages_arac_cagrisi_tool_use_blogu_olur():
    sonuc = ModelResult(
        name="m",
        model="m",
        text="bakıyorum",
        latency_ms=1,
        ok=True,
        usage=TokenUsage(prompt_tokens=3, completion_tokens=2),
        tool_calls=(ToolCall(id="t1", name="oku", arguments='{"yol": "a"}'),),
    )
    body = anthropic.to_message(sonuc, "auto")
    assert body["stop_reason"] == "tool_use"
    assert body["content"][1] == {
        "type": "tool_use",
        "id": "t1",
        "name": "oku",
        "input": {"yol": "a"},
    }
    assert body["usage"] == {"input_tokens": 3, "output_tokens": 2}


# --- Embeddings --------------------------------------------------------------------------- #


def test_embeddings_girdi_dogrulamasi():
    assert gomme.parse_inputs({"input": "a"}) == (["a"], "")
    assert gomme.parse_inputs({"input": ["a", "b"], "model": "x"}) == (["a", "b"], "x")
    for kotu in ({"input": []}, {"input": [1]}, {"input": "  "}, {}):
        try:
            gomme.parse_inputs(kotu)
        except Exception as error:
            assert "input" in str(error)
        else:
            raise AssertionError(kotu)


async def test_embeddings_rotasi_openai_zarfi_doner(monkeypatch):
    monkeypatch.setattr(
        gomme, "build_embedder", lambda config: (lambda texts: [[0.1, 0.2] for _ in texts], "sahte")
    )
    async with _client(_app()) as client:
        resp = await client.post("/v1/embeddings", json={"input": ["a", "b"]})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["object"] == "list" and body["model"] == "sahte"
    assert [d["index"] for d in body["data"]] == [0, 1] and body["data"][1]["embedding"] == [
        0.1,
        0.2,
    ]


async def test_embeddings_saglayici_yoksa_501(monkeypatch):
    def _yok(config):
        raise gomme.EmbeddingUnavailableError("yerel gömme yok")

    monkeypatch.setattr(gomme, "build_embedder", _yok)
    async with _client(_app()) as client:
        resp = await client.post("/v1/embeddings", json={"input": "a"})
    assert resp.status_code == 501 and "gömme" in resp.json()["error"]["message"]


async def test_chat_rotasi_hala_calisir():
    async with _client(_app("Selam!")) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "auto", "messages": [{"role": "user", "content": "x"}]},
        )
    assert resp.status_code == 200 and resp.json()["object"] == "chat.completion"


# --- 31 Ekim inceleme bulguları ----------------------------------------------------------- #


def test_messages_karma_metin_ve_tool_result_sirasi_arac_once():
    """Ölçüldü (31 Ekim): aynı kullanıcı mesajında text + tool_result varsa metin araç
    sonucundan ÖNCE geliyordu; OpenAI uyumlu sağlayıcılar tool_calls'tan hemen sonra tool
    mesajı bekler (400 'tool_call_id ... did not have response')."""
    request, _, _ = anthropic.to_request(
        {
            "model": "auto",
            "messages": [
                {"role": "user", "content": "oku"},
                {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "t1", "name": "oku", "input": {}}],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "<system-reminder>…</system-reminder>"},
                        {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
                    ],
                },
            ],
        },
        make_config().runtime,
    )

    assert [m.role for m in request.messages] == ["user", "assistant", "tool", "user"]
    assert request.messages[2].tool_call_id == "t1"
    assert "system-reminder" in request.messages[3].content


async def test_messages_count_tokens_tahmini_doner():
    async with _client(_app()) as client:
        resp = await client.post(
            "/v1/messages/count_tokens",
            json={"model": "auto", "messages": [{"role": "user", "content": "a" * 400}]},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["input_tokens"] >= 90


async def test_uzak_istemci_x_api_key_ile_messages_rotasina_girer():
    """Anthropic SDK ANTHROPIC_API_KEY'i `x-api-key` başlığıyla gönderir; Bearer değil."""
    config = make_config()
    app = GatewayApp(
        config,
        provider_factory=lambda spec: FakeProvider("mock", chunks=("Selam!",)),
        access_token="gizli-belirtec",
    )
    transport = httpx.ASGITransport(app=app, client=("192.168.1.50", 50123))
    govde = {"model": "auto", "max_tokens": 8, "messages": [{"role": "user", "content": "x"}]}
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        kabul = await client.post(
            "/v1/messages", json=govde, headers={"x-api-key": "gizli-belirtec"}
        )
        ret = await client.post("/v1/messages", json=govde, headers={"x-api-key": "yanlis"})
        bos = await client.post("/v1/messages", json=govde)

    assert kabul.status_code == 200, kabul.text
    assert ret.status_code == 401 and bos.status_code == 401


async def test_responses_basarisiz_model_502_ve_hata_maskeli():
    """Akışsız yol hatayı maskesiz ve 200 ile dönüyordu; akışlı yol ve /v1/messages maskeliydi."""
    sir = "ghp_" + "A" * 36
    app = GatewayApp(
        make_config(),
        provider_factory=lambda spec: FakeProvider(
            "mock", chunks=(), ok=False, error=f"yetki: {sir}"
        ),
    )
    async with _client(app) as client:
        resp = await client.post("/v1/responses", json={"model": "auto", "input": "x"})

    assert resp.status_code == 502, resp.text
    assert resp.json()["status"] == "failed" and sir not in resp.text


def test_responses_developer_rolu_sisteme_eslenir_ve_desteklenmeyen_arac_400():
    request, _, _ = responses.to_request(
        {
            "model": "auto",
            "input": [
                {"role": "developer", "content": "Türkçe yaz."},
                {"role": "user", "content": "selam"},
            ],
        },
        make_config().runtime,
    )
    assert [m.role for m in request.messages] == ["system", "user"]

    try:
        responses.to_request(
            {"model": "auto", "input": "x", "tools": [{"type": "local_shell"}]},
            make_config().runtime,
        )
    except Exception as error:
        assert "local_shell" in str(error)
    else:
        raise AssertionError("desteklenmeyen araç türü sessizce düştü")


async def test_embeddings_gomme_islevi_onbellege_alinir_ve_base64_destegi(monkeypatch):
    kurulum = {"sayi": 0}

    def _kur(config):
        kurulum["sayi"] += 1
        return (lambda texts: [[0.5, -1.0] for _ in texts]), "sahte"

    monkeypatch.setattr(gomme, "build_embedder", _kur)
    async with _client(_app()) as client:
        ilk = await client.post("/v1/embeddings", json={"input": "a"})
        b64 = await client.post("/v1/embeddings", json={"input": "a", "encoding_format": "base64"})

    assert ilk.status_code == b64.status_code == 200
    assert kurulum["sayi"] == 1, "gömme işlevi her istekte yeniden kuruluyor"
    import base64
    import struct

    ham = base64.b64decode(b64.json()["data"][0]["embedding"])
    assert struct.unpack("<2f", ham) == (0.5, -1.0)


async def test_embeddings_parti_ve_uzunluk_siniri_400(monkeypatch):
    monkeypatch.setattr(
        gomme, "build_embedder", lambda config: ((lambda t: [[0.0] for _ in t]), "s")
    )
    async with _client(_app()) as client:
        cok = await client.post("/v1/embeddings", json={"input": ["a"] * (gomme.MAX_BATCH + 1)})
        uzun = await client.post(
            "/v1/embeddings", json={"input": "a" * (gomme.MAX_TOTAL_CHARS + 1)}
        )

    assert cok.status_code == 400 and uzun.status_code == 400
