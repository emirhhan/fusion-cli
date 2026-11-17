"""Re-expand original tool constraints as a turn's real MCP catalog changes.

An initial projection is a snapshot, never a new authority ceiling. Parent
constraints remain a separate intersection and are evaluated on the same registry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from weakref import WeakKeyDictionary

from ...core.mcp_tool_names import canonical_mcp_name, cold_mcp_alias_matches_server, mcp_server_of
from ...tools.capabilities import expand_tool_patterns

if TYPE_CHECKING:
    from ...core.tools import Tool
    from ...mcp_bridge.references import McpExpansion
    from ...tools.registry import ToolRegistry
    from .loop import AgentDeps

DISCOVER_MCP_TOOLS = "DiscoverMcpTools"


@dataclass(frozen=True, slots=True)
class RuntimeToolSurface:
    task: str = ""
    allowed: frozenset[str] | None = None
    denied: frozenset[str] = frozenset()
    parent: RuntimeToolSurface | None = None
    fixed_names: frozenset[str] | None = None
    project: Callable[[ToolRegistry], set[str] | None] | None = None
    server_filter: frozenset[str] = frozenset()
    admission_caps: tuple[frozenset[str], ...] = ()
    validate: Callable[[ToolRegistry], set[str]] | None = None

    def names(self, registry: ToolRegistry) -> set[str]:
        available = registry.names()
        names = (
            set(available)
            if self.allowed is None
            else expand_tool_patterns(set(self.allowed), available) & set(available)
        )
        if self.validate is not None:
            names &= self.validate(registry)
        if self.project is not None:
            projected = self.project(registry)
            if projected is not None:
                names &= projected
        if self.parent is not None:
            names &= self.parent.names(registry)
        if self.fixed_names is not None:
            names &= expand_tool_patterns(set(self.fixed_names), available)
        names -= expand_tool_patterns(set(self.denied), available)
        if self.server_filter:
            names = {
                name
                for name in names
                if not registry.is_remote(name)
                or mcp_server_of(canonical_mcp_name(name)) in self.server_filter
                or (
                    selected_metadata_servers(registry.get(name))
                    and all(
                        self.admit(server, registry)
                        for server in selected_metadata_servers(registry.get(name))
                    )
                )
            }
        return names

    def preflight_patterns(self) -> frozenset[str]:
        patterns = set(self.allowed or ())
        for cap in self.admission_caps:
            patterns.update(cap)
        if self.parent is not None:
            patterns.update(self.parent.preflight_patterns())
        return frozenset(patterns)

    def explicit_names(self, registry: ToolRegistry) -> set[str] | None:
        """Retain explicit selections without calling every projected name explicit."""
        caps = [cap for cap in (self.allowed, *self.admission_caps) if cap is not None]
        parent = self.parent.explicit_names(registry) if self.parent is not None else None
        if not caps and parent is None:
            return None
        selected = set() if parent is None else parent
        for cap in caps:
            selected |= expand_tool_patterns(set(cap), registry.names())
        return selected & self.names(registry)

    def admit(self, server: str, registry: ToolRegistry | None = None) -> bool:
        if self.parent is not None and not self.parent.admit(server, registry):
            return False
        if self.server_filter and server not in self.server_filter:
            return False
        if {f"mcp__{server}__*", f"{server}__*", f"mcp__{server}"} & set(self.denied):
            return False
        for cap in (self.allowed, self.fixed_names, *self.admission_caps):
            if cap is None:
                continue
            # Explicit discovery permits selecting a service, but never bypasses
            # a separate parent cap, server filter, or execution-name cap.
            if DISCOVER_MCP_TOOLS in cap:
                continue
            if not any(
                (
                    mcp_server_of(canonical_mcp_name(name)) == server
                    or cold_mcp_alias_matches_server(name, server)
                )
                and not (
                    registry is not None
                    and any(
                        not registry.is_remote(candidate)
                        and canonical_mcp_name(candidate) == canonical_mcp_name(name)
                        for candidate in registry.names()
                    )
                )
                for name in cap
            ):
                return False
        return True


class McpDiscovery(Protocol):
    async def preflight_selected(
        self,
        registry: ToolRegistry,
        patterns: frozenset[str],
        *,
        task: str,
        permitted: Callable[[], set[str]],
        admit: Callable[[str], bool],
        deps: AgentDeps,
    ) -> McpExpansion: ...

    def permitted_names(self, registry: ToolRegistry) -> set[str]: ...

    def bind(
        self,
        registry: ToolRegistry,
        *,
        permitted: Callable[[], set[str]],
        admit: Callable[[str], bool],
        deps: AgentDeps,
        selected_admit: Callable[[str], bool] | None = None,
    ) -> Tool: ...


_SURFACES: WeakKeyDictionary[ToolRegistry, RuntimeToolSurface] = WeakKeyDictionary()
_TASKS: WeakKeyDictionary[ToolRegistry, str] = WeakKeyDictionary()


def bind_surface(registry: ToolRegistry, surface: RuntimeToolSurface) -> None:
    _SURFACES[registry] = surface
    _TASKS[registry] = surface.task


def surface_for(registry: ToolRegistry) -> RuntimeToolSurface | None:
    return _SURFACES.get(registry)


def selected_metadata_servers(tool: Tool | None) -> tuple[str, ...]:
    """Trusted local executor scope, never a remote schema annotation or tool name guess."""
    if tool is None or tool.name != "WaitForMcpServers":
        return ()
    servers = getattr(tool.run, "mcp_selected_servers", ())
    if not isinstance(servers, tuple) or not servers:
        return ()
    if not all(isinstance(server, str) and server for server in servers):
        return ()
    return servers


def update_surface_task(registry: ToolRegistry, task: str) -> None:
    if registry in _SURFACES:
        _TASKS[registry] = task


def surface_task(registry: ToolRegistry) -> str:
    return _TASKS.get(registry, "")
