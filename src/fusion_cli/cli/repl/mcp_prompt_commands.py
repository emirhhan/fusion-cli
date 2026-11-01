"""MCP istemlerinin slash komutları ve `/mcp prompts|resources` listeleri (P-049).

Bağlı sunucunun her istemi menüde `/<sunucu>:<istem> (MCP)` olarak "MCP" grubunda sunulur;
`/mcp__<sunucu>__<istem>` yazmak da çalışır (Claude Code, #268). İşleyici turu ÇALIŞTIRMAZ (makro sözleşmesi): satırı bekleyen görev yapar; tur
yürütücüsü MCP bağlandıktan sonra istemi `prompts/get` ile çözer (`mcp_bridge.reference_service`).
Katalog bağlantı kurulunca dolar: sunucu henüz hiç bağlanmadıysa ilk turdan sonra görünür.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ...ui import messages
from .state import ReplState

if TYPE_CHECKING:
    from ...mcp_bridge.references import McpPrompt
    from .commands import SlashCommand

#: `mcp_bridge.references.SLASH_PREFIX` ile aynı (o modül `mcp` paketini içe aktarır).
SLASH_PREFIX = "mcp__"

#: Yardım/tamamlama grubu.
GROUP = "MCP"
#: Menüde istem adının yanındaki ek (Claude Code `/servername:promptname (MCP)`).
MENU_SUFFIX = "(MCP)"
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


def _known_prompts() -> tuple[McpPrompt, ...]:
    from ...mcp_bridge.references import McpCatalog, visible_prompts

    return visible_prompts(
        [
            prompt
            for catalog in _catalogs().values()
            if isinstance(catalog, McpCatalog)
            for prompt in catalog.prompts
        ]
    )


def _prompt_command(prompt: McpPrompt) -> SlashCommand:
    from .commands import SlashCommand

    summary = " ".join(prompt.description.split())[:_SUMMARY_CHARS]
    text = summary or messages.MCP_PROMPT_DEFAULT.format(server=prompt.server)
    return SlashCommand(
        prompt.display_name,
        f"{text} {MENU_SUFFIX}",
        prompt_handler(prompt.slash_name),
        aliases=(prompt.slash_name,),
        group=GROUP,
        usage=prompt.usage,
    )


def mcp_prompt_slash_commands() -> tuple[object, ...]:
    """Bilinen MCP istemleri için `SlashCommand`'lar (katalog boşsa hiç)."""
    return tuple(_prompt_command(prompt) for prompt in _known_prompts())


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
            for prompt in _known_prompts()
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
    from ...mcp_bridge.references import find_prompt
    from .commands import SlashCommand

    known = find_prompt(_known_prompts(), name) if (":" in name or SLASH_PREFIX in name) else None
    if known is not None:  # menü adı dinamik komutta; `/mcp__…` yazımı buraya düşer
        return _prompt_command(known)
    if not name.startswith(SLASH_PREFIX) or len(name) <= len(SLASH_PREFIX):
        return None

    def _handler(state: ReplState, argument: str) -> str:
        if not state.config.mcp_servers:
            return messages.REPL_UNKNOWN_COMMAND.format(name=name)
        state.pending_task = f"/{name} {argument}".strip()
        return messages.MCP_PROMPT_UNLISTED_QUEUED.format(name=name)

    return SlashCommand(name, messages.MCP_PROMPT_UNLISTED, _handler, group=GROUP)
