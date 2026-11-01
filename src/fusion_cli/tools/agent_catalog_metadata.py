"""Ajan frontmatter'ındaki tiplenmiş çalışma verisini kaynak kimliğine bağla."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from ..config.models import McpServerConfig
from ..core.hooks.events import HookSet

if TYPE_CHECKING:
    from .capabilities import Capability


def bind_agent_source(capability: Capability, source: str) -> Capability:
    """CLI gibi dosyasız tanımın kanca kaynağını da açık kapsamına bağla."""
    updated = replace(capability, source=source)
    return replace(updated, hook_definitions=_bound_hooks(updated.hook_definitions, updated))


def _bound_hooks(hook_set: HookSet, capability: Capability) -> HookSet:
    return replace(
        hook_set,
        commands=tuple(
            replace(item, source=capability.source, path=str(capability.path))
            for item in hook_set.commands
        ),
        skipped=tuple(
            replace(item, source=capability.source, path=str(capability.path))
            for item in hook_set.skipped
        ),
    )


def _int_field(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def apply_agent_metadata(capability: Capability, fields: Mapping[str, object]) -> Capability:
    """Ayrıştırılmış kancayı bağla; eklenti ajanının desteklenmeyen alanlarını çıkar."""
    hooks = fields.get("hook_definitions")
    hook_set = hooks if isinstance(hooks, HookSet) else HookSet()
    servers = fields.get("inline_mcp_servers")
    inline_servers = (
        tuple(item for item in servers if isinstance(item, McpServerConfig))
        if isinstance(servers, tuple)
        else ()
    )
    updated = replace(
        capability,
        initial_prompt=str(fields.get("initial_prompt") or ""),
        omit_claude_md=fields.get("omit_claude_md") is True,
        auto_compact_window=_int_field(fields.get("auto_compact_window")),
        cache_ttl=str(fields.get("cache_ttl") or ""),
        hook_definitions=_bound_hooks(hook_set, capability),
        inline_mcp_servers=inline_servers,
    )
    if capability.source == "eklenti":
        return replace(
            updated,
            permission_mode="",
            hooks=(),
            hook_definitions=HookSet(),
            mcp_servers=(),
            inline_mcp_servers=(),
            initial_prompt="",
        )
    return updated
