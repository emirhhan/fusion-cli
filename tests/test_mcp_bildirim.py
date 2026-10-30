"""MCP bağlantı başarısızlığı: sunucu adı + kısa neden, tek satır, oturumda bir kez (30 Ekim)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from fusion_cli.cli import session as cli_session
from fusion_cli.cli.mcp_notice import new_failure_lines, short_reason
from fusion_cli.config.models import McpServerConfig
from fusion_cli.core.events import ErrorOccurred
from fusion_cli.mcp_bridge import pool as pool_module
from fusion_cli.mcp_bridge.client import McpConnectionStatus
from fusion_cli.mcp_bridge.pool import McpToolPool

from .fakes import make_config
from .test_mcp_pool import _configs, _FakeClient, _login_required, fake_client  # noqa: F401


def _bozuk(name: str, *, kind: str = "paket_yok") -> McpConnectionStatus:
    return McpConnectionStatus(
        server=name,
        state="hata",
        kind=kind,
        message="Bu bağlantının paketi npm üzerinde bulunamadı. Adı kontrol et.",
    )


async def test_baglanamayan_sunucu_bir_kez_bildirilir(fake_client):  # noqa: F811
    fake_client.results = {"notion": _bozuk("notion")}
    havuz = McpToolPool()

    await havuz.clients_for(_configs("notion", "godot"))
    ilk = havuz.take_new_failures(["notion", "godot"])
    await havuz.clients_for(_configs("notion", "godot"))
    ikinci = havuz.take_new_failures(["notion", "godot"])

    assert [durum.server for durum in ilk] == ["notion"]
    assert ikinci == ()
    await havuz.aclose()


async def test_giris_bekleyen_sunucu_basarisizlik_sayilmaz(fake_client):  # noqa: F811
    fake_client.results = {"notion": _login_required("notion")}
    havuz = McpToolPool()

    await havuz.clients_for(_configs("notion"))

    assert havuz.take_new_failures(["notion"]) == ()
    await havuz.aclose()


async def test_sunucu_duzeltilip_yeniden_bozulursa_yine_bildirilir(fake_client):  # noqa: F811
    fake_client.results = {"notion": _bozuk("notion")}
    havuz = McpToolPool()
    await havuz.clients_for(_configs("notion"))
    assert len(havuz.take_new_failures(["notion"])) == 1

    havuz.forget("notion")
    await havuz.clients_for(_configs("notion"))

    assert len(havuz.take_new_failures(["notion"])) == 1
    await havuz.aclose()


def test_kisa_neden_yalniz_ilk_cumleyi_alir_ve_satira_sigar():
    uzun = "Sunucu girişi reddetti (HTTP 401). Bağlantılar ekranında 'Bağlan'a bas."

    assert short_reason(uzun) == "Sunucu girişi reddetti (HTTP 401)"
    assert len(short_reason("a" * 400)) <= 110
    assert short_reason("") == "neden bilinmiyor"


async def test_satir_sunucu_adini_ve_nedeni_tasir(monkeypatch):
    monkeypatch.setattr(
        pool_module,
        "_POOL",
        SimpleNamespace(take_new_failures=lambda names: (_bozuk("notion"),)),
    )

    satirlar = new_failure_lines((McpServerConfig(name="notion", command="npx"),))

    assert len(satirlar) == 1
    assert "notion" in satirlar[0]
    assert "npm üzerinde bulunamadı" in satirlar[0]
    assert "Adı kontrol et" not in satirlar[0]


async def test_tur_baslangicinda_ham_uyari_degil_tek_satir_yayinlanir(monkeypatch):
    olaylar: list[object] = []
    bus = SimpleNamespace(publish=olaylar.append)

    async def sahte_run_agent(task, deps, **kwargs):
        from fusion_cli.engines.agent.loop import AgentOutcome

        return AgentOutcome(final_text="tamam", messages=[], ok=True)

    async def sahte_ensure(configs, registry, **kwargs):
        return ()

    monkeypatch.setattr(cli_session, "run_agent", sahte_run_agent)
    monkeypatch.setattr(pool_module, "ensure_mcp_tools", sahte_ensure)
    monkeypatch.setattr(
        pool_module,
        "_POOL",
        SimpleNamespace(take_new_failures=lambda names: (_bozuk("notion"), _bozuk("godot"))),
    )
    config = make_config(mcp_servers=_configs("notion", "godot"))

    await cli_session._run_agent_with_mcp(
        "merhaba",
        deps=SimpleNamespace(
            base_registry=None, tool_context=SimpleNamespace(available_tools=set())
        ),
        config=config,
        bus=bus,
        history=None,
        mode=cli_session.ApprovalMode.AUTO,
        extra_system="",
    )

    satirlar = [olay.message for olay in olaylar if isinstance(olay, ErrorOccurred)]
    assert len(satirlar) == 2
    assert "notion" in satirlar[0]
    assert "godot" in satirlar[1]


def test_mcp_paketi_uyarilari_son_care_isleyicisine_dusmez():
    gunluk = logging.getLogger("fusion_cli.mcp_bridge")

    assert any(isinstance(islem, logging.NullHandler) for islem in gunluk.handlers)
