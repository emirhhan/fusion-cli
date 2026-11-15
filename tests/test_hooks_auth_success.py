"""`Notification(auth_success)` (#125): MCP girişi bağlanarak bitince."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.core.hooks.events import HookSet
from fusion_cli.engines.hooks.notify import notify_auth_success
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.mcp_bridge.client import McpConnectionStatus
from fusion_cli.mcp_bridge.service import McpConnectionService

_CONFIG = McpServerConfig(
    name="meta", transport=McpTransport.STREAMABLE_HTTP, url="https://mcp.example.com/mcp"
)


def _service(state: str) -> tuple[McpConnectionService, list[str]]:
    async def probe(_config: McpServerConfig) -> McpConnectionStatus:
        return McpConnectionStatus(server="meta", state=state)

    service = McpConnectionService(probe=probe)
    seen: list[str] = []
    service.on_login_success = seen.append
    return service, seen


async def _settle(service: McpConnectionService) -> None:
    task = service.pending_task("meta")
    if task is not None:
        await task


async def test_basarili_giris_geri_cagirimi_tetikler() -> None:
    service, seen = _service("bagli")
    service.start_login(_CONFIG)
    await _settle(service)
    assert seen == ["meta"]
    await service.close()


async def test_basarisiz_giris_tetiklemez() -> None:
    service, seen = _service("giris_gerekli")
    service.start_login(_CONFIG)
    await _settle(service)
    assert seen == []
    await service.close()


def test_kanca_auth_success_turu_ve_basligi_alir(tmp_path: Path) -> None:
    log = tmp_path / "girdi.json"
    script = tmp_path / "k.py"
    script.write_text(
        f"import sys\nopen(r'{log}', 'w').write(sys.stdin.read())\nsys.exit(2)\n",
        encoding="utf-8",
    )
    commands, skipped = parse_hooks_block(
        {
            "Notification": [
                {
                    "matcher": "auth_success",
                    "hooks": [{"type": "command", "command": f"{sys.executable} {script}"}],
                }
            ]
        },
        source="kullanici",
        path=Path("settings.json"),
    )
    assert not skipped
    session = HookSession(root=tmp_path, loader=lambda: HookSet(commands))

    async def run() -> None:
        notify_auth_success(session, "meta")
        while session._background:
            await asyncio.gather(*list(session._background))

    asyncio.run(run())
    payload = json.loads(log.read_text())
    assert payload["notification_type"] == "auth_success"
    assert payload["title"] == "Fusion"
    assert "meta" in payload["message"]
