"""MCP köprüsü — sunucu + istemci uçtan uca (gerçek stdio alt-süreç).

Fusion'ın KENDİ MCP sunucusunu bir alt-süreç olarak başlatır ve McpClient ile bağlanır:
tek testte HEM sunucu (araçları dışa açar) HEM istemci (bağlanıp kullanır) doğrulanır.
Ağ yok; her şey yerel stdio.
"""

from __future__ import annotations

import sys

from fusion_cli.config.models import McpServerConfig
from fusion_cli.mcp_bridge.client import McpClient
from fusion_cli.mcp_bridge.server import build_server


def _server_config(root):
    # Fusion'ın MCP sunucusunu venv python'uyla alt-süreç olarak başlat.
    return McpServerConfig(
        name="fusion",
        command=sys.executable,
        args=("-m", "fusion_cli.mcp_bridge.server", str(root)),
    )


# --- sunucu (birim) -------------------------------------------------------- #


def test_sunucu_kurulur():
    server = build_server(root=".")  # type: ignore[arg-type]
    assert server.name == "fusion"


# --- uçtan uca: sunucu + istemci ------------------------------------------- #


async def test_ustten_uca_baglan_listele_cagir(tmp_path):
    (tmp_path / "ornek.txt").write_text("selam", encoding="utf-8")

    async with McpClient([_server_config(tmp_path)]) as client:
        tools = await client.list_tools("fusion")
        adlar = {t.name for t in tools}
        # Salt-okunur araçlar açılır; değiştirici araçlar (write_file) AÇILMAZ.
        assert "list_dir" in adlar
        assert "read_file" in adlar
        assert "write_file" not in adlar

        # Uzak aracı gerçekten çağır.
        cikti = await client.call("fusion", "list_dir", {"path": "."})
        assert "ornek.txt" in cikti


async def test_register_into_araclari_kayit_defterine_ekler(tmp_path):
    from fusion_cli.tools import ToolRegistry

    registry = ToolRegistry()
    async with McpClient([_server_config(tmp_path)]) as client:
        eklenen = await client.register_into(registry)

    # Araçlar <sunucu>__<araç> biçiminde ve mutating (onay akışına girsin) eklenir.
    assert any(name.startswith("fusion__") for name in eklenen)
    tool = registry.get("fusion__list_dir")
    assert tool is not None
    assert tool.mutating is True
