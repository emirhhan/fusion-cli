"""`fusion mcp prompts` ve `fusion mcp resources`: sunucuların istem/kaynak listesi (P-049).

Bağlanır, `prompts/list` / `resources/list` çeker ve yazdırır; REPL'de `/mcp prompts` aynı
katalogu oturum havuzundan gösterir. İstem `/mcp__<sunucu>__<istem>` olarak, kaynak
`@<sunucu>:<uri>` olarak kullanılır.
"""

from __future__ import annotations

from rich.markup import escape

from ..config.loader import load_config
from ..ui import messages, theme


def prompts() -> None:
    """Yapılandırılmış MCP sunucularının istemlerini listele (bağlanır)."""
    _print_catalogs(kind="prompts")


def resources() -> None:
    """Yapılandırılmış MCP sunucularının kaynaklarını listele (bağlanır)."""
    _print_catalogs(kind="resources")


def _print_catalogs(*, kind: str) -> None:
    # Aynı sınır katmanı ve konsol (zaman aşımı, Türkçe hata); döngüsel içe aktarma tembel.
    from .mcp_commands import MCP_TOOLS_TIMEOUT_S, _run_connected, console

    config = load_config()
    if not config.mcp_servers:
        console.print(messages.MCP_NO_SERVERS)
        return
    from ..mcp_bridge.client import McpClient
    from ..mcp_bridge.references import visible_prompts, visible_resources

    async def _run() -> None:
        async with McpClient(config.mcp_servers) as client:
            for server in client.servers:
                catalog = await client.catalog(server)
                resources = visible_resources(catalog.resources)
                items = catalog.prompts if kind == "prompts" else resources
                console.print(f"[bold]{escape(server)}[/bold] — {len(items)}")
                for prompt in visible_prompts(catalog.prompts) if kind == "prompts" else ():
                    console.print(
                        f"  [{theme.ACCENT}]/{escape(prompt.slash_name)}[/{theme.ACCENT}] "
                        f"{escape(prompt.usage)} — {escape(prompt.description)}"
                    )
                for resource in resources if kind == "resources" else ():
                    console.print(
                        f"  [{theme.ACCENT}]@{escape(server)}:{escape(resource.uri)}"
                        f"[/{theme.ACCENT}] — {escape(resource.name or resource.description)}"
                    )

    _run_connected(
        _run,
        timeout_s=MCP_TOOLS_TIMEOUT_S,
        timeout_message=messages.MCP_TOOLS_TIMEOUT.format(seconds=MCP_TOOLS_TIMEOUT_S),
    )
