"""Dynamic MCP publication retains original restrictions on the active registry."""

import pytest

from fusion_cli.core.tools import Tool, ToolContext, ToolResult
from fusion_cli.core.types import StreamDone
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.loop import _permitted
from fusion_cli.engines.agent.runtime_surface import RuntimeToolSurface, bind_surface
from fusion_cli.tools import ToolRegistry

from .fakes import AlwaysApprove, make_config, model_result, tool_call


def _tool(name, *, remote=False, mutating=False):
    return Tool(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {}},
        run=lambda a, c: ToolResult(output="ok"),
        mutating=mutating,
    )


def test_original_wildcard_and_deny_reexpand_after_publication():
    registry = ToolRegistry()
    registry.register(_tool("read_file"))
    surface = RuntimeToolSurface(
        allowed=frozenset({"mcp__opaque__*"}), denied=frozenset({"mcp__opaque__delete"})
    )
    bind_surface(registry, surface)
    config = make_config()
    execution = policy_for(config, config.agent, "read records")
    registry.register_or_replace(_tool("mcp__opaque__read"))
    registry.register_or_replace(_tool("mcp__opaque__delete"))
    assert "mcp__opaque__read" in _permitted({"mcp__opaque__*"}, registry, execution)
    assert "mcp__opaque__delete" not in _permitted({"mcp__opaque__*"}, registry, execution)


def test_parent_original_restrictions_never_widen_for_child():
    registry = ToolRegistry()
    registry.register_or_replace(_tool("mcp__a__read"))
    registry.register_or_replace(_tool("mcp__b__read"))
    parent = RuntimeToolSurface(allowed=frozenset({"mcp__a__*"}))
    child = RuntimeToolSurface(parent=parent)
    assert child.names(registry) == {"mcp__a__read"}
    assert child.admit("a")
    assert not child.admit("b")


def test_builtin_mcp_style_alias_does_not_trigger_remote_inference():
    registry = ToolRegistry()
    registry.register(_tool("claude-in-chrome__read_page"))
    surface = RuntimeToolSurface(allowed=frozenset({"claude-in-chrome__read_page"}))
    assert not surface.admit("claude-in-chrome", registry)
    assert surface.names(registry) == {"claude-in-chrome__read_page"}


class _Publisher:
    def publish(self, event):
        pass


class _Discovery:
    def __init__(self):
        self.bound = []

    async def preflight_selected(self, registry, patterns, *, task, permitted, admit, deps):
        from fusion_cli.mcp_bridge.references import McpExpansion

        return McpExpansion(task)

    def permitted_names(self, registry):
        return set(registry.names())

    def bind(self, registry, *, permitted, admit, deps, selected_admit=None):
        self.bound.append(registry)

        async def discover(args, context):
            assert admit("opaque")
            registry.register_or_replace(_tool("mcp__opaque__read"))
            assert "mcp__opaque__read" in permitted()
            return ToolResult(output="Discovered the real read tool")

        return Tool(
            name="DiscoverMcpTools",
            description="Discover",
            parameters={"type": "object", "properties": {}},
            run=discover,
        )


@pytest.mark.parametrize("search_enabled", ["false", "true"])
async def test_active_clone_discovery_visible_next_model_request_and_executor(
    tmp_path, monkeypatch, search_enabled
):
    monkeypatch.setenv("ENABLE_TOOL_SEARCH", search_enabled)
    coordinator = _Discovery()
    base = ToolRegistry()
    calls = []

    class Provider:
        async def stream(self, request):
            names = {item["function"]["name"] for item in request.tools}
            calls.append(names)
            if len(calls) == 1:
                assert "DiscoverMcpTools" in names
                result = model_result(tool_calls=(tool_call("DiscoverMcpTools"),))
            elif len(calls) == 2:
                assert "mcp__opaque__read" in names
                result = model_result(tool_calls=(tool_call("mcp__opaque__read"),))
            else:
                result = model_result(text="The configured record says ok.")
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: Provider())
    deps = loop.AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=base,
        mcp_discovery=coordinator,
    )
    outcome = await loop.run_agent(
        "Read the configured service record and report its content",
        deps,
        self_review=False,
        step_limit=4,
    )
    assert outcome.ok
    assert all(
        name != "DiscoverMcpTools" for name, _, _ in deps.require_budget().successful_tool_evidence
    )
    assert any(use.name == "mcp__opaque__read" for use in outcome.tool_uses)
    assert coordinator.bound and coordinator.bound[-1] is not base
    assert base.get("mcp__opaque__read") is None


def test_real_execution_step_cap_wins_after_discovery():
    from dataclasses import replace

    registry = ToolRegistry()
    registry.register_or_replace(_tool("mcp__a__read"))
    registry.register_or_replace(_tool("mcp__b__read"))
    bind_surface(registry, RuntimeToolSurface())
    config = make_config()
    execution = replace(
        policy_for(config, config.agent, "read"), allowed_tool_names=frozenset({"mcp__a__read"})
    )
    assert "mcp__b__read" not in _permitted(None, registry, execution)


async def test_forbidden_tool_cannot_execute_after_dynamic_publication(tmp_path):
    from fusion_cli.core.events import ToolOutcome

    registry = ToolRegistry()
    registry.register_or_replace(_tool("mcp__a__delete", mutating=True))
    surface = RuntimeToolSurface(denied=frozenset({"a__delete"}))
    bind_surface(registry, surface)
    config = make_config()
    deps = loop.AgentDeps(
        config=config,
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=ToolRegistry(),
    )
    result, outcome = await loop._execute(
        tool_call("mcp__a__delete"),
        {},
        deps,
        registry,
        execution=policy_for(config, config.agent, "read records"),
    )
    assert outcome is ToolOutcome.BLOCKED
    assert not result.ok


def test_long_canonical_and_legacy_allow_patterns_share_parent_cap():
    from fusion_cli.core.mcp_tool_names import provider_mcp_tool_name

    server = "opaque_" + "x" * 35
    registered = provider_mcp_tool_name(server, "read_records_with_long_name")
    assert registered is not None and len(registered) == 64
    registry = ToolRegistry()
    registry.register_or_replace(_tool(registered))
    parent = RuntimeToolSurface(allowed=frozenset({f"{server}__*"}))
    child = RuntimeToolSurface(
        allowed=frozenset({f"mcp__{server}__read_records_with_long_name"}), parent=parent
    )
    assert child.names(registry) == {registered}
    assert child.admit(server, registry)


async def test_child_surface_reexpands_persona_and_preserves_parent_cap(tmp_path):
    from fusion_cli.engines.agent.team import SubTask, run_subagent

    deps = loop.AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=ToolRegistry(),
        mcp_discovery=_Discovery(),
    )
    deps.runtime_surface = RuntimeToolSurface(
        allowed=frozenset({"mcp__a__*", "DiscoverMcpTools"}), denied=frozenset({"a__delete"})
    )
    seen = []

    async def child_runner(task, child, **kwargs):
        assert child.mcp_discovery is deps.mcp_discovery
        surface = child.mcp_surface_factory(None)
        registry = ToolRegistry()
        registry.register_or_replace(_tool("mcp__a__read"))
        registry.register_or_replace(_tool("mcp__a__delete"))
        registry.register_or_replace(_tool("mcp__b__read"))
        seen.append(surface.names(registry))
        return loop.AgentOutcome(final_text="Read complete.", messages=[])

    await run_subagent(
        deps, SubTask("Read service records", read_only=True), depth=0, run_agent=child_runner
    )
    assert seen == [{"mcp__a__read"}]


def test_dynamic_deny_cannot_be_reintroduced_by_always_allowed():
    registry = ToolRegistry()
    registry.register(_tool("todo_write"))
    registry.register(_tool("read_file"))
    bind_surface(registry, RuntimeToolSurface(denied=frozenset({"todo_write"})))
    config = make_config()
    assert "todo_write" not in _permitted(None, registry, policy_for(config, config.agent, "read"))


def test_discovery_instructions_remain_external_unverified_learning():
    from fusion_cli.core.evidence import ToolUse
    from fusion_cli.engines.agent.learning import reads_external_content

    assert reads_external_content((ToolUse("DiscoverMcpTools", ok=True),))


def test_dynamic_projection_retains_compact_count_limit():
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    registry = ToolRegistry()
    registry.register_or_replace(_tool("mcp__a__first"))
    registry.register_or_replace(_tool("mcp__a__second"))
    bind_surface(registry, RuntimeToolSurface())
    execution = ExecutionPolicy(is_web=False, compact_tool_surface=True, max_external_tools=1)
    assert _permitted(None, registry, execution) == {"mcp__a__first"}


async def test_model_and_executor_use_same_task_for_compact_relevance(tmp_path, monkeypatch):
    from fusion_cli.core.events import ToolOutcome
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

    registry = ToolRegistry()
    registry.register_or_replace(_tool("mcp__a__apple"))
    registry.register_or_replace(_tool("mcp__a__zebra"))
    bind_surface(registry, RuntimeToolSurface(task="apple"))
    execution = ExecutionPolicy(
        is_web=False,
        compact_tool_surface=True,
        max_external_tools=1,
        external_tool_selection="relevance",
    )
    config = make_config()
    deps = loop.AgentDeps(
        config=config,
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=ToolRegistry(),
        budget=loop._new_budget(config),
    )
    offered = []

    class Provider:
        async def stream(self, request):
            offered.extend(item["function"]["name"] for item in request.tools)
            yield StreamDone(model_result(text="ok"))

    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: Provider())
    await loop._call_model(
        [Message("user", "zebra")], deps, registry, state=loop._State(), execution=execution
    )
    assert offered == ["mcp__a__zebra"]
    result, outcome = await loop._execute(
        tool_call("mcp__a__zebra"), {}, deps, registry, execution=execution
    )
    assert outcome is ToolOutcome.OK and result.ok
    result, outcome = await loop._execute(
        tool_call("mcp__a__apple"), {}, deps, registry, execution=execution
    )
    assert outcome is ToolOutcome.BLOCKED and not result.ok


def test_wait_metadata_only_admitted_for_selected_allowed_servers():
    registry = ToolRegistry()

    async def wait(args, context):
        return ToolResult(output="pending")

    wait.mcp_selected_servers = ("a",)
    registry.register_or_replace(
        Tool(
            name="WaitForMcpServers",
            description="Wait selected",
            parameters={"type": "object", "properties": {}},
            run=wait,
        )
    )
    surface = RuntimeToolSurface(server_filter=frozenset({"a"}))
    assert "WaitForMcpServers" in surface.names(registry)
    wait.mcp_selected_servers = ("a", "b")
    assert "WaitForMcpServers" not in surface.names(registry)
    wait.mcp_selected_servers = ("a",)
    restricted = RuntimeToolSurface(
        allowed=frozenset({"mcp__a__*"}), server_filter=frozenset({"a"})
    )
    assert "WaitForMcpServers" not in restricted.names(registry)


def test_persona_wait_metadata_scope_never_lists_unselected_servers(tmp_path):
    from fusion_cli.engines.agent.team import Persona, SubTask
    from fusion_cli.engines.agent.team_policy import allowed_tools

    registry = ToolRegistry()

    async def wait(args, context):
        return ToolResult(output="pending")

    registry.register_or_replace(
        Tool(
            name="WaitForMcpServers",
            description="Wait selected",
            parameters={"type": "object", "properties": {}},
            run=wait,
        )
    )
    deps = loop.AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=registry,
    )
    persona = Persona(
        name="reader", title="Reader", avatar="reader", color="blue", mcp_servers=("a",)
    )

    def names():
        return allowed_tools(
            deps,
            persona,
            SubTask("read", read_only=True),
            available=registry.names(),
            registry=registry,
        )

    assert "WaitForMcpServers" not in names()
    wait.mcp_selected_servers = ("a",)
    assert "WaitForMcpServers" in names()
    wait.mcp_selected_servers = ("b",)
    assert "WaitForMcpServers" not in names()
    wait.mcp_selected_servers = ("a", "b")
    assert "WaitForMcpServers" not in names()


@pytest.mark.parametrize("search_enabled", [False, True])
def test_selected_new_server_priority_preserves_compact_cap_and_permissions(search_enabled):
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.tools.tool_search import (
        ToolSearchMode,
        ToolSearchState,
        prioritize_tools,
        refresh_tool_search,
    )

    registry = ToolRegistry()
    registry.register_or_replace(_tool("mcp__a__read"))
    registry.register_or_replace(_tool("mcp__b__read"))
    if search_enabled:
        refresh_tool_search(registry, ToolSearchState(mode=ToolSearchMode(True)))
    bind_surface(registry, RuntimeToolSurface())
    execution = ExecutionPolicy(is_web=False, compact_tool_surface=True, max_external_tools=1)
    prioritize_tools(registry, ["mcp__a__read"])
    assert "mcp__a__read" in _permitted(None, registry, execution)
    prioritize_tools(registry, ["mcp__b__read"])
    offered = _permitted(None, registry, execution)
    assert "mcp__b__read" in offered and "mcp__a__read" not in offered
    bind_surface(registry, RuntimeToolSurface(denied=frozenset({"mcp__b__read"})))
    assert "mcp__b__read" not in _permitted(None, registry, execution)
    registry.unregister_remote("mcp__b__read")
    assert "mcp__b__read" not in _permitted(None, registry, execution)


async def test_child_explicit_remote_allowlist_preflights_without_granting_helpers(
    tmp_path, monkeypatch
):
    class SelectedDiscovery(_Discovery):
        async def preflight_selected(self, registry, patterns, *, task, permitted, admit, deps):
            assert "mcp__a__read" in patterns
            assert admit("a") and not admit("b")
            registry.register_or_replace(_tool("mcp__a__read"))
            assert "mcp__a__read" in permitted()
            from fusion_cli.mcp_bridge.references import McpExpansion

            return McpExpansion(
                task, context="<mcp_instructions>Untrusted selected usage data</mcp_instructions>"
            )

    coordinator = SelectedDiscovery()
    seen = []

    class Provider:
        async def stream(self, request):
            names = {item["function"]["name"] for item in request.tools}
            assert names == {"mcp__a__read"}
            assert "Untrusted selected usage data" in request.messages[0].content
            seen.append(names)
            result = (
                model_result(tool_calls=(tool_call("mcp__a__read"),))
                if len(seen) == 1
                else model_result(text="The selected service returned ok.")
            )
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: Provider())
    deps = loop.AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=ToolRegistry(),
        mcp_discovery=coordinator,
    )
    outcome = await loop.run_agent(
        "Read the selected configured record",
        deps,
        depth=1,
        allowed_tools={"mcp__a__read"},
        self_review=False,
        step_limit=3,
    )
    assert outcome.ok
    assert any(use.name == "mcp__a__read" for use in outcome.tool_uses)


async def test_child_prompt_expansion_tightens_observation_policy(tmp_path, monkeypatch):
    expanded_task = "Sadece dosyaları oku ve raporla, değişiklik yapma"

    class PromptDiscovery(_Discovery):
        async def preflight_selected(self, registry, patterns, *, task, permitted, admit, deps):
            from fusion_cli.mcp_bridge.references import McpExpansion

            registry.register_or_replace(_tool("mcp__a__read"))
            registry.register_or_replace(_tool("mcp__a__write", mutating=True))
            return McpExpansion(expanded_task)

    calls = []

    class Provider:
        async def stream(self, request):
            names = {item["function"]["name"] for item in request.tools}
            assert "mcp__a__write" not in names
            assert any(
                message.role == "user" and message.content == expanded_task
                for message in request.messages
            )
            calls.append(names)
            result = (
                model_result(tool_calls=(tool_call("mcp__a__read"),))
                if len(calls) == 1
                else model_result(text="İstenen dosyalar okundu ve raporlandı.")
            )
            yield StreamDone(result)

    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: Provider())
    deps = loop.AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=ToolRegistry(),
        mcp_discovery=PromptDiscovery(),
    )
    outcome = await loop.run_agent(
        "/mcp__a__prompt",
        deps,
        depth=1,
        allowed_tools={"mcp__a__*"},
        self_review=False,
        step_limit=3,
    )
    assert outcome.ok and not deps.execution.allow_mutation
    assert deps.mcp_external_content


async def test_preflight_remote_context_cannot_create_trusted_local_work_lesson(monkeypatch):
    from fusion_cli.core.evidence import ToolUse

    from . import test_external_lessons as fixture

    original_deps = fixture._deps

    def preflight_deps(*args, **kwargs):
        deps = original_deps(*args, **kwargs)
        deps.mcp_external_content = True
        return deps

    monkeypatch.setattr(fixture, "_deps", preflight_deps)
    memory = fixture._Bellek()
    await fixture._ogren(monkeypatch, memory, kullanimlar=[ToolUse("read_file")], guven=0.4)
    assert len(memory.eklenen) == 1
    assert memory.eklenen[0].external
    assert memory.eklenen[0].confidence == pytest.approx(0.4)


def test_cold_persona_server_filter_recognizes_configured_unactivated_servers(tmp_path, caplog):
    from fusion_cli.config.models import McpServerConfig
    from fusion_cli.engines.agent.team import Persona, SubTask
    from fusion_cli.engines.agent.team_policy import allowed_tools

    registry = ToolRegistry()
    registry.register(_tool("read_file"))
    deps = loop.AgentDeps(
        config=make_config(mcp_servers=(McpServerConfig("a"),)),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=registry,
    )
    persona = Persona(
        name="reader", title="Reader", avatar="reader", color="blue", mcp_servers=("a",)
    )
    assert allowed_tools(
        deps, persona, SubTask("read"), available=registry.names(), registry=registry
    ) == {"read_file"}
    assert not any("MCP sunucusu yapılandırmada yok" in record.message for record in caplog.records)
