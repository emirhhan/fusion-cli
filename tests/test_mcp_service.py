from __future__ import annotations

import asyncio

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge.client import McpConnectionStatus
from fusion_cli.mcp_bridge.service import McpConnectionService


async def test_giris_arka_planda_baslar_ve_durum_sorgulanir() -> None:
    release = asyncio.Event()

    async def probe(_config: McpServerConfig) -> McpConnectionStatus:
        await release.wait()
        return McpConnectionStatus(server="meta", state="bagli", tool_count=4)

    service = McpConnectionService(probe=probe)
    config = McpServerConfig(
        name="meta",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.example.com/mcp",
    )

    started = service.start_login(config)
    assert started.state == "giris_bekleniyor"
    assert service.login_status("meta").state == "giris_bekleniyor"

    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert service.login_status("meta").state == "bagli"
    await service.close()


async def test_ayni_baglanti_icin_ikinci_giris_gorevi_acilmaz() -> None:
    blocker = asyncio.Event()

    async def probe(_config: McpServerConfig) -> McpConnectionStatus:
        await blocker.wait()
        return McpConnectionStatus(server="meta", state="bagli")

    service = McpConnectionService(probe=probe)
    config = McpServerConfig(name="meta", command="x")

    service.start_login(config)
    first = service.pending_task("meta")
    service.start_login(config)

    assert service.pending_task("meta") is first
    blocker.set()
    await service.close()


async def test_hic_test_edilmemis_sunucunun_durumu_turlardan_gelir() -> None:
    """Turda atlanan giriş-gerekli sunucu Bağlantılar ekranında görünmeli."""
    tur_durumu = McpConnectionStatus(server="notion", state="giris_gerekli", kind="giris_gerekli")
    service = McpConnectionService(pool_statuses=lambda: {"notion": tur_durumu})

    assert service.statuses["notion"].state == "giris_gerekli"


async def test_kullanicinin_kendi_denemesi_tur_durumundan_onceliklidir() -> None:
    async def probe(config: McpServerConfig) -> McpConnectionStatus:
        return McpConnectionStatus(server=config.name, state="bagli", tool_count=3)

    eski = McpConnectionStatus(server="notion", state="giris_gerekli")
    service = McpConnectionService(probe=probe, pool_statuses=lambda: {"notion": eski})

    await service.test(McpServerConfig(name="notion", command="x"))

    assert service.statuses["notion"].state == "bagli"


async def test_dogrulama_giris_penceresi_acmayan_yoklamayi_kullanir() -> None:
    kullanilan: list[str] = []

    async def probe(config: McpServerConfig) -> McpConnectionStatus:
        kullanilan.append("etkilesimli")
        return McpConnectionStatus(server=config.name, state="bagli")

    async def quiet(config: McpServerConfig) -> McpConnectionStatus:
        kullanilan.append("sessiz")
        return McpConnectionStatus(server=config.name, state="giris_gerekli")

    service = McpConnectionService(probe=probe, quiet_probe=quiet, pool_statuses=dict)

    status = await service.verify(McpServerConfig(name="notion", command="x"))

    assert status.state == "giris_gerekli"
    assert kullanilan == ["sessiz"]


async def test_basarili_giris_turdaki_park_kaydini_kaldirir(monkeypatch) -> None:
    from fusion_cli.mcp_bridge import service as service_module

    unutulan: list[str] = []
    monkeypatch.setattr(service_module, "forget_mcp_failure", unutulan.append)

    async def probe(config: McpServerConfig) -> McpConnectionStatus:
        return McpConnectionStatus(server=config.name, state="bagli")

    service = McpConnectionService(probe=probe, pool_statuses=dict)
    service.start_login(McpServerConfig(name="notion", command="x"))
    await asyncio.wait_for(service.pending_task("notion"), timeout=2)

    assert service.login_status("notion").state == "bagli"
    assert unutulan == ["notion"]


def test_new_pool_failure_is_not_hidden_by_old_success():
    old_success = McpConnectionStatus(server="offline", state="bagli", observed_at=1.0)
    fresh_failure = McpConnectionStatus(server="offline", state="zaman_asimi", observed_at=2.0)
    service = McpConnectionService(pool_statuses=lambda: {"offline": fresh_failure})
    service._record("offline", old_success)
    assert service.statuses["offline"].state == "zaman_asimi"


async def test_old_source_probe_cannot_replace_new_source_health():
    entered, release = asyncio.Event(), asyncio.Event()

    async def probe(config):
        if config.command == "old":
            entered.set()
            await release.wait()
            return McpConnectionStatus(config.name, "bagli")
        return McpConnectionStatus(config.name, "giris_gerekli")

    service = McpConnectionService(probe=probe, pool_statuses=dict)
    old = asyncio.create_task(service.test(McpServerConfig("offline", command="old")))
    await entered.wait()
    await service.test(McpServerConfig("offline", command="new"))
    release.set()
    await old
    assert service.statuses["offline"].state == "giris_gerekli"
    await service.close()


async def test_new_login_during_logout_cleanup_keeps_its_health():
    entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def probe(config):
        if config.command == "old":
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cleaning.set()
                await release.wait()
                raise
        return McpConnectionStatus(config.name, "bagli")

    service = McpConnectionService(probe=probe, pool_statuses=dict)
    old = McpServerConfig("offline", command="old")
    service.start_login(old)
    await entered.wait()
    logout = asyncio.create_task(service.logout(old))
    await cleaning.wait()
    service.start_login(McpServerConfig("offline", command="new"))
    await service.pending_task("offline")
    assert service.login_status("offline").state == "bagli"
    release.set()
    await logout
    assert service.login_status("offline").state == "bagli"
    await service.close()
