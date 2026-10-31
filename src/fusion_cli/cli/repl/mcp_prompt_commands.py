"""MCP istemlerinin slash komutları ve `/mcp prompts|resources` listeleri (P-049).

Bağlı sunucunun her istemi `/mcp__<sunucu>__<istem>` olarak "MCP" grubunda sunulur (Claude
Code yazımı). İşleyici turu ÇALIŞTIRMAZ (makro sözleşmesi): satırı bekleyen görev yapar; tur
yürütücüsü MCP bağlandıktan sonra istemi `prompts/get` ile çözer (`mcp_bridge.reference_service`).
Katalog bağlantı kurulunca dolar: sunucu henüz hiç bağlanmadıysa ilk turdan sonra görünür.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ...ui import messages
from .state import ReplState

if TYPE_CHECKING:
    from .commands import SlashCommand

#: `mcp_bridge.references.SLASH_PREFIX` ile aynı (o modül `mcp` paketini içe aktarır).
SLASH_PREFIX = "mcp__"

#: Yardım/tamamlama grubu.
GROUP = "MCP"
#: Listede açıklamanın en fazla uzunluğu.
_SUMMARY_CHARS = 72


def _catalogs() -> dict[str, object]:
    try:
        from ...mcp_bridge.pool import mcp_catalogs
    except ImportError:  # `mcp` paketi kurulu değil: istem yok
        return {}
    return dict(mcp_catalogs())


def prompt_handler(name: str) -> Callable[[ReplState, str], str]:
    def _handler(state: ReplState, argument: str) -> str:
        state.pending_task = f"/{name} {argument}".strip()
        return messages.MCP_PROMPT_QUEUED.format(name=name)

    return _handler


def mcp_prompt_slash_commands() -> tuple[object, ...]:
    """Bilinen MCP istemleri için `SlashCommand`'lar (katalog boşsa hiç)."""
    from ...mcp_bridge.references import McpCatalog
    from .commands import SlashCommand

    commands: list[SlashCommand] = []
    for catalog in _catalogs().values():
        if not isinstance(catalog, McpCatalog):
            continue
        for prompt in catalog.prompts:
            summary = " ".join(prompt.description.split())[:_SUMMARY_CHARS]
            commands.append(
                SlashCommand(
                    prompt.slash_name,
                    summary or messages.MCP_PROMPT_DEFAULT.format(server=prompt.server),
                    prompt_handler(prompt.slash_name),
                    group=GROUP,
                    usage=prompt.usage,
                )
            )
    return tuple(commands)


def listing(kind: str) -> str:
    """`/mcp prompts` ya da `/mcp resources` metni."""
    from ...mcp_bridge.references import McpCatalog

    catalogs = {
        server: catalog
        for server, catalog in _catalogs().items()
        if isinstance(catalog, McpCatalog)
    }
    if kind in ("prompts", "istemler"):
        rows = [
            messages.MCP_PROMPT_ROW.format(
                name=prompt.slash_name, usage=prompt.usage, description=prompt.description
            ).rstrip(" —")
            for catalog in catalogs.values()
            for prompt in catalog.prompts
        ]
        return "\n".join(rows) if rows else messages.MCP_PROMPTS_EMPTY
    rows = [
        messages.MCP_RESOURCE_ROW.format(
            server=resource.server, uri=resource.uri, name=resource.name or resource.description
        ).rstrip(" —")
        for catalog in catalogs.values()
        for resource in catalog.resources
    ]
    return "\n".join(rows) if rows else messages.MCP_RESOURCES_EMPTY


def unlisted_prompt_command(name: str) -> SlashCommand | None:
    """Katalogda olmayan `/mcp__…` için geçici komut: görev sıradaki turda çözülür.

    Ölçüldü (31 Ekim): katalog yalnız ilk agent turunda bağlantı kurulunca doluyordu; taze
    REPL'de `/mcp__github__review-pr 12` "bilinmeyen komut" alıyordu. Tur yürütücüsü önce
    bağlanır, sonra istemi çözer (`reference_service.expand_mcp_references`); bulunamazsa
    model çağrılmadan "MCP istemi bulunamadı" denir.
    """
    from .commands import SlashCommand

    if not name.startswith(SLASH_PREFIX) or len(name) <= len(SLASH_PREFIX):
        return None

    def _handler(state: ReplState, argument: str) -> str:
        if not state.config.mcp_servers:
            return messages.REPL_UNKNOWN_COMMAND.format(name=name)
        state.pending_task = f"/{name} {argument}".strip()
        return messages.MCP_PROMPT_UNLISTED_QUEUED.format(name=name)

    return SlashCommand(name, messages.MCP_PROMPT_UNLISTED, _handler, group=GROUP)
