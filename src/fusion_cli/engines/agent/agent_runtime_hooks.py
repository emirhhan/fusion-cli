"""Ajan dosyasının güven sınırını ve kanca ömrünü koruyan birleşim."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ...core.errors import ConfigError
from ...core.hooks.events import HookEvent, HookSet
from ..hooks.session import HookSession

if TYPE_CHECKING:
    from .loop import AgentDeps
    from .team import Persona, SubTask


def trusted_definition(deps: AgentDeps, persona: Persona) -> bool:
    from .team_settings import is_trusted_agent_definition

    return is_trusted_agent_definition(
        deps.config, persona, root=deps.tool_context.root, home=deps.home
    )


def scoped_hooks(
    deps: AgentDeps, persona: Persona, *, child: bool, identifier: str = ""
) -> HookSession | None:
    base = deps.definition_base_hooks if child and deps.main_metadata_applied else deps.hooks
    local = persona.hook_definitions if trusted_definition(deps, persona) else HookSet()
    if base is None and not local.commands and not local.skipped:
        return None
    if child:
        local = replace(
            local,
            commands=tuple(
                replace(command, event=HookEvent.SUBAGENT_STOP)
                if command.event is HookEvent.STOP
                else command
                for command in local.commands
            ),
        )

    original = base.loader if base is not None else HookSet
    if isinstance(original, DefinitionHookLoader):
        original = original.base
    loader = DefinitionHookLoader(original, local)
    if base is None:
        return HookSession(
            deps.tool_context.root, loader=loader, conversation_id=deps.conversation_id
        )
    if not child:
        # Aynı oturumun SessionStart/End durumu korunur; bir sonraki tur yalnız tanımı yeniler.
        base.loader = loader
        base.refresh()
        return base
    return replace(
        base,
        loader=loader,
        hooks=HookSet(),
        _loaded=False,
        session_id=identifier or base.session_id,
        _deferred=[],
        _pending_end=None,
    )


@dataclass(frozen=True, slots=True)
class DefinitionHookLoader:
    """Küresel yükleyiciyi kaybetmeden tek aktif ajan tanımını bağla."""

    base: Callable[[], HookSet]
    local: HookSet

    def __call__(self) -> HookSet:
        inherited = self.base()
        return replace(
            inherited,
            commands=(*inherited.commands, *self.local.commands),
            skipped=(*inherited.skipped, *self.local.skipped),
        )


def prepare_main_metadata(deps: AgentDeps) -> None:
    persona = deps.session_persona
    if persona is None or deps.main_metadata_applied:
        return
    from . import team_settings
    from .agent_launch_runtime import prepare_main_agent

    prepare_main_agent(deps, persona)
    deps.definition_base_hooks = deps.hooks
    deps.hooks = scoped_hooks(deps, persona, child=False)
    if persona.memory_scope:
        deps.plain_memory = team_settings.child_memory(deps, persona)
        # Claude Code: ajan belleği Read/Write/Edit ile yönetilir; dizin dosya araçlarına açık.
        deps.tool_context = team_settings.with_memory_roots(deps.tool_context, deps.plain_memory)
        deps.lesson_owner = persona.name
    deps.allowed_agent_types = persona.allowed_agent_types
    deps.prompt_cache_ttl = getattr(persona, "cache_ttl", "") or ""
    deps.main_metadata_applied = True


@asynccontextmanager
async def child_mcp_scope(deps: AgentDeps, persona: Persona, task: SubTask) -> AsyncIterator[None]:
    """Inline sunucu yalnız güvenilmiş tanım ve izinli araç kapsamıyla açılır."""
    from . import team_settings
    from .engine_tools import _clone

    servers = persona.inline_mcp_servers
    if not servers or not trusted_definition(deps, persona):
        yield
        return
    for names in (persona.tools, task.tool_cap):
        if names is not None:
            servers = tuple(
                server
                for server in servers
                if any(name.startswith(server.name + "__") or name == "*" for name in names)
            )
    denied = persona.disallowed_tools | task.tool_deny
    servers = tuple(
        server for server in servers if "*" not in denied and f"{server.name}__*" not in denied
    )
    if not servers:
        yield
        return
    if deps.mcp_connector is None:
        raise ConfigError(
            "Inline MCP için oturum bağlantı hizmeti gerekli; "
            "ajanı CLI veya oturum üzerinden başlatın."
        )
    assert deps.base_registry is not None
    deps.base_registry = _clone(deps.base_registry)
    configured = team_settings.agent_mcp_config(
        deps.config,
        replace(persona, inline_mcp_servers=servers),
        root=deps.tool_context.root,
        home=deps.home,
    )
    server_names = {server.name for server in servers}
    isolated = replace(
        configured,
        mcp_servers=tuple(
            server for server in configured.mcp_servers if server.name in server_names
        ),
    )
    async with deps.mcp_connector(isolated, deps.base_registry):
        deps.config = configured
        yield
