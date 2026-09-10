"""MCP bağlantıları oturum boyunca açık kalır; her tur yeniden bağlanmaz."""

from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest

from fusion_cli.config.models import McpServerConfig
from fusion_cli.mcp_bridge import pool as pool_module
from fusion_cli.mcp_bridge.pool import McpToolPool


class _FakeClient:
    """`McpClient` yerine geçer; giriş/çıkış sayılarını ve görevini kaydeder."""

    opened = 0
    closed = 0
    enter_tasks: ClassVar[list[object]] = []
    exit_tasks: ClassVar[list[object]] = []

    def __init__(self, configs, **_kwargs) -> None:
        self.configs = tuple(configs)

    async def __aenter__(self) -> _FakeClient:
        type(self).opened += 1
        type(self).enter_tasks.append(asyncio.current_task())
        return self

    async def __aexit__(self, *_exc: object) -> None:
        type(self).closed += 1
        type(self).exit_tasks.append(asyncio.current_task())

    async def register_into(self, registry: object) -> tuple[str, ...]:
        del registry
        return ("godot__save_scene",)


@pytest.fixture
def fake_client(monkeypatch):
    _FakeClient.opened = 0
    _FakeClient.closed = 0
    _FakeClient.enter_tasks = []
    _FakeClient.exit_tasks = []
    monkeypatch.setattr(pool_module, "McpClient", _FakeClient)
    return _FakeClient


def _configs(*names: str) -> tuple[McpServerConfig, ...]:
    return tuple(McpServerConfig(name=name, command="npx") for name in names)


async def test_ayni_yapilandirmada_ikinci_tur_yeniden_baglanmaz(fake_client):
    """Ölçülmüş maliyet: her tur stdio sunucusunu yeniden başlatıyordu."""
    havuz = McpToolPool()

    first = await havuz.client_for(_configs("godot"))
    second = await havuz.client_for(_configs("godot"))

    assert first is second
    assert fake_client.opened == 1
    await havuz.aclose()
    assert fake_client.closed == 1


async def test_yapilandirma_degisince_havuz_yenilenir(fake_client):
    """Kullanıcı bağlantı ekleyince eski bağlantılar kapanır, yenisi açılır."""
    havuz = McpToolPool()

    await havuz.client_for(_configs("godot"))
    await havuz.client_for(_configs("godot", "meta"))

    assert fake_client.opened == 2
    assert fake_client.closed == 1
    await havuz.aclose()


async def test_yigin_acildigi_gorevde_kapatilir(fake_client):
    """anyio cancel scope'u başka görevde terk edilemez; ömür gözetmene aittir."""
    havuz = McpToolPool()

    await havuz.client_for(_configs("godot"))
    # Kapatma BAŞKA bir görevden istenir — gerçek teardown da böyle çağırıyor.
    await asyncio.create_task(havuz.aclose())

    assert fake_client.enter_tasks == fake_client.exit_tasks
    assert fake_client.enter_tasks[0] is not asyncio.current_task()


async def test_baglanma_hatasi_havuzda_saklanmaz(monkeypatch):
    """Başarısız bağlantı önbelleğe yazılmaz: sonraki tur yeniden denesin."""

    class _Bozuk(_FakeClient):
        async def __aenter__(self):
            raise RuntimeError("sunucu yok")

    monkeypatch.setattr(pool_module, "McpClient", _Bozuk)
    havuz = McpToolPool()

    with pytest.raises(RuntimeError, match="sunucu yok"):
        await havuz.client_for(_configs("godot"))

    assert havuz.is_empty
    await havuz.aclose()
