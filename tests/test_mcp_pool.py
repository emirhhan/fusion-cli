"""MCP bağlantıları oturum boyunca açık kalır; her tur yeniden bağlanmaz."""

from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge import pool as pool_module
from fusion_cli.mcp_bridge.client import McpConnectionStatus
from fusion_cli.mcp_bridge.pool import McpToolPool
from fusion_cli.tools import ToolRegistry


class _FakeClient:
    """`McpClient` yerine geçer; giriş/çıkış sayılarını ve görevini kaydeder.

    Durum sınıf düzeyinde ayarlanır: `results[ad]` verilmişse o sunucu o durumla
    "bağlanır" (ör. giriş gerekli), verilmemişse bağlı sayılır.
    """

    opened: ClassVar[list[str]] = []
    closed: ClassVar[list[str]] = []
    enter_tasks: ClassVar[list[object]] = []
    exit_tasks: ClassVar[list[object]] = []
    results: ClassVar[dict[str, McpConnectionStatus]] = {}

    def __init__(self, configs, **_kwargs) -> None:
        self.configs = tuple(configs)
        self.name = self.configs[0].name

    @property
    def statuses(self) -> dict[str, McpConnectionStatus]:
        status = type(self).results.get(self.name)
        return {self.name: status or McpConnectionStatus(server=self.name, state="bagli")}

    async def __aenter__(self) -> _FakeClient:
        type(self).opened.append(self.name)
        type(self).enter_tasks.append(asyncio.current_task())
        return self

    async def __aexit__(self, *_exc: object) -> None:
        type(self).closed.append(self.name)
        type(self).exit_tasks.append(asyncio.current_task())

    async def register_into(self, registry: object) -> tuple[str, ...]:
        del registry
        return (f"{self.name}__arac",)


@pytest.fixture
def fake_client(monkeypatch):
    _FakeClient.opened = []
    _FakeClient.closed = []
    _FakeClient.enter_tasks = []
    _FakeClient.exit_tasks = []
    _FakeClient.results = {}
    monkeypatch.setattr(pool_module, "McpClient", _FakeClient)
    return _FakeClient


def _configs(*names: str) -> tuple[McpServerConfig, ...]:
    return tuple(McpServerConfig(name=name, command="npx", args=(name,)) for name in names)


def _login_required(name: str) -> McpConnectionStatus:
    return McpConnectionStatus(
        server=name, state="giris_gerekli", message="giriş gerekli", kind="giris_gerekli"
    )


async def test_ayni_yapilandirmada_ikinci_tur_yeniden_baglanmaz(fake_client):
    """Ölçülmüş maliyet: her tur stdio sunucusunu yeniden başlatıyordu."""
    havuz = McpToolPool()

    first = await havuz.clients_for(_configs("godot"))
    second = await havuz.clients_for(_configs("godot"))

    assert first == second
    assert fake_client.opened == ["godot"]
    await havuz.aclose()
    assert fake_client.closed == ["godot"]


async def test_yeni_baglanti_eklenince_yalniz_o_sunucu_baslar(fake_client):
    """Bağlantı eklemek ya da kapatmak diğer sunucuları yeniden başlatmamalı."""
    havuz = McpToolPool()

    await havuz.clients_for(_configs("godot"))
    await havuz.clients_for(_configs("godot", "meta"))
    await havuz.clients_for(_configs("meta"))

    assert fake_client.opened == ["godot", "meta"]
    assert fake_client.closed == ["godot"]
    await havuz.aclose()


async def test_sunucular_esezamanli_baglanir(monkeypatch):
    """Tur başı gecikme sunucuların TOPLAMI değil en yavaşı olmalı."""
    baslayan: list[str] = []
    ikisi_basladi = asyncio.Event()

    class _Yavas(_FakeClient):
        async def __aenter__(self):
            baslayan.append(self.name)
            if len(baslayan) == 2:
                ikisi_basladi.set()
            # Sırayla bağlansaydı ikinci sunucu hiç başlamaz, bu bekleme bitmezdi.
            await asyncio.wait_for(ikisi_basladi.wait(), timeout=2)
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(pool_module, "McpClient", _Yavas)
    havuz = McpToolPool()

    clients = await havuz.clients_for(_configs("godot", "meta"))

    assert len(clients) == 2
    await havuz.aclose()


async def test_yigin_acildigi_gorevde_kapatilir(fake_client):
    """anyio cancel scope'u başka görevde terk edilemez; ömür gözetmene aittir."""
    havuz = McpToolPool()

    await havuz.clients_for(_configs("godot"))
    # Kapatma BAŞKA bir görevden istenir — gerçek teardown da böyle çağırıyor.
    await asyncio.create_task(havuz.aclose())

    assert fake_client.enter_tasks == fake_client.exit_tasks
    assert fake_client.enter_tasks[0] is not asyncio.current_task()


async def test_gecici_baglanma_hatasi_havuzda_saklanmaz(monkeypatch):
    """Geçici arıza önbelleğe yazılmaz: sonraki tur yeniden denesin."""
    denemeler: list[str] = []

    class _Bozuk(_FakeClient):
        async def __aenter__(self):
            denemeler.append(self.name)
            raise TimeoutError

    monkeypatch.setattr(pool_module, "McpClient", _Bozuk)
    havuz = McpToolPool()

    assert await havuz.clients_for(_configs("godot")) == ()
    assert await havuz.clients_for(_configs("godot")) == ()

    assert denemeler == ["godot", "godot"]
    assert havuz.is_empty
    await havuz.aclose()


async def test_giris_gereken_sunucu_turlarda_tekrar_denenmez(fake_client):
    """Notion her turda OAuth hata dökümü basıyordu; bir kez atlanmalı ve bildirilmeli."""
    fake_client.results = {"notion": _login_required("notion")}
    havuz = McpToolPool()

    first = await havuz.clients_for(_configs("notion", "godot"))
    second = await havuz.clients_for(_configs("notion", "godot"))

    assert [client.name for client in first] == ["godot"]
    assert [client.name for client in second] == ["godot"]
    assert fake_client.opened == ["notion", "godot"]
    # Başarısız bağlantı açık bırakılmaz ve durumu ekrana taşınır.
    assert "notion" in fake_client.closed
    assert havuz.statuses["notion"].state == "giris_gerekli"
    await havuz.aclose()


async def test_giris_yapilinca_park_kalkar_ve_sunucu_baglanir(fake_client):
    fake_client.results = {"notion": _login_required("notion")}
    havuz = McpToolPool()
    await havuz.clients_for(_configs("notion"))

    fake_client.results = {}
    havuz.forget("notion")
    clients = await havuz.clients_for(_configs("notion"))

    assert [client.name for client in clients] == ["notion"]
    assert fake_client.opened == ["notion", "notion"]
    await havuz.aclose()


async def test_yapilandirmasi_degisen_park_edilmis_sunucu_yeniden_denenir(fake_client):
    fake_client.results = {"notion": _login_required("notion")}
    havuz = McpToolPool()
    await havuz.clients_for(_configs("notion"))

    degisen = (McpServerConfig(name="notion", command="npx", args=("yeni",)),)
    await havuz.clients_for(degisen)

    assert fake_client.opened == ["notion", "notion"]
    await havuz.aclose()


async def test_ayni_sunucuya_giden_kopyalar_bir_kez_baglanir(fake_client):
    """Ayardaki üç Meta kopyası üç ayrı bağlantı açıyordu."""
    kopyalar = tuple(
        McpServerConfig(name=name, transport=McpTransport.STREAMABLE_HTTP, url=url)
        for name, url in (
            ("meta", "https://mcp.facebook.com/ads"),
            ("meta-2", "https://MCP.facebook.com/ads/"),
            ("meta-3", "https://mcp.facebook.com:443/ads"),
        )
    )
    havuz = McpToolPool()

    clients = await havuz.clients_for(kopyalar)

    assert [client.name for client in clients] == ["meta"]
    assert fake_client.opened == ["meta"]
    await havuz.aclose()


async def test_baglanirken_iptal_gozetmeni_sahipsiz_birakmaz(monkeypatch):
    """İptal edilen ilk tur, açılmış bağlantıyı arkada bırakmamalı.

    Ölçülmüş sızıntı yolu (inceleme): kullanıcı REPL'de Ctrl-C'ye bastığında ya da
    `AppSession.close()` çalışan turu iptal ettiğinde bağlantı kurulurken tur iptal
    ediliyordu. Girdi havuza yazılmadan çıkılıyor, gözetmen görevi bağlanmayı
    bitirip `stop.wait()`'te sonsuza park ediyor ve `aclose()` onu bulamıyordu:
    stdio alt süreci (npx ...) oturumdan sağ çıkıyordu.
    """
    baslatildi = asyncio.Event()
    serbest = asyncio.Event()
    kapandi = asyncio.Event()

    class _Yavas(_FakeClient):
        async def __aenter__(self):
            baslatildi.set()
            await serbest.wait()
            return self

        async def __aexit__(self, *_exc: object) -> None:
            kapandi.set()

    monkeypatch.setattr(pool_module, "McpClient", _Yavas)
    havuz = McpToolPool()

    gorev = asyncio.create_task(havuz.clients_for(_configs("godot")))
    await baslatildi.wait()
    gorev.cancel()
    with pytest.raises(asyncio.CancelledError):
        await gorev

    # Bağlantı kurulmayı bitirir (gerçek dünyada npx ayağa kalkar)...
    serbest.set()
    # ...ve teardown onu BULMAK zorundadır.
    await havuz.aclose()

    assert kapandi.is_set(), "iptal edilen turun bağlantısı sahipsiz kaldı"


async def test_bir_sunucunun_kesfi_dusse_digerlerinin_araclari_eklenir(monkeypatch, fake_client):
    class _Kopan(_FakeClient):
        async def register_into(self, registry: object) -> tuple[str, ...]:
            if self.name == "godot":
                raise ConnectionError("süreç öldü")
            return await super().register_into(registry)

    monkeypatch.setattr(pool_module, "McpClient", _Kopan)
    havuz = McpToolPool()
    monkeypatch.setattr(pool_module, "_POOL", havuz)

    eklenen = await pool_module.ensure_mcp_tools(_configs("godot", "meta"), ToolRegistry())

    assert eklenen == ("meta__arac",)
    # Kopan sunucu bırakılır; sonraki tur yeniden bağlanır.
    assert [client.name for client in await havuz.clients_for(_configs("godot"))] == ["godot"]
    await havuz.aclose()


async def test_ayni_kayit_defterine_ikinci_kayit_turu_dusurmez(fake_client, tmp_path):
    """Bağlantı oturum boyunca yaşıyorsa araçlar aynı deftere iki kez yazılabilir.

    `ToolRegistry.register` yinelenen adda `FusionError` fırlatır. Bağlantı artık
    turlar arası yaşadığı için, aynı `base_registry` ikinci turda yeniden
    beslenirse tur bu hatayla düşerdi. Uzak araç her keşifte TAZE şemayla gelir;
    doğru davranış üzerine yazmaktır.
    """
    from fusion_cli.core.tools import Tool, ToolResult

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
