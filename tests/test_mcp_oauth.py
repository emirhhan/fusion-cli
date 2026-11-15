from __future__ import annotations

import httpx
import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge.oauth import (
    LoopbackOAuthCallback,
    McpBrowserOpenError,
    validate_remote_mcp_url,
)
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


async def _get(url: str) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.get(url)


async def test_yabanci_istek_giris_akisini_dusurmez() -> None:
    """Ölçüldü (30 Ekim): `/` ya da `code`suz herhangi bir istek (başka sekme, tarayıcı
    ön-yükleyicisi, kötü niyetli `fetch`) akışı `RuntimeError` ile bitiriyordu."""
    callback = LoopbackOAuthCallback(timeout_seconds=5)
    await callback.start()
    base = callback.redirect_uri.removesuffix("/oauth/callback")

    stray = await _get(f"{base}/")
    no_code = await _get(f"{base}/oauth/callback")
    real = await _get(f"{callback.redirect_uri}?code=abc&state=s")
    code, state = await callback.wait_for_code()

    assert stray.status_code == 404
    assert no_code.status_code == 404
    assert real.status_code == 200
    assert (code, state) == ("abc", "s")


async def test_beklenen_state_ile_eslesmeyen_donus_yok_sayilir(monkeypatch) -> None:
    callback = LoopbackOAuthCallback(timeout_seconds=5)
    monkeypatch.setattr("fusion_cli.mcp_bridge.oauth.webbrowser.open", lambda *a, **k: True)
    await callback.open_redirect("https://auth.example.com/authorize?state=dogru&x=1")

    sahte = await _get(f"{callback.redirect_uri}?code=sahte&state=yanlis")
    hata = await _get(f"{callback.redirect_uri}?error=access_denied&state=yanlis")
    gercek = await _get(f"{callback.redirect_uri}?code=iyi&state=dogru")
    code, state = await callback.wait_for_code()

    assert sahte.status_code == 400
    assert hata.status_code == 400
    assert gercek.status_code == 200
    assert (code, state) == ("iyi", "dogru")


async def test_tarayici_acilamazsa_bekleme_yerine_adresli_hata_verir(monkeypatch) -> None:
    """Ölçüldü (30 Ekim): `webbrowser.open` False dönse de bağlantı süresi askıya
    alınıp 300 sn beklenir, yetkilendirme adresi hiçbir yerde görünmezdi."""
    waiting: list[bool] = []
    callback = LoopbackOAuthCallback(timeout_seconds=5, on_waiting=waiting.append)
    monkeypatch.setattr("fusion_cli.mcp_bridge.oauth.webbrowser.open", lambda *a, **k: False)

    with pytest.raises(McpBrowserOpenError, match=r"https://auth\.example\.com/authorize"):
        await callback.open_redirect("https://auth.example.com/authorize?state=s")

    assert waiting == []
    assert callback._server is None  # dinleyici sızdırılmaz
