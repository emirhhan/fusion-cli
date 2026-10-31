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


async def test_bilgisayar_kullanimi_kapaliysa_masaustu_araclari_sunulmaz(tmp_path):
    """Ölçüldü (31 Ekim): `desktop.enabled=false` iken `fusion mcp` desktop_* sunuyordu."""
    acik = await _names(build_server(tmp_path, expose_mutating=True))
    assert {"desktop_screenshot", "desktop_click"} <= acik

    kapali = build_server(
        tmp_path, expose_mutating=True, desktop_settings=DesktopSettings(enabled=False)
    )
    names = await _names(kapali)
    assert not any(name.startswith("desktop_") for name in names) and "read_file" in names
    result = await _call(kapali, "desktop_windows", {})
    assert result.isError is not True and "sunulmuyor" in result.content[0].text


@pytest.mark.parametrize(
    ("answer", "needle"),
    [
        ({"ok": True, "app": "1Password", "bundle": "com.1password.1password", "pid": 9}, "engelli"),
        ({"ok": False, "metin": "izin yok"}, "okunamadı"),
        ({"ok": True, "app": "Mail", "bundle": "com.apple.mail", "pid": 9}, "reddedilen"),
    ],
)
async def test_masaustu_politikasi_mcp_cagrisinda_da_uygulanir(tmp_path, monkeypatch, answer, needle):
    async def fake(_request):
        return answer

    monkeypatch.setattr(desktop_policy, "_swift_probe", fake)
    called: list[str] = []

    async def no_run(*_args, **_kwargs):
        called.append("run")
        raise AssertionError("araç çalışmamalı")

    server = build_server(
        tmp_path, expose_mutating=True, desktop_settings=DesktopSettings(denied_apps=("Mail",))
    )
    monkeypatch.setattr(mcp_server, "_execute", no_run)

    result = await _call(server, "desktop_type", {"text": "x"})

    assert result.isError is True and needle in result.content[0].text and called == []


def test_yapilandirma_okunamazsa_masaustu_kapali_sayilir(monkeypatch):
    from fusion_cli.core.errors import ConfigError

    def broken(*_args, **_kwargs):
        raise ConfigError("bozuk")

    monkeypatch.setattr(mcp_server, "load_config", broken)
    assert mcp_server.load_desktop_settings().enabled is False
