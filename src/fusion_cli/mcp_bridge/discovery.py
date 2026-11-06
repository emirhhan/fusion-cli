"""Turn-owned MCP admission. Building/listing the catalog never opens a session.

Connection ownership remains in the pool. Discovery stages real client definitions
before publishing atomically into the requesting runtime, after rechecking admission.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Collection, Iterable, Iterator, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Literal, cast

from ..config.models import Config, HostedConnectorConfig, McpScope, McpServerConfig
from ..core.mcp_tool_names import (
    canonical_mcp_name,
    claude_mcp_tool_name,
    cold_mcp_alias_matches_server,
)
from ..core.tools import Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from ..tools.registry import ToolRegistry
from ..tools.tool_search import (
    ToolSearchState,
    prioritize_tools,
    refresh_tool_search,
    tool_search_state,
)
from .identity import unique_configs, unique_hosted_configs
from .reference_syntax import McpExpansion, parse_prompt_call, resource_mentions

if TYPE_CHECKING:
    from ..engines.agent.loop import AgentDeps
    from .pool import McpToolPool

DISCOVER_MCP_TOOLS = "DiscoverMcpTools"
WAIT_FOR_MCP_SERVERS = "WaitForMcpServers"
_SAFE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_MAX_CATALOG = 100
_MAX_RESULTS = 12
ServerConfig = McpServerConfig | HostedConnectorConfig
Kind = Literal["mcp", "hosted"]
Stage = Literal[
    "catalog_preparation",
    "selected_connection_wait",
    "selected_schema_discovery",
    "runtime_publication",
    "explicit_reference_expansion",
]


def reference_servers(task: str, configs: Sequence[McpServerConfig]) -> frozenset[str]:
    """Only explicit reference syntax selects a server, never task keywords."""
    names = [c.name for c in configs]
    selected = {server for server, _ in resource_mentions(task, names)}
    call = parse_prompt_call(task)
    if call:
        for name in names:
            if call[0].startswith(claude_mcp_tool_name(name, "")):
                selected.add(name)
    return frozenset(selected)


class AmbiguousMcpAliasError(ValueError):
    def __init__(self, servers: Collection[str]) -> None:
        self.servers = frozenset(servers)
        super().__init__("Ambiguous cold MCP alias.")


def requested_servers(
    patterns: Iterable[str] | None,
    configs: Sequence[ServerConfig],
    registry: ToolRegistry,
    *,
    eligible: Callable[[str], bool] | None = None,
    allow_ambiguous: bool = False,
) -> frozenset[str]:
    """Resolve explicit canonical/legacy patterns against configured identifiers.

    A registered builtin takes precedence over MCP-looking syntax (Chrome aliases).
    """
    selected = set()
    local_aliases = {
        canonical_mcp_name(name) for name in registry.names() if not registry.is_remote(name)
    }
    for pattern in patterns or ():
        canonical = canonical_mcp_name(pattern)
        if canonical in local_aliases:
            continue
        candidates = set()
        for config in configs:
            prefix = claude_mcp_tool_name(config.name, "")
            if canonical.startswith(prefix) or canonical == prefix.removesuffix("__"):
                if eligible is None or eligible(config.name):
                    selected.add(config.name)
            elif cold_mcp_alias_matches_server(pattern, config.name) and (
                eligible is None or eligible(config.name)
            ):
                candidates.add(config.name)
        if len(candidates) > 1 and not allow_ambiguous:
            raise AmbiguousMcpAliasError(candidates)
        selected.update(candidates)
    return frozenset(selected)


class McpDiscovery:
    """A catalog and publication lease for one outer turn, shared by child runtimes."""

    def __init__(
        self,
        config: Callable[[], Config],
        *,
        root: Path | None = None,
        pool: McpToolPool | None = None,
        parent: McpDiscovery | None = None,
    ) -> None:
        self._config = config
        self.root = root
        self._closed = False
        self.pool = pool
        self.parent = parent
        self._locks: dict[str, asyncio.Lock] = {}
        self._published: dict[tuple[int, str], set[str]] = {}
        self._owners: dict[tuple[int, str], tuple[Kind, ServerConfig]] = {}
        self._origins: dict[str, tuple[Kind, ServerConfig, object]] = {}
        self._states: dict[tuple[Kind, str], tuple[ServerConfig, str]] = {}
        self._pending: dict[str, tuple[Kind, McpServerConfig, str]] = {}

    @property
    def closed(self) -> bool:
        return self._closed or bool(self.parent is not None and self.parent.closed)

    @property
    def has_catalog(self) -> bool:
        config = self._config()
        return bool(config.mcp_servers or config.hosted_connectors)

    def close(self) -> None:
        # No detached registry jobs are started. Pool-owned transports may stay warm.
        self._closed = True

    def _entries(self) -> list[tuple[str, Kind, ServerConfig]]:
        config = self._config()
        servers = unique_configs(config.mcp_servers)
        hosted = unique_hosted_configs(config.hosted_connectors)
        used: set[str] = set()
        entries: list[tuple[str, Kind, ServerConfig]] = []
        groups: tuple[tuple[Kind, Sequence[ServerConfig]], ...] = (
            ("mcp", servers),
            ("hosted", hosted),
        )
        for kind, items in groups:
            for item in items:
                candidate = (
                    item.name if _SAFE_ID.fullmatch(item.name) else f"service-{len(entries) + 1}"
                )
                suffix = 1
                while candidate in used:
                    candidate = f"service-{len(entries) + 1}-{suffix}"
                    suffix += 1
                used.add(candidate)
                entries.append((candidate, kind, item))
        return entries

    def catalog(
        self, admit: Callable[[str], bool] = lambda _: True, query: str = ""
    ) -> list[dict[str, str]]:
        return [
            {
                "server": safe,
                "kind": kind,
                "status": self._status(kind, item),
                "capabilities": "unknown",
            }
            for safe, kind, item in self._entries()
            if admit(item.name) and (not query or query.lower() in safe.lower())
        ][:_MAX_CATALOG]

    def ambiguity_message(self, error: AmbiguousMcpAliasError) -> str:
        safe = [name for name, _, item in self._entries() if item.name in error.servers][
            :_MAX_RESULTS
        ]
        return (
            "Ambiguous cold MCP alias. Eligible catalog IDs: "
            + ", ".join(safe)
            + ". Select one server explicitly for discovery "
            "or use its full canonical MCP tool name."
        )

    def _status(self, kind: Kind, item: ServerConfig) -> str:
        known = self._states.get((kind, item.name))
        return known[1] if known is not None and known[0] == item else "not_activated"

    def _current(self, kind: Kind, selected: ServerConfig) -> ServerConfig | None:
        return next(
            (item for _, k, item in self._entries() if k == kind and item == selected), None
        )

    def _capture_clone(self, registry: ToolRegistry) -> None:
        """Preserve exact source/config identity when a runtime copies preflight tools."""
        origins = dict(self.parent._origins) if self.parent is not None else {}
        origins.update(self._origins)
        for tool in registry:
            origin = origins.get(tool.name)
            if origin is None or origin[2] is not tool.run or not registry.is_remote(tool.name):
                continue
            kind, selected, _executor = origin
            key = (id(registry), selected.name)
            self._owners.setdefault(key, (kind, selected))
            self._published.setdefault(key, set()).add(tool.name)

    def permitted_names(self, registry: ToolRegistry) -> set[str]:
        """Local config-generation check for every schema/executor projection."""
        names = set(registry.names())
        for key, (kind, selected) in self._owners.items():
            if key[0] == id(registry) and (self.closed or self._current(kind, selected) is None):
                names -= self._published.get(key, set())
        return names

    def _admitted(self, kind: Kind, selected: ServerConfig) -> bool:
        """Re-read existing organization/project gates only for explicit admission."""
        import os

        from ..config.mcp_policy import filter_hosted_connectors, filter_servers, load_policy

        if self._current(kind, selected) is None:
            return False
        root = self.root or Path.cwd()
        policy = load_policy(root)
        if isinstance(selected, HostedConnectorConfig):
            return selected in filter_hosted_connectors((selected,), policy, os.environ)
        if selected not in filter_servers(self._config().mcp_servers, policy, os.environ):
            return False
        if selected.scope is McpScope.PROJECT:
            from ..config.mcp_project_approval import (
                APPROVED,
                _file_trusted,
                decide,
                load_approval_settings,
            )

            return (
                decide(
                    selected.name, load_approval_settings(root), file_trusted=_file_trusted(root)
                )
                == APPROVED
            )
        return True

    @contextmanager
    def phase(self, deps: AgentDeps, stage: Stage, count: int) -> Iterator[None]:
        from ..core.events import McpDiscoveryDiagnostic

        started = monotonic()
        outcome: Literal["ready", "cancelled", "error"] = "ready"
        try:
            yield
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except BaseException:
            outcome = "error"
            raise
        finally:
            # Diagnostics cannot change admission or tool results.
            with suppress(Exception):
                deps.publisher.publish(
                    McpDiscoveryDiagnostic(
                        stage=stage,
                        elapsed_ms=max(0, int((monotonic() - started) * 1000)),
                        selected_count=count,
                        outcome=outcome,
                    )
                )

    def bind(
        self,
        registry: ToolRegistry,
        *,
        permitted: Callable[[], set[str]],
        admit: Callable[[str], bool],
        deps: AgentDeps,
        selected_admit: Callable[[str], bool] | None = None,
    ) -> Tool:
        self._capture_clone(registry)
        waiting = registry.get(WAIT_FOR_MCP_SERVERS)
        selected = getattr(waiting.run, "mcp_selected_servers", ()) if waiting else ()
        if waiting is not None and registry.is_remote(WAIT_FOR_MCP_SERVERS) and selected:
            source: McpDiscovery | None = self
            pending = None
            while source is not None and pending is None:
                pending = source._pending.get(selected[0])
                source = source.parent
            if pending is not None and self._current(pending[0], pending[1]) is not None:
                self._wait_tool(
                    registry,
                    pending[1],
                    pending[0],
                    pending[2],
                    permitted,
                    selected_admit or admit,
                    deps,
                )
            else:
                registry.unregister_remote(WAIT_FOR_MCP_SERVERS)

        async def effect(args: ToolArgs, context: ToolContext | None) -> ToolEffect:
            return ToolEffect.REMOTE_READ if args.get("server") else ToolEffect.LOCAL

        async def run(args: ToolArgs, context: ToolContext) -> ToolResult:
            if self.closed or context.cancelled.is_set():
                return ToolResult.failure("MCP discovery turn is closed.")
            name = str(args.get("server") or "").strip()
            query = str(args.get("query") or "").strip()[:256]
            if not name:
                with self.phase(deps, "catalog_preparation", 0):
                    return ToolResult(
                        output=json.dumps(
                            {"catalog": self.catalog(admit, query)}, ensure_ascii=False
                        )
                    )
            entry = next((entry for entry in self._entries() if entry[0] == name), None)
            if entry is None:
                return ToolResult.failure(
                    "Select an exact configured server identifier from the local catalog."
                )
            _, kind, selected = entry
            if not admit(selected.name) or not self._admitted(kind, selected):
                return ToolResult.failure("MCP server admission denied.")
            try:
                async with self._locks.setdefault(kind + ":" + selected.name, asyncio.Lock()):
                    return await self._discover(
                        registry,
                        selected,
                        kind,
                        query,
                        context,
                        permitted,
                        admit,
                        deps,
                        wait_admit=selected_admit,
                    )
            except Exception as error:
                # Transport/provider messages may contain secrets or configuration.
                return ToolResult.failure(f"MCP discovery failed ({type(error).__name__}).")

        return Tool(
            name=DISCOVER_MCP_TOOLS,
            description=(
                "List/search the local configured MCP catalog without a server argument. "
                "When a service is relevant, select its exact identifier to discover real tools. "
                "Selection contacts only that service and does not execute business tools. "
                "Query filters selected tools; it never searches other servers. "
                "ToolSearch schema deferral does not initiate connections."
            ),
            parameters={
                "type": "object",
                "properties": {"server": {"type": "string"}, "query": {"type": "string"}},
            },
            run=run,
            mutating=False,
            effect=ToolEffect.REMOTE_READ,
            effect_resolver=effect,
        )

    async def _discover(
        self,
        registry: ToolRegistry,
        selected: ServerConfig,
        kind: Kind,
        query: str,
        context: ToolContext,
        permitted: Callable[[], set[str]],
        admit: Callable[[str], bool],
        deps: AgentDeps,
        *,
        wait_admit: Callable[[str], bool] | None = None,
    ) -> ToolResult:
        from .pool import ensure_hosted_tools, ensure_mcp_tools

        if (
            self.closed
            or context.cancelled.is_set()
            or not admit(selected.name)
            or not self._admitted(kind, selected)
        ):
            return ToolResult.failure("MCP server admission changed.")
        staging = ToolRegistry()
        config = self._config()
        chosen = frozenset({selected.name})
        with self.phase(deps, "selected_schema_discovery", 1):
            if kind == "mcp":
                added = await ensure_mcp_tools(
                    config.mcp_servers,
                    staging,
                    selected_names=chosen,
                    root=self.root,
                    retry_delays_s=config.runtime.retry_delays_s,
                    refresh_references=False,
                    schedule_late=False,
                    pool=self.pool,
                )
            else:
                added = await ensure_hosted_tools(
                    config, staging, selected_names=chosen, root=self.root
                )
        # No await between this guard and publication; cancellation/revocation wins.
        if (
            self.closed
            or context.cancelled.is_set()
            or not admit(selected.name)
            or not self._admitted(kind, selected)
        ):
            return ToolResult.failure("MCP discovery superseded; no tools published.")
        if not added:
            from .pool import _POOL

            target = _POOL if self.pool is None else self.pool
            pending = kind == "mcp" and selected.name in target.connecting_tasks()
            if pending and isinstance(selected, McpServerConfig):
                self._wait_tool(
                    registry, selected, kind, query, permitted, wait_admit or admit, deps
                )
            state = "pending" if pending else "unavailable"
            self._states[(kind, selected.name)] = (selected, state)
            return ToolResult(output=json.dumps({"status": state, "tools": []}))
        with self.phase(deps, "runtime_publication", 1):
            key = (id(registry), selected.name)
            previous = self._published.get(key, set())
            current = set(added)
            for stale in previous - current:
                registry.unregister_remote(stale)
                context.available_tools.discard(stale)
            for tool in staging:
                if tool.name in current:
                    registry.register_or_replace(tool)
                    self._origins[tool.name] = (kind, selected, tool.run)
            self._published[key] = current
            self._owners[key] = (kind, selected)
            self._states[(kind, selected.name)] = (selected, "ready")
            self._pending.pop(selected.name, None)
            wait_tool = registry.get(WAIT_FOR_MCP_SERVERS)
            if wait_tool is not None and getattr(wait_tool.run, "mcp_selected_servers", ()) == (
                selected.name,
            ):
                registry.unregister_remote(WAIT_FOR_MCP_SERVERS)
            candidates = [
                name
                for name in added
                if (definition := registry.get(name)) is not None
                and definition.advertised
                and (not query or query.lower() in (name + " " + definition.description).lower())
            ][:_MAX_RESULTS]
            prioritize_tools(registry, candidates)
            allowed = permitted()
            usable = [
                name
                for name in added
                if name in allowed
                and (definition := registry.get(name)) is not None
                and definition.advertised
            ]
            if query:
                usable = [name for name in usable if name in candidates]
            usable = usable[:_MAX_RESULTS]
            staged_search = tool_search_state(staging)
            search = tool_search_state(registry)
            if staged_search:
                if search is None:
                    search = ToolSearchState(
                        mode=staged_search.mode, upfront_limit=staged_search.upfront_limit
                    )
                search.set_owner(selected.name, staged_search.deferrable, previous)
                search.loaded.update(usable)
                search.recent = (usable + [n for n in search.recent if n not in usable])[:12]
                refresh_tool_search(registry, search)
            context.available_tools.update(usable)
        instructions = ""
        if isinstance(selected, McpServerConfig):
            from .reference_service import server_instructions_block

            instructions = server_instructions_block(
                (selected,), client_for=None if self.pool is None else self.pool.connected_client
            )
        # Real remote schemas/descriptions are external data even when initialize
        # supplies no instructions. Private preflight must retain this taint too.
        deps.mcp_external_content = True
        return ToolResult(
            output=json.dumps(
                {
                    "status": "ready",
                    "tools": registry.schemas(usable),
                    "instructions": instructions,
                },
                ensure_ascii=False,
            )
        )

    async def preflight_selected(
        self,
        registry: ToolRegistry,
        patterns: Collection[str],
        *,
        permitted: Callable[[], set[str]],
        admit: Callable[[str], bool],
        deps: AgentDeps,
        task: str = "",
    ) -> McpExpansion:
        """Private explicit selections retain strict surfaces without adding helpers."""
        config = self._config()
        self._capture_clone(registry)
        try:
            explicit = requested_servers(
                patterns, (*config.mcp_servers, *config.hosted_connectors), registry, eligible=admit
            )
        except AmbiguousMcpAliasError as error:
            return McpExpansion(task, error=self.ambiguity_message(error))
        refs = reference_servers(task, config.mcp_servers)
        selected = explicit | refs
        if not selected:
            if parse_prompt_call(task):
                return McpExpansion(task, error="MCP istemi bulunamadı: sunucu yapılandırılmamış.")
            return McpExpansion(task)
        from .pool import _POOL
        from .reference_service import expand_mcp_references, server_instructions_block

        entries = [(kind, item) for _, kind, item in self._entries() if item.name in selected]
        for kind, item in entries:
            if not admit(item.name) or not self._admitted(kind, item):
                continue
            key = (id(registry), item.name)
            if key not in self._owners or self._owners[key] != (kind, item):
                async with self._locks.setdefault(kind + ":" + item.name, asyncio.Lock()):
                    await self._discover(
                        registry, item, kind, "", deps.tool_context, permitted, admit, deps
                    )
        target = _POOL if self.pool is None else self.pool
        active_configs = tuple(
            c for c in config.mcp_servers if c.name in selected and admit(c.name)
        )
        if refs:
            for name in refs:
                if admit(name):
                    client = target.connected_client(name)
                    if client is not None:
                        await target.refresh_catalog(client)
            return await expand_mcp_references(
                task,
                active_configs,
                client_for=target.connected_client,
                catalogs_for=target.catalogs,
            )
        return McpExpansion(
            task,
            context=server_instructions_block(active_configs, client_for=target.connected_client),
        )

    def _wait_tool(
        self,
        registry: ToolRegistry,
        selected: McpServerConfig,
        kind: Kind,
        query: str,
        permitted: Callable[[], set[str]],
        admit: Callable[[str], bool],
        deps: AgentDeps,
    ) -> None:
        from .pool import _POOL
        from .timeouts import startup_timeout_s

        def completion_admit(server: str) -> bool:
            # Every creation path (including child private preflight after bind)
            # must retain the caller's current permission to complete this wait.
            return WAIT_FOR_MCP_SERVERS in permitted() and admit(server)

        async def wait(args: ToolArgs, context: ToolContext) -> ToolResult:
            if (
                self.closed
                or context.cancelled.is_set()
                or not completion_admit(selected.name)
                or not self._admitted(kind, selected)
            ):
                return ToolResult.failure("MCP selected wait admission changed.")
            target = _POOL if self.pool is None else self.pool
            task = target.connecting_tasks().get(selected.name)
            if task is not None:
                await asyncio.wait({task}, timeout=startup_timeout_s(selected))
            return await self._discover(
                registry, selected, kind, query, context, permitted, completion_admit, deps
            )

        self._pending[selected.name] = (kind, selected, query)
        wait.mcp_selected_servers = (selected.name,)  # type: ignore[attr-defined]
        self._origins[WAIT_FOR_MCP_SERVERS] = (kind, selected, wait)
        key = (id(registry), selected.name)
        self._owners[key] = (kind, selected)
        self._published.setdefault(key, set()).add(WAIT_FOR_MCP_SERVERS)
        registry.register_or_replace(
            Tool(
                name=WAIT_FOR_MCP_SERVERS,
                description="Wait for the selected MCP server and publish permitted tools.",
                parameters={"type": "object", "properties": {}},
                run=wait,
                mutating=False,
                effect=ToolEffect.REMOTE_READ,
            )
        )


def preflight_admission(
    deps: AgentDeps,
    server: str,
    allowed: Collection[str] | None,
    denied: Collection[str],
    registry: ToolRegistry,
) -> bool:
    """An explicit server selection never broadens a builtin-only or persona cap."""
    from ..engines.agent.bare_deny import bare_denied_tools

    probe = claude_mcp_tool_name(server, "discovery_metadata")
    if bare_denied_tools(getattr(deps, "permission_rules", None), (probe,)):
        return False
    config = deps.config
    all_configs: tuple[ServerConfig, ...] = (*config.mcp_servers, *config.hosted_connectors)
    if allowed is not None and server not in requested_servers(
        allowed, all_configs, registry, allow_ambiguous=True
    ):
        return False
    server_prefix = claude_mcp_tool_name(server, "")
    for pattern in denied:
        if canonical_mcp_name(pattern) in {
            server_prefix.removesuffix("__"),
            server_prefix + "*",
            "*",
        }:
            return False
    persona = getattr(deps, "session_persona", None)
    if persona is not None:
        if persona.mcp_servers and server not in persona.mcp_servers:
            return False
        if persona.tools is not None and server not in requested_servers(
            persona.tools, all_configs, registry
        ):
            return False
        if any(
            canonical_mcp_name(pattern)
            in {server_prefix.removesuffix("__"), server_prefix + "*", "*"}
            for pattern in persona.disallowed_tools
        ):
            return False
    return True


async def prepare_mcp_turn(
    task: str,
    deps: AgentDeps,
    *,
    allowed: Collection[str] | None = None,
    denied: Collection[str] = (),
    enabled: bool = True,
) -> tuple[McpDiscovery, McpExpansion]:
    """Prepare a local catalog; only explicit tool/reference selections do preflight I/O."""
    root = getattr(deps.tool_context, "root", None)
    owner = McpDiscovery(lambda: deps.config, root=root)
    deps.mcp_external_content = False
    config = deps.config
    deps.mcp_discovery = owner if enabled else None
    if not enabled:
        return owner, McpExpansion(task)
    registry = deps.base_registry
    assert registry is not None
    config = deps.config
    with owner.phase(deps, "catalog_preparation", 0):
        # Materialize safe catalog locally. No pool/status/config-file access.
        owner.catalog()

    def admitted(name: str) -> bool:
        return preflight_admission(deps, name, allowed, denied, registry)

    try:
        explicit = requested_servers(
            allowed, (*config.mcp_servers, *config.hosted_connectors), registry, eligible=admitted
        )
    except AmbiguousMcpAliasError as error:
        return owner, McpExpansion(task, error=owner.ambiguity_message(error))
    references = reference_servers(task, config.mcp_servers)
    selected = explicit | references
    if not selected:
        if parse_prompt_call(task):
            from .reference_service import expand_mcp_references

            return owner, await expand_mcp_references(task, ())
        return owner, McpExpansion(task)
    tool = owner.bind(registry, permitted=lambda: set(registry.names()), admit=admitted, deps=deps)
    safe_by_name = {item.name: safe for safe, _, item in owner._entries()}
    for name in sorted(selected):
        if admitted(name) and name in safe_by_name:
            await cast(
                Awaitable[ToolResult], tool.run({"server": safe_by_name[name]}, deps.tool_context)
            )
    if references:
        from .pool import _POOL
        from .reference_service import expand_mcp_references

        for name in references:
            if not admitted(name):
                continue
            client = _POOL.connected_client(name)
            if client is not None:
                await _POOL.refresh_catalog(client)
        with owner.phase(deps, "explicit_reference_expansion", len(references)):
            expansion = await expand_mcp_references(
                task,
                tuple(c for c in config.mcp_servers if c.name in references and admitted(c.name)),
            )
            deps.mcp_external_content = deps.mcp_external_content or bool(
                expansion.context or expansion.task != task
            )
            return owner, expansion
    from .reference_service import server_instructions_block

    expansion = McpExpansion(
        task,
        context=server_instructions_block(
            tuple(c for c in config.mcp_servers if c.name in explicit and admitted(c.name))
        ),
    )
    deps.mcp_external_content = deps.mcp_external_content or bool(expansion.context)
    return owner, expansion
