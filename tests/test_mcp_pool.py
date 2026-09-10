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


async def test_baglanirken_iptal_gozetmeni_sahipsiz_birakmaz(monkeypatch):
    """İptal edilen ilk tur, açılmış bağlantıyı arkada bırakmamalı.

    Ölçülmüş sızıntı yolu (inceleme): kullanıcı REPL'de Ctrl-C'ye bastığında ya da
    `AppSession.close()` çalışan turu iptal ettiğinde `client_for` bağlantı
    kurulurken iptal ediliyordu. `_open` `self._entry`'yi ATAMADAN çıkıyor, gözetmen
    görevi bağlanmayı bitirip `stop.wait()`'te sonsuza park ediyor ve `aclose()`
    `self._entry is None` görüp hiçbir şey yapmıyordu: stdio alt süreci (npx ...)
    oturumdan sağ çıkıyordu — yani bu modülün var olma gerekçesinin tam tersi.
    """
    baslatildi = asyncio.Event()
    serbest = asyncio.Event()
    kapandi = asyncio.Event()

    class _Yavas:
        def __init__(self, configs, **_kwargs) -> None:
            del configs

        async def __aenter__(self):
            baslatildi.set()
            await serbest.wait()
            return self

        async def __aexit__(self, *_exc: object) -> None:
            kapandi.set()

    monkeypatch.setattr(pool_module, "McpClient", _Yavas)
    havuz = McpToolPool()

    gorev = asyncio.create_task(havuz.client_for(_configs("godot")))
    await baslatildi.wait()
    gorev.cancel()
    with pytest.raises(asyncio.CancelledError):
        await gorev

    # Bağlantı kurulmayı bitirir (gerçek dünyada npx ayağa kalkar)...
    serbest.set()
    # ...ve teardown onu BULMAK zorundadır.
    await havuz.aclose()

    assert kapandi.is_set(), "iptal edilen turun bağlantısı sahipsiz kaldı"


async def test_ayni_kayit_defterine_ikinci_kayit_turu_dusurmez(fake_client, tmp_path):
    """Bağlantı oturum boyunca yaşıyorsa araçlar aynı deftere iki kez yazılabilir.

    `ToolRegistry.register` yinelenen adda `FusionError` fırlatır. Bağlantı artık
    turlar arası yaşadığı için, aynı `base_registry` ikinci turda yeniden
    beslenirse tur bu hatayla düşerdi. Uzak araç her keşifte TAZE şemayla gelir;
    doğru davranış üzerine yazmaktır.
    """
    from fusion_cli.core.tools import Tool, ToolResult
    from fusion_cli.tools import ToolRegistry

    registry = ToolRegistry()

    async def _run(args: object, context: object) -> ToolResult:
        del args, context
        return ToolResult.success("")

    arac = Tool(name="godot__save_scene", description="", parameters={}, run=_run, mutating=True)
    registry.register_or_replace(arac)
    registry.register_or_replace(arac)

    assert registry.get("godot__save_scene") is arac


async def test_barindirmali_kanal_turlar_arasi_korunur(monkeypatch):
    """Kanal her turda yeniden kurulursa konuşma geçmişi çöpe gider.

    `hosted_bridge` konuşmanın SÜREKLİ olmasını şart koşuyor: her tur yeni kanal
    demek, her turda yeniden keşif turu ve kaybolan bağlam demekti.
    """
    from dataclasses import replace

    from fusion_cli.config.models import HostedConnectorConfig, WebSessionConfig
    from fusion_cli.tools import ToolRegistry

    from .fakes import make_config

    kurulan: list[object] = []

    class _Kanal:
        def __init__(self, config) -> None:
            kurulan.append(config)

        async def __call__(self, connector, prompt):
            del connector, prompt
            return ""

    monkeypatch.setattr(pool_module, "_hosted_channel_factory", _Kanal, raising=False)

    config = replace(
        make_config(),
        web_sessions=(
            WebSessionConfig(
                model="claude_web/main/auto",
                provider="claude_web",
                account="main",
                transport="browser",
                login_verified=True,
                enabled=True,
            ),
        ),
        hosted_connectors=(
            HostedConnectorConfig(
                name="MetaAds",
                url="https://mcp.facebook.com/ads",
                provider="claude_web",
                verified=False,
            ),
        ),
    )

    await pool_module.ensure_hosted_tools(config, ToolRegistry())
    await pool_module.ensure_hosted_tools(config, ToolRegistry())

    assert len(kurulan) == 1, "aynı yapılandırmada kanal yeniden kurulmamalı"
