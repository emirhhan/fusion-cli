"""Normal bir tur ASLA giriş penceresi açmamalı.

Ölçüldü (11 Eylül, kullanıcı makinesi): kullanıcı Fusion'a bir istek yazıp Enter'a
bastığında Notion'un yetkilendirme sayfası tarayıcıda AÇILIYORDU. Sebep: `notion`
OAuth'lu uzak bir MCP sunucusu ve her tur `ensure_mcp_tools` ile bağlanılıyor;
geçerli token yoksa SDK yönlendirme işleyicisini çağırıyor, o da
`webbrowser.open()` yapıyor.

Giriş KULLANICININ açık eylemidir ("Bağlan" düğmesi). Tur yolunda bağlantı bir
zenginleştirmedir: token yoksa o sunucu atlanır ve tur MCP'siz sürer.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge import client as client_module
from fusion_cli.mcp_bridge import oauth as oauth_module
from fusion_cli.mcp_bridge.client import McpClient


def _remote() -> McpServerConfig:
    return McpServerConfig(
        name="notion", transport=McpTransport.STREAMABLE_HTTP, url="https://mcp.example.com/sse"
    )


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def initialize(self) -> None:
        return None


async def test_etkilesimsiz_kipte_tarayici_acilmaz(monkeypatch):
    acilan: list[str] = []
    monkeypatch.setattr(oauth_module.webbrowser, "open", lambda url, **_k: acilan.append(url))

    yakalanan: dict[str, object] = {}

    async def sahte_saglayici(config, *, on_waiting=None, interactive=True):
        yakalanan["interactive"] = interactive
        # Gerçek `oauth_provider_for` bayrağı callback'e geçirir; sahte de geçirmeli.
        callback = oauth_module.LoopbackOAuthCallback(
            timeout_seconds=1, port=0, interactive=interactive
        )
        await callback.start()
        # Etkileşimsiz kipte yönlendirme istemi tarayıcı AÇMAMALI.
        with contextlib.suppress(oauth_module.McpLoginRequiredError):
            await callback.open_redirect("https://mcp.example.com/authorize")
        await callback.close()
        from types import SimpleNamespace

        return SimpleNamespace(auth=None, callback=callback)

    @asynccontextmanager
    async def open_stream(_config, *, auth=None) -> AsyncIterator[tuple[None, None]]:
        yield None, None

    monkeypatch.setattr(oauth_module, "oauth_provider_for", sahte_saglayici)
    monkeypatch.setattr(client_module, "open_mcp_stream", open_stream)
    monkeypatch.setattr(client_module, "ClientSession", lambda _r, _w: _Session())

    async with McpClient((_remote(),), interactive=False):
        pass

    assert yakalanan["interactive"] is False
    assert acilan == [], f"tur sırasında tarayıcı açıldı: {acilan}"


async def test_acik_giris_eyleminde_tarayici_acilir(monkeypatch):
    """Kullanıcı 'Bağlan' dediğinde davranış değişmemeli."""
    acilan: list[str] = []
    monkeypatch.setattr(oauth_module.webbrowser, "open", lambda url, **_k: acilan.append(url))

    callback = oauth_module.LoopbackOAuthCallback(timeout_seconds=1, port=0)
    await callback.start()
    await callback.open_redirect("https://mcp.example.com/authorize")
    await callback.close()

    assert acilan == ["https://mcp.example.com/authorize"]
