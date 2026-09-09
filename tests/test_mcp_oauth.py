from __future__ import annotations

import httpx
import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge.oauth import LoopbackOAuthCallback, validate_remote_mcp_url
from fusion_cli.mcp_bridge.tokens import KeyringTokenStorage


class MemoryKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))

    def set_password(self, service: str, account: str, value: str) -> None:
        self.values[(service, account)] = value

    def delete_password(self, service: str, account: str) -> None:
        self.values.pop((service, account), None)


async def test_oauth_tokenlari_keyringde_round_trip_yapar() -> None:
    backend = MemoryKeyring()
    storage = KeyringTokenStorage("https://mcp.example.com/mcp", backend=backend)
    tokens = OAuthToken(access_token="secret-access", refresh_token="secret-refresh")
    client = OAuthClientInformationFull(
        redirect_uris=["http://127.0.0.1:43123/oauth/callback"], client_id="fusion"
    )

    await storage.set_tokens(tokens)
    await storage.set_client_info(client)

    assert await storage.get_tokens() == tokens
    assert await storage.get_client_info() == client
    assert "secret-access" not in " ".join(account for _, account in backend.values)

    await storage.clear()
    assert await storage.get_tokens() is None
    assert await storage.get_client_info() is None


async def test_loopback_callback_code_ve_state_dondurur() -> None:
    callback = LoopbackOAuthCallback(timeout_seconds=2)
    await callback.start()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{callback.redirect_uri}?code=abc&state=expected")
    code, state = await callback.wait_for_code()

    assert response.status_code == 200
    assert code == "abc"
    assert state == "expected"
    assert "Fusion" in response.text


async def test_loopback_callback_oauth_hatasini_acikca_dondurur() -> None:
    callback = LoopbackOAuthCallback(timeout_seconds=2)
    await callback.start()

    async with httpx.AsyncClient() as client:
        await client.get(f"{callback.redirect_uri}?error=access_denied&state=x")

    with pytest.raises(RuntimeError, match="reddedildi"):
        await callback.wait_for_code()


def test_http_mcp_yalniz_https_ve_loopback_plain_http_kabul_eder() -> None:
    validate_remote_mcp_url("https://mcp.example.com/mcp")
    validate_remote_mcp_url("http://127.0.0.1:8765/mcp")
    validate_remote_mcp_url("http://localhost:8765/mcp")

    with pytest.raises(ValueError, match="HTTPS"):
        validate_remote_mcp_url("http://mcp.example.com/mcp")


def test_oauth_yapilandirmasinda_token_alani_yoktur() -> None:
    config = McpServerConfig(
        name="meta",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.example.com/mcp",
    )

    assert not hasattr(config, "access_token")
    assert not hasattr(config, "refresh_token")
