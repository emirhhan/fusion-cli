"""Canlı ses bağlantısı sırları arayüze taşımaz, onaysız ücretli çağrı yapmaz."""

from __future__ import annotations

import json

import httpx
import pytest

from fusion_cli.providers.live_voice import LiveVoiceProvider


async def test_no_consent_or_missing_key_never_calls_network():
    def reject(request):
        pytest.fail("Onaysız veya anahtarsız çağrı ağa çıkamaz")

    provider = LiveVoiceProvider(transport=httpx.MockTransport(reject))
    assert not (await provider.connect("v=0\r\n", "key", consent=False)).ok
    assert not (await provider.connect("v=0\r\n", "", consent=True)).ok


async def test_webrtc_uses_client_delegation_and_returns_no_credentials():
    def respond(request):
        assert request.url == "https://api.openai.com/v1/live/sessions"
        body = json.loads(request.content)
        assert body["session"]["delegation"] == {"type": "client"}
        assert body["session"]["model"] == "gpt-live-1"
        assert body["transport"] == {"type": "webrtc", "sdp": "v=0\r\n"}
        assert request.headers["Authorization"] == "Bearer test-only-secret"
        return httpx.Response(
            201, json={"session": {"id": "opaque_id"}, "transport": {"sdp": "v=0\r\nanswer"}}
        )

    provider = LiveVoiceProvider(transport=httpx.MockTransport(respond))
    result = await provider.connect("v=0\r\n", "test-only-secret", consent=True)
    assert result.ok and result.session_id == "opaque_id" and result.sdp.endswith("answer")
    assert "test-only-secret" not in repr(result)


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_provider_errors_do_not_echo_secrets_or_raw_body(status):
    provider = LiveVoiceProvider(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status, text="secret-provider-body")
        )
    )
    result = await provider.connect("v=0\r\n", "key", consent=True)
    assert not result.ok and result.message
    assert "secret-provider-body" not in repr(result)


async def test_malformed_sdp_is_rejected_before_network():
    provider = LiveVoiceProvider(
        transport=httpx.MockTransport(lambda request: pytest.fail("Geçersiz teklif gönderildi"))
    )
    assert not (await provider.connect("https://elsewhere", "key", consent=True)).ok


async def test_network_timeout_returns_safe_recoverable_message():
    def timeout(request):
        raise httpx.ReadTimeout("test-only-secret", request=request)

    provider = LiveVoiceProvider(transport=httpx.MockTransport(timeout))
    result = await provider.connect("v=0\r\n", "key", consent=True)
    assert not result.ok
    assert "test-only-secret" not in result.message


@pytest.mark.parametrize("payload", [{}, [], {"session": {"id": "x"}, "transport": {"sdp": 12}}])
async def test_invalid_success_payload_is_not_accepted(payload):
    provider = LiveVoiceProvider(
        transport=httpx.MockTransport(lambda request: httpx.Response(201, json=payload))
    )
    assert not (await provider.connect("v=0\r\n", "key", consent=True)).ok
