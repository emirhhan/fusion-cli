"""MCP kaynakları Claude Code gibi: `@` tamamlamada dosyalarla birlikte, sınırsız anma (#254).

Belge (code.claude.com/docs/en/mcp, "Use MCP resources"): `@` yazınca bağlı sunucuların
kaynakları dosyalarla birlikte bulanık aramalı tamamlamada görünür; birden çok kaynak anılabilir;
`ui://` ve `text/html;profile=mcp-app` kaynakları önerilerde ve liste aracında görünmez, URI ile
okunabilir.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from fusion_cli.cli.repl.completion import ReplCompleter
from fusion_cli.config.models import McpServerConfig
from fusion_cli.mcp_bridge import pool as pool_module
from fusion_cli.mcp_bridge import reference_service
from fusion_cli.mcp_bridge.references import (
    McpCatalog,
    McpResource,
    resource_block,
    visible_resources,
)

KAYNAKLAR = (
    McpResource("github", "repo://fusion/readme", name="README"),
    McpResource("github", "ui://panel"),
    McpResource("github", "app://x", mime_type="text/html;profile=mcp-app"),
)


def test_ui_ve_mcp_app_kaynaklari_gizlenir():
    assert visible_resources(KAYNAKLAR) == (KAYNAKLAR[0],)


def test_at_tamamlama_kaynaklari_bulanik_onerir(tmp_path: Path, monkeypatch):
    (tmp_path / "readme.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        pool_module, "mcp_catalogs", lambda: {"github": McpCatalog(resources=KAYNAKLAR)}
    )
    completer = ReplCompleter([], (tmp_path,))

    shown = [
        item.text
        for item in completer.get_completions(Document("bak @ghread"), CompleteEvent())
    ]
    files = [
        item.text for item in completer.get_completions(Document("bak @read"), CompleteEvent())
    ]

    assert shown == ["@github:repo://fusion/readme"]
    assert "@readme.md" in files and "@github:repo://fusion/readme" in files
    assert not any("ui://" in text or "app://" in text for text in files)


async def test_bes_anma_siniri_yok(monkeypatch):
    class _Bagli:
        async def read_resource(self, server: str, uri: str) -> str:
            return f"<{uri}>"

    client = _Bagli()
    monkeypatch.setattr(reference_service, "mcp_catalogs", lambda: {})
    monkeypatch.setattr(reference_service, "connected_mcp_client", lambda name: client)
    task = " ".join(f"@github:r://{n}" for n in range(8))

    expansion = await reference_service.expand_mcp_references(
        task, (McpServerConfig(name="github", command="npx"),)
    )

    assert len(expansion.resources) == 8 and not expansion.warnings


def test_kaynak_govdesi_20k_ile_kirpilmaz():
    body = "x" * 30_000
    block = resource_block("s", "r://a", SimpleNamespace(contents=[SimpleNamespace(text=body)]))

    assert body in block and "kırpıldı" not in block
