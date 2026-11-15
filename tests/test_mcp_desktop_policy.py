"""`fusion mcp` sunucusu masaüstü ayarını ve politikasını uygular (P-006/P-007 inceleme).

Süreç içi çağrılır; yardımcı (Swift) çağrılmaz, hedef sorgusu sahte verilir.
"""

from __future__ import annotations

import mcp.types as mcp_types
import pytest

from fusion_cli.core.desktop_settings import DesktopSettings
from fusion_cli.mcp_bridge import server as mcp_server
from fusion_cli.mcp_bridge.server import build_server
from fusion_cli.tools import desktop_policy


async def _names(server) -> set[str]:
    handler = server.request_handlers[mcp_types.ListToolsRequest]
    result = (await handler(mcp_types.ListToolsRequest(method="tools/list"))).root
    return {tool.name for tool in result.tools}


async def _call(server, name: str, arguments: dict[str, object]):
    handler = server.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments),
    )
    return (await handler(request)).root


@pytest.mark.parametrize("enabled", [True, False])
async def test_mcp_sunucusu_masaustu_araclarini_hic_sunmaz(tmp_path, monkeypatch, enabled):
    """#445: Claude Code'da computer use etkileşimli oturum ister; `fusion mcp` dış istemciye
    `desktop_*` açmaz (`desktop.enabled` açık olsa da). Ölçüldü (1 Kasım): açıkken sunuluyor,
    uygulama onayı dış istemciye bırakılıyordu."""
    called: list[str] = []

    async def no_run(*_args, **_kwargs):
        called.append("run")
        raise AssertionError("araç çalışmamalı")

    server = build_server(
        tmp_path, expose_mutating=True, desktop_settings=DesktopSettings(enabled=enabled)
    )
    monkeypatch.setattr(mcp_server, "_execute", no_run)
    names = await _names(server)
    assert not any(name.startswith("desktop_") for name in names) and "read_file" in names
    result = await _call(server, "desktop_type", {"text": "x"})
    assert "sunulmuyor" in result.content[0].text and called == []


async def test_politika_savunma_katmani_kalir(tmp_path, monkeypatch):
    async def fake(_request):
        return {"ok": True, "app": "Mail", "bundle": "com.apple.mail", "pid": 9}

    monkeypatch.setattr(desktop_policy, "_swift_probe", fake)
    context = mcp_server.ToolContext(
        root=tmp_path, desktop_settings=DesktopSettings(enabled=True, denied_apps=("Mail",))
    )
    refusal = await mcp_server._desktop_refusal("desktop_type", {"text": "x"}, context)
    assert refusal is not None and "reddedilen" in refusal


def test_yapilandirma_okunamazsa_masaustu_kapali_sayilir(monkeypatch):
    from fusion_cli.core.errors import ConfigError

    def broken(*_args, **_kwargs):
        raise ConfigError("bozuk")

    monkeypatch.setattr(mcp_server, "load_config", broken)
    assert mcp_server.load_desktop_settings().enabled is False
