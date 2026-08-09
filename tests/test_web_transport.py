"""Genel web-session transport — OpenAI-uyumlu uca istek ve yanıt ayrıştırma."""

from __future__ import annotations

import httpx
import pytest

from fusion_cli.core.types import Message
from fusion_cli.providers.web_session import WebSessionCredential
from fusion_cli.providers.web_transport import build_http_transport


def _handler(capture: dict) -> httpx.MockTransport:
    """İsteği yakalayıp sabit bir OpenAI-uyumlu yanıt döndüren sahte httpx transport."""

    def _respond(request: httpx.Request) -> httpx.Response:
        capture["url"] = str(request.url)
        capture["auth"] = request.headers.get("authorization")
        capture["cookie"] = request.headers.get("cookie")
        capture["x-test"] = request.headers.get("x-test")
        import json

        capture["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "merhaba dünya"}}]})

    return httpx.MockTransport(_respond)


async def test_transport_yaniti_metin_olarak_doner():
    capture: dict = {}
    transport = build_http_transport(
        "https://uc.example/v1/chat/completions", http_transport=_handler(capture)
    )
    cred = WebSessionCredential(token="gizli-token")

    metin = await transport(cred, (Message("user", "selam"),), "benim-modelim")

    assert metin.text == "merhaba dünya"


async def test_bearer_token_ve_model_gonderilir():
    capture: dict = {}
    transport = build_http_transport(
        "https://uc.example/v1/chat/completions", http_transport=_handler(capture)
    )
    cred = WebSessionCredential(token="gizli-token")

    await transport(cred, (Message("user", "selam"),), "benim-modelim")

    assert capture["auth"] == "Bearer gizli-token"
    assert capture["body"]["model"] == "benim-modelim"
    assert capture["body"]["messages"] == [{"role": "user", "content": "selam"}]


async def test_cookies_ve_ozel_basliklar_iletilir():
    capture: dict = {}
    transport = build_http_transport(
        "https://uc.example/v1/chat/completions", http_transport=_handler(capture)
    )
    cred = WebSessionCredential(token="", cookies={"session": "abc"}, headers={"x-test": "deger"})

    await transport(cred, (Message("user", "selam"),), "m")

    assert "session=abc" in (capture["cookie"] or "")
    assert capture["x-test"] == "deger"
    # Token boşsa Authorization başlığı hiç eklenmez.
    assert capture["auth"] is None


async def test_hata_kodunda_anlasilir_istisna_firlatir():
    def _fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "oturum süresi doldu"}})

    transport = build_http_transport(
        "https://uc.example/v1/chat/completions", http_transport=httpx.MockTransport(_fail)
    )

    with pytest.raises(Exception) as err:
        await transport(WebSessionCredential(token="x"), (Message("user", "s"),), "m")
    assert "401" in str(err.value)
