"""Uzak MCP bağlantısında başarısızlık ve kullanıcı girişi bekleme davranışı."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import anyio
import anyio.lowlevel
import httpx
import pytest
from mcp.client.auth.exceptions import OAuthRegistrationError

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge import client as client_module
from fusion_cli.mcp_bridge import oauth as oauth_module
from fusion_cli.mcp_bridge.client import McpClient
from fusion_cli.mcp_bridge.service import McpConnectionService


def _remote() -> McpServerConfig:
    return McpServerConfig(
        name="meta", transport=McpTransport.STREAMABLE_HTTP, url="https://mcp.example.com/mcp"
    )


class _Session:
    """SDK `ClientSession` yerine geçer; `initialize` davranışı parametre ile verilir."""

    def __init__(self, *, blocks: bool) -> None:
        self._blocks = blocks

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def initialize(self) -> None:
        if self._blocks:
            await anyio.sleep_forever()


def _session_factory(*, blocks: bool):
    return lambda _read, _write: _Session(blocks=blocks)


async def test_kayit_reddi_giris_durumunu_client_id_mesajiyla_hataya_dusurur(monkeypatch):
    """Meta gibi sunucu dinamik kaydı reddedince giriş sonsuza dek "bekleniyor"da kalıyordu.

    SDK hatayı taşıma görev grubunda fırlatır ve bekleyen `initialize`'ı İPTAL
    eder; asıl hata ancak bağlantı yığını kapanırken görünür.
    """

    async def fake_provider(_config, *, on_waiting=None, interactive=True):
        return SimpleNamespace(
            auth=None, callback=oauth_module.LoopbackOAuthCallback(timeout_seconds=1)
        )

    @asynccontextmanager
    async def rejecting_stream(_config, *, auth=None) -> AsyncIterator[tuple[None, None]]:
        async def reject() -> None:
            await anyio.lowlevel.checkpoint()
            raise OAuthRegistrationError("Registration failed: 400 invalid_client_metadata")

        async with anyio.create_task_group() as group:
            group.start_soon(reject)
            yield None, None

    monkeypatch.setattr(oauth_module, "oauth_provider_for", fake_provider)
    monkeypatch.setattr(client_module, "open_mcp_stream", rejecting_stream)
    monkeypatch.setattr(client_module, "ClientSession", _session_factory(blocks=True))
    service = McpConnectionService()

    service.start_login(_remote())
    await asyncio.wait_for(service.pending_task("meta"), timeout=5)
    status = service.login_status("meta")

    assert status.state == "hata"
    assert "client_id" in (status.message or "")
    await service.close()


async def test_dis_iptal_mcp_baglantisinda_yutulmaz(monkeypatch):
    @asynccontextmanager
    async def open_stream(_config, *, auth=None) -> AsyncIterator[tuple[None, None]]:
        yield None, None

    monkeypatch.setattr(client_module, "open_mcp_stream", open_stream)
    monkeypatch.setattr(client_module, "ClientSession", _session_factory(blocks=True))
    connecting = asyncio.ensure_future(
        McpClient((McpServerConfig(name="godot", command="x"),), timeout_seconds=5).__aenter__()
    )
    await asyncio.sleep(0.05)

    connecting.cancel()

    with pytest.raises(asyncio.CancelledError):
        await connecting


async def test_kullanici_girisi_beklenirken_baglanti_zaman_asimi_islemez(monkeypatch):
    """Tarayıcıda giriş yapan kullanıcıya 10 saniyelik bağlantı süresi uygulanıyordu."""
    monkeypatch.setattr(oauth_module.webbrowser, "open", lambda *_args, **_kwargs: True)
    callbacks: list[oauth_module.LoopbackOAuthCallback] = []

    async def fake_provider(_config, *, on_waiting=None, interactive=True):
        callback = oauth_module.LoopbackOAuthCallback(timeout_seconds=2, on_waiting=on_waiting)
        await callback.start()
        callbacks.append(callback)
        return SimpleNamespace(auth=None, callback=callback)

    @asynccontextmanager
    async def login_stream(_config, *, auth=None) -> AsyncIterator[tuple[None, None]]:
        callback = callbacks[0]
        await callback.open_redirect("https://login.example.com")
        # Kullanıcı giriş yapıyor: bağlantı süresinin (0.1 sn) üç katı.
        await asyncio.sleep(0.3)
        async with httpx.AsyncClient() as http:
            await http.get(f"{callback.redirect_uri}?code=abc&state=s")
        await callback.wait_for_code()
        yield None, None

    monkeypatch.setattr(oauth_module, "oauth_provider_for", fake_provider)
    monkeypatch.setattr(client_module, "open_mcp_stream", login_stream)
    monkeypatch.setattr(client_module, "ClientSession", _session_factory(blocks=False))

    async with McpClient((_remote(),), timeout_seconds=0.1) as client:
        assert client.statuses["meta"].state == "bagli"


async def test_loopback_callback_bekleme_durumunu_bildirir(monkeypatch):
    monkeypatch.setattr(oauth_module.webbrowser, "open", lambda *_args, **_kwargs: True)
    states: list[bool] = []
    callback = oauth_module.LoopbackOAuthCallback(timeout_seconds=2, on_waiting=states.append)
    await callback.start()

    await callback.open_redirect("https://login.example.com")
    async with httpx.AsyncClient() as http:
        await http.get(f"{callback.redirect_uri}?code=abc&state=s")
    await callback.wait_for_code()

    assert states == [True, False]
