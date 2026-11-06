"""Current runtime authority governs tool discovery as well as execution."""

from dataclasses import replace

import pytest

from fusion_cli.config.models import McpServerConfig
from fusion_cli.core.tools import Tool, ToolContext, ToolEffect, ToolResult
from fusion_cli.core.types import ModelSpec, StreamDone
from fusion_cli.engines.agent import loop, team
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.mcp_bridge import pool
from fusion_cli.mcp_bridge.discovery import McpDiscovery
from fusion_cli.mcp_bridge.tool_search_bridge import McpToolSearch
from fusion_cli.mcp_bridge.types import RemoteTool
from fusion_cli.tools import ToolRegistry
from fusion_cli.tools.tool_search import (
    ToolSearchMode,
    ToolSearchState,
    prioritized_tool_names,
    refresh_tool_search,
    visible_tool_names,
)
from tests.fakes import AlwaysApprove, make_config, model_result, tool_call

SAFE = "mcp__synthetic__safe"
BLOCKED = "mcp__synthetic__blocked"
MARKER = "SYNTHETIC_DENIED_DESCRIPTION"


@pytest.mark.parametrize("target", [SAFE, BLOCKED])
async def test_deferred_helper_resume_binds_permissions_before_first_model_request(
    tmp_path,
    monkeypatch,
    target,
):
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent.hook_bridge import TOOL_DEFERRED
    from tests.fakes import RecordingSink, ScriptedProvider
    from tests.test_agent_loop import _deps

    monkeypatch.setenv("ENABLE_TOOL_SEARCH", "true")
    deps = _deps(
        tmp_path,
        RecordingSink(),
        runtime={
            "project_instructions": False,
            "lessons": False,
            "skill_index_chars": 0,
        },
    )
    deps.base_registry, search_state = _catalog()
    call = tool_call("ToolSearch", query="select:" + target)
    history = [
        Message("user", "Inspect tool metadata."),
        Message("assistant", "", tool_calls=(call,)),
        Message("tool", TOOL_DEFERRED, tool_call_id=call.id, name=call.name, ok=False),
    ]
    provider = ScriptedProvider([model_result("Metadata inspection finished.")])
    monkeypatch.setattr(loop, "build_provider", lambda *a, **kw: provider)
    outcome = await loop.run_agent(
        "Continue metadata inspection.",
        deps,
        history=history,
        allowed_tools={"ToolSearch", SAFE},
        verify=False,
        self_review=False,
        step_limit=1,
    )
    assert not any(MARKER in m.content for m in outcome.messages if m.role == "tool")
    assert BLOCKED not in search_state.loaded
    assert (SAFE in search_state.loaded) is (target == SAFE)


def _catalog(*, mode=None):
    registry = ToolRegistry()
    state = ToolSearchState(mode or ToolSearchMode(True, explicit=True))
    for name in (BLOCKED, SAFE):
        registry.register_or_replace(
            Tool(
                name,
                MARKER if name == BLOCKED else "safe record reader",
                {"type": "object", "properties": {}},
                lambda args, context: ToolResult(output="42"),
                effect=ToolEffect.REMOTE_READ,
            )
        )
        state.deferrable[name] = "synthetic"
    refresh_tool_search(registry, state)
    return registry, state


@pytest.mark.parametrize(
    "mode,search,child",
    [
        ("deny", "true", False),
        ("allow", "true", False),
        ("late", "true", False),
        ("deny", "default", False),
        ("deny", "true", True),
    ],
)
async def test_actual_actor_search_never_discloses_denied_definition(
    tmp_path,
    monkeypatch,
    mode,
    search,
    child,
):
    monkeypatch.delenv("CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS", raising=False)
    if search == "default":
        monkeypatch.delenv("ENABLE_TOOL_SEARCH", raising=False)
    else:
        monkeypatch.setenv("ENABLE_TOOL_SEARCH", search)
    events, business, helper_descriptions, frames = [], [], [], []
    cfg = make_config(
        agent=ModelSpec(name="agent", model="nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"),
        source=tmp_path / "config.yaml",
        memory_dir=tmp_path / "memory",
        runtime={"project_instructions": False, "lessons": False},
        mcp_servers=(McpServerConfig("synthetic", command="NEVER_START"),),
    )

    class Publisher:
        def publish(self, event):
            events.append(event)

    deps = loop.AgentDeps(
        config=cfg,
        publisher=Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=ToolRegistry(),
        denied_tools=frozenset({BLOCKED}) if mode == "deny" else frozenset(),
    )
    deps.mcp_discovery = McpDiscovery(lambda: deps.config, root=tmp_path)

    async def ensure(configs, registry, **kwargs):
        named = []
        assert kwargs["selected_names"] == frozenset({"synthetic"})
        for name, description in ((SAFE, "safe record reader"), (BLOCKED, MARKER)):

            def execute(args, context, selected=name):
                business.append(selected)
                return ToolResult(output="safe record42")

            registry.register_or_replace(
                Tool(
                    name,
                    description,
                    {"type": "object", "properties": {}},
                    execute,
                    effect=ToolEffect.REMOTE_READ,
                )
            )
            named.append((name, RemoteTool("synthetic", name, description)))
        McpToolSearch().apply(registry, "synthetic", configs[0], named, ())
        return tuple(name for name, _ in named)

    class Provider:
        stage = 0

        async def stream(self, request):
            helper = next(
                (x["function"] for x in request.tools if x["function"]["name"] == "ToolSearch"),
                None,
            )
            if self.stage >= 2:
                helper_descriptions.append(helper["description"] if helper else "")
            frames.append(request)
            if self.stage == 0:
                result = model_result(
                    tool_calls=(tool_call("DiscoverMcpTools", server="synthetic"),)
                )
            elif self.stage == 1:
                if mode == "late":
                    deps.denied_tools = frozenset({BLOCKED})
                result = model_result(
                    tool_calls=(tool_call("ToolSearch", query="select:" + BLOCKED),)
                )
            elif self.stage == 2:
                result = model_result(tool_calls=(tool_call(BLOCKED),))
            elif self.stage == 3:
                result = model_result(tool_calls=(tool_call(SAFE),))
            else:
                result = model_result(text="The safe record is42.")
            self.stage += 1
            yield StreamDone(result)

    monkeypatch.setattr(pool, "ensure_mcp_tools", ensure)
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider_instance)
    provider_instance = Provider()
    if child:
        persona = team.Persona(
            "reader", "Reader", "Read", "gray", disallowed_tools=frozenset({BLOCKED})
        )
        monkeypatch.setattr(team, "resolve_persona", lambda *args, **kwargs: persona)
        await team.run_subagent(
            deps,
            team.SubTask("Retrieve the safe service record", persona="reader"),
            depth=0,
            run_agent=loop.run_agent,
        )
        outputs = [
            e.output
            for e in events
            if type(e).__name__ == "ToolExecuted" and e.name == "ToolSearch"
        ]
    else:
        allowed = {"DiscoverMcpTools", "ToolSearch", SAFE} if mode == "allow" else None
        outcome = await loop.run_agent(
            "Retrieve the safe service record",
            deps,
            allowed_tools=allowed,
            self_review=False,
            step_limit=6,
        )
        outputs = [u.output for u in outcome.tool_uses if u.name == "ToolSearch"]
    assert outputs and all(MARKER not in value for value in outputs)
    assert all(BLOCKED not in value for value in helper_descriptions)
    assert business == [SAFE]
    if mode != "late":
        assert all(MARKER not in message.content for frame in frames for message in frame.messages)


async def test_child_binding_does_not_replace_parent_admission(tmp_path):
    from fusion_cli.engines.agent.engine_tools import _clone
    from fusion_cli.tools.tool_search import bind_tool_search

    parent, state = _catalog()
    bind_tool_search(parent, lambda: {"ToolSearch", SAFE})
    child = _clone(parent)
    bind_tool_search(child, lambda: {"ToolSearch", BLOCKED})
    assert BLOCKED not in parent.get("ToolSearch").description
    assert SAFE not in child.get("ToolSearch").description
    for registry, wanted, forbidden in ((parent, SAFE, BLOCKED), (child, BLOCKED, SAFE)):
        result = await registry.execute(
            "ToolSearch", {"query": "record " + MARKER}, ToolContext(root=tmp_path)
        )
        assert wanted in result.output
        assert forbidden not in result.output
    assert state.loaded == {SAFE, BLOCKED}


async def test_publication_after_binding_keeps_runtime_admission(tmp_path):
    from fusion_cli.tools.tool_search import bind_tool_search

    registry = ToolRegistry()
    bind_tool_search(registry, lambda: {"ToolSearch", SAFE})
    source, state = _catalog()
    for tool in source:
        if tool.name != "ToolSearch":
            registry.register_or_replace(tool)
    refresh_tool_search(registry, state)
    assert BLOCKED not in registry.get("ToolSearch").description
    result = await registry.execute(
        "ToolSearch", {"query": "select:" + BLOCKED + "," + SAFE}, ToolContext(root=tmp_path)
    )
    assert SAFE in result.output and MARKER not in result.output
    assert state.loaded == {SAFE}
    assert prioritized_tool_names(registry) == (SAFE,)


async def test_revoked_search_does_not_emit_or_newly_activate_definition(tmp_path):
    from fusion_cli.tools.tool_search import bind_tool_search

    registry, state = _catalog()
    allowed = {"ToolSearch", SAFE, BLOCKED}
    bind_tool_search(registry, lambda: allowed.copy())
    first = await registry.execute(
        "ToolSearch", {"query": "select:" + BLOCKED}, ToolContext(root=tmp_path)
    )
    assert MARKER in first.output
    allowed.remove(BLOCKED)
    state.loaded.clear()
    result = await registry.execute(
        "ToolSearch", {"query": "select:" + BLOCKED}, ToolContext(root=tmp_path)
    )
    assert MARKER not in result.output and not state.loaded
    assert MARKER in first.output  # Legitimately previously seen history is unchanged.


def test_denied_candidate_does_not_consume_result_slot():
    registry, state = _catalog()
    found = state.search("record " + MARKER, registry, 1, permitted={SAFE})
    assert [tool.name for tool in found] == [SAFE]
    assert state.search("record", registry, 1, permitted=set()) == []


def test_auto_threshold_uses_permitted_definitions():
    registry, state = _catalog(mode=ToolSearchMode(True, 10, explicit=True))
    registry.register_or_replace(replace(registry.get(BLOCKED), description=MARKER * 10000))
    visible = visible_tool_names(
        {"ToolSearch", SAFE}, registry, lambda: 10000, model="claude-sonnet-4-5"
    )
    assert SAFE in visible
    assert not state.latched


async def test_callback_failure_never_falls_back_to_full_catalog(tmp_path):
    from fusion_cli.tools.tool_search import bind_tool_search

    registry, state = _catalog()

    def fail():
        raise RuntimeError("SYNTHETIC_SECRET")

    bind_tool_search(registry, fail)
    assert BLOCKED not in registry.get("ToolSearch").description
    result = await registry.execute(
        "ToolSearch", {"query": "select:" + BLOCKED}, ToolContext(root=tmp_path)
    )
    assert MARKER not in result.output and "SYNTHETIC_SECRET" not in result.output
    assert not state.loaded


async def test_helper_excluded_grants_no_metadata_authority(tmp_path):
    from fusion_cli.tools.tool_search import bind_tool_search

    registry, state = _catalog()
    bind_tool_search(registry, lambda: {SAFE})
    result = await registry.execute(
        "ToolSearch", {"query": "select:" + SAFE}, ToolContext(root=tmp_path)
    )
    assert SAFE not in result.output and not state.loaded
    assert SAFE not in registry.get("ToolSearch").description


def test_runtime_binding_does_not_retain_registry_globally():
    import gc
    import weakref

    from fusion_cli.tools.tool_search import bind_tool_search

    registry, _state = _catalog()
    bind_tool_search(registry, lambda owner=registry: set(owner.names()))
    reference = weakref.ref(registry)
    del registry
    gc.collect()
    assert reference() is None
