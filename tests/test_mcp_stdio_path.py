"""Finder'dan açılan uygulamada stdio MCP komutları bulunur (WP11).

macOS, Finder/Dock'tan açılan uygulamalara kabuğun PATH'ini vermez; çekirdek
`/usr/bin:/bin:/usr/sbin:/sbin` ile başlar. SDK komutu bu PATH'te arar: `npx`/`uvx`
Homebrew'da (`/opt/homebrew/bin`) kurulu olsa da `FileNotFoundError` olur ve
kullanıcıya "Node.js kurulu değil" denirdi. `npx` betiği ayrıca `#!/usr/bin/env node`
ile başladığından komutun tam yolu da yetmez: PATH'in kendisi genişletilmelidir.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge import transport as transport_module
from fusion_cli.mcp_bridge.transport import stdio_search_path

_FINDER_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def test_finder_pathine_yaygin_kurulum_yerleri_eklenir():
    path = stdio_search_path({"PATH": _FINDER_PATH}, home=Path("/Users/ornek"))
    parts = path.split(":")

    assert parts[:4] == _FINDER_PATH.split(":"), "mevcut sıra korunur"
    for beklenen in ("/opt/homebrew/bin", "/usr/local/bin", "/Users/ornek/.local/bin"):
        assert beklenen in parts
    assert len(parts) == len(set(parts)), "aynı dizin iki kez eklenmez"


def test_kabuktan_gelen_path_one_alinir_tekrar_eklenmez():
    path = stdio_search_path({"PATH": "/opt/homebrew/bin:/usr/bin"}, home=Path("/Users/ornek"))

    assert path.startswith("/opt/homebrew/bin:/usr/bin:")
    assert path.split(":").count("/opt/homebrew/bin") == 1


async def test_stdio_sureci_genisletilmis_path_ile_baslar(monkeypatch):
    kaydedilen = {}

    @asynccontextmanager
    async def fake_stdio(params, errlog=None):
        kaydedilen["env"] = params.env
        yield None, None

    monkeypatch.setattr(transport_module, "stdio_client", fake_stdio)
    monkeypatch.setenv("PATH", _FINDER_PATH)
    config = McpServerConfig(name="yerel", transport=McpTransport.STDIO, command="npx")

    async with transport_module.open_mcp_stream(config):
        pass

    assert "/opt/homebrew/bin" in kaydedilen["env"]["PATH"].split(":")
