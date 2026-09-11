"""Uzak MCP sunucusuna statik erişim token'ı ile bağlanma.

Neden gerekli — ölçülmüş bir engel: Meta'nın barındırdığı MCP (mcp.facebook.com/ads)
dinamik istemci kaydını reddediyor, yani OAuth akışı client_id olmadan hiç başlamıyor.
Aynı sunucunun metadatası `bearer_methods_supported: ["header"]` diyor: hazır bir
token başlıkla kabul ediliyor. Token yolu OAuth'u tamamen atlar — giriş penceresi,
client_id ve her tura eklenen OAuth gecikmesi ortadan kalkar.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from fusion_cli.appserver.connectors import add_connector
from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge import client as client_module
from fusion_cli.mcp_bridge import transport as transport_module
from fusion_cli.mcp_bridge.client import McpClient
from tests.fakes import make_config

TOKEN_ENV = "FUSION_MCP_TOKEN_META_ADS"


def _remote(**extra: object) -> McpServerConfig:
    return McpServerConfig(
        name="Meta Ads",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.example.com/ads",
        **extra,  # type: ignore[arg-type]
    )


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def initialize(self) -> None:
        return None


async def test_token_ortami_authorization_basligina_donusur(monkeypatch):
    """Token yalnız ortamda durur; isteğe `Authorization: Bearer` olarak girer."""
    kaydedilen: dict[str, object] = {}

    @asynccontextmanager
    async def fake_http(url, headers=None, **kwargs) -> AsyncIterator[tuple[None, None, None]]:
        kaydedilen["url"] = url
        kaydedilen["headers"] = headers
        yield None, None, None

    monkeypatch.setattr(transport_module, "streamablehttp_client", fake_http)
    monkeypatch.setenv(TOKEN_ENV, "gizli-token")

    async with transport_module.open_mcp_stream(_remote(token_env=TOKEN_ENV)):
        pass

    assert kaydedilen["headers"] == {"Authorization": "Bearer gizli-token"}


async def test_token_ortamda_yoksa_anlasilir_hata(monkeypatch):
    """Sessizce kimliksiz bağlanmak 401'i anlaşılmaz bir başlatma hatasına çevirirdi."""
    monkeypatch.delenv(TOKEN_ENV, raising=False)

    with pytest.raises(ValueError, match=TOKEN_ENV):
        async with transport_module.open_mcp_stream(_remote(token_env=TOKEN_ENV)):
            pass


async def test_token_varken_oauth_akisi_hic_baslatilmaz(monkeypatch):
    """Token varken giriş penceresi açılmamalı: OAuth sağlayıcısı kurulmamalı."""
    cagrildi = False

    async def fake_provider(_config, *, on_waiting=None, interactive=True):
        nonlocal cagrildi
        cagrildi = True
        return SimpleNamespace(auth=None, callback=SimpleNamespace(close=_noop))

    async def _noop() -> None:
        return None

    @asynccontextmanager
    async def open_stream(_config, *, auth=None) -> AsyncIterator[tuple[None, None]]:
        assert auth is None
        yield None, None

    from fusion_cli.mcp_bridge import oauth as oauth_module

    monkeypatch.setattr(oauth_module, "oauth_provider_for", fake_provider)
    monkeypatch.setattr(client_module, "open_mcp_stream", open_stream)
    monkeypatch.setattr(client_module, "ClientSession", lambda _r, _w: _Session())
    monkeypatch.setenv(TOKEN_ENV, "gizli-token")

    client = McpClient([_remote(token_env=TOKEN_ENV)])
    async with client:
        assert client.statuses["Meta Ads"].state == "bagli"
    assert cagrildi is False


def test_baglanti_ekle_token_icin_ortam_adi_turetir():
    """Kullanıcı token'ı yazar; adı ve saklanması Fusion'ın işi."""
    yeni, sonuc = add_connector(
        make_config(),
        {
            "ad": "Meta Ads",
            "tasima": "streamable_http",
            "url": "https://mcp.example.com/ads",
            "token": "gizli-token",
        },
    )

    assert yeni is not None, sonuc
    sunucu = yeni.mcp_servers[-1]
    assert sunucu.token_env == TOKEN_ENV
    assert TOKEN_ENV in sunucu.env_names
    # Değer config'e GİRMEZ.
    assert "gizli-token" not in repr(sunucu)
