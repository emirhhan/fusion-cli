"""Generated current capability claims use the actual request authority."""

from dataclasses import replace

import pytest

from fusion_cli.core.tools import Tool, ToolResult
from fusion_cli.core.types import Message, StreamDone
from fusion_cli.engines.agent import loop
from fusion_cli.tools import ToolRegistry
from fusion_cli.tools.capabilities import Capability, CapabilityRegistry
from tests.fakes import RecordingSink, model_result
from tests.test_agent_loop import _deps


def _library(tmp_path):
    return CapabilityRegistry(
        tmp_path / "home",
        tmp_path,
        disabled_builtin_agents=frozenset({"*"}),
        extra_agent_sources=False,
        session_agents=(
            Capability(
                "reader-one",
                "FIRST_AGENT_DESCRIPTION",
                tmp_path / "one",
                "session",
                inline_prompt="BODY_ONE",
            ),
            Capability(
                "reader-two",
                "SECOND_AGENT_DESCRIPTION",
                tmp_path / "two",
                "session",
                inline_prompt="BODY_TWO",
            ),
        ),
    )


def _base():
    registry = ToolRegistry()
    for name in ("read_file", "browser_open", "desktop_apps", "find_skill", "read_skill"):
        registry.register(
            Tool(
                name,
                "Synthetic",
                {"type": "object", "properties": {}},
                lambda args, context: ToolResult("synthetic"),
            )
        )
    return registry


async def _actual(tmp_path, monkeypatch, allowed, *, custom=None, agent_types=None, depth=0):
    deps = _deps(
        tmp_path,
        RecordingSink(),
        runtime={"project_instructions": False, "skill_index_chars": 0, "lessons": False},
    )
    deps.home = tmp_path / "home"
    deps.capabilities = _library(tmp_path)
    deps.base_registry = _base()
    deps.allowed_agent_types = agent_types
    deps.config = replace(deps.config, desktop=replace(deps.config.desktop, enabled=True))
    frames = []

    class Provider:
        async def stream(self, request):
            frames.append(request)
            yield StreamDone(model_result("Available capabilities described."))

    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: Provider())
    result = await loop.run_agent(
        "Describe current available capabilities briefly.",
        deps,
        allowed_tools=allowed,
        self_review=False,
        verify=False,
        step_limit=1,
        system_prompt=custom,
        depth=depth,
    )
    return deps, result, frames


def _system(frame):
    return "\n".join(m.content for m in frame.messages if m.role == "system")


def _current(frame):
    return next(
        line
        for line in _system(frame).splitlines()
        if line.startswith("Bu turda elindeki aileler:")
    )


@pytest.mark.parametrize("allowed", [set(), {"read_file"}])
async def test_empty_or_read_scope_advertises_only_its_current_capabilities(
    tmp_path, monkeypatch, allowed
):
    _, result, frames = await _actual(tmp_path, monkeypatch, allowed)
    assert result.ok
    line = _current(frames[0])
    for claim in (
        "Fusion Browser",
        "masaüstü kontrolü",
        "çoklu-model danışma",
        "site araçları",
        "ajanlar",
    ):
        assert claim not in line
    assert "FIRST_AGENT_DESCRIPTION" not in _system(frames[0])
    if allowed:
        assert "kod ve dosya" in line and "beceriler" in line
    else:
        assert not frames[0].tools and "yok" in line


async def test_only_launchable_agents_are_in_actual_request(tmp_path, monkeypatch):
    _, _, frames = await _actual(tmp_path, monkeypatch, {"Agent"}, agent_types=("reader-one",))
    system = _system(frames[0])
    assert "FIRST_AGENT_DESCRIPTION" in system and "SECOND_AGENT_DESCRIPTION" not in system
    assert "BODY_ONE" not in system


async def test_legacy_route_does_not_instruct_unavailable_canonical_tool(tmp_path, monkeypatch):
    _, _, frames = await _actual(tmp_path, monkeypatch, {"invoke_agent"})
    system = _system(frames[0])
    assert "FIRST_AGENT_DESCRIPTION" in system
    assert "invoke_agent aracıyla" in system and "Agent aracıyla" not in system


async def test_current_context_never_mutates_canonical_custom_prompt(tmp_path, monkeypatch):
    custom = "USER_CUSTOM_BODY\nBu turda elindeki aileler: user-owned words."
    _, result, frames = await _actual(tmp_path, monkeypatch, set(), custom=custom)
    assert result.messages[0].content.startswith(custom)
    assert "<fusion-current-capabilities>" in _system(frames[0])
    assert all("<fusion-current-capabilities>" not in m.content for m in result.messages)
    assert "USER_CUSTOM_BODY" in _system(frames[0])


def test_filtered_duplicate_retains_qualified_identity(tmp_path):
    from fusion_cli.tools.agent_catalog_index import agent_catalog_index

    agents = (
        Capability("same", "ALLOWED", tmp_path / "one", "first"),
        Capability("same", "DENIED", tmp_path / "two", "second"),
    )
    text = agent_catalog_index(
        None, count_tokens=len, agents=agents, include=lambda item, name: item.source == "first"
    )
    assert agents[0].qualified_name in text and "DENIED" not in text


async def test_request_projection_refreshes_without_accumulation_or_history_mutation(tmp_path):
    from fusion_cli.engines.agent.capability_context import request_capability_messages

    deps = _deps(tmp_path, RecordingSink())
    deps.home = tmp_path / "home"
    deps.capabilities = _library(tmp_path)
    messages = [Message("system", "ORIGINAL_SYSTEM"), Message("user", "ORIGINAL_USER")]
    first = request_capability_messages(
        messages,
        deps,
        {"desktop_apps", "Agent"},
        offer_tools=True,
        depth=0,
        agents=deps.capabilities.agents(),
    )
    second = request_capability_messages(
        messages, deps, {"read_file"}, offer_tools=True, depth=0, agents=deps.capabilities.agents()
    )
    assert "masaüstü kontrolü" in "\n".join(m.content for m in first)
    assert "masaüstü kontrolü" not in "\n".join(m.content for m in second)
    assert messages == [Message("system", "ORIGINAL_SYSTEM"), Message("user", "ORIGINAL_USER")]
    assert sum("<fusion-current-capabilities>" in m.content for m in second) == 1
    none = request_capability_messages(
        messages,
        deps,
        {"Agent", "desktop_apps"},
        offer_tools=False,
        depth=0,
        agents=deps.capabilities.agents(),
    )
    text = "\n".join(m.content for m in none)
    assert "FIRST_AGENT_DESCRIPTION" not in text and "masaüstü kontrolü" not in text


def test_catalog_metadata_never_resolves_persona_body(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import team
    from fusion_cli.engines.agent.capability_context import request_capability_messages

    deps = _deps(tmp_path, RecordingSink())
    deps.capabilities = _library(tmp_path)
    monkeypatch.setattr(team, "resolve_persona", lambda *args: pytest.fail("persona body read"))
    text = request_capability_messages(
        [Message("system", "base")],
        deps,
        {"Agent"},
        offer_tools=True,
        depth=0,
        agents=deps.capabilities.agents(),
    )
    assert "FIRST_AGENT_DESCRIPTION" in "\n".join(m.content for m in text)


def test_type_deny_and_depth_limit_match_launch_metadata(tmp_path):
    from fusion_cli.config.permission_rules import (
        PermissionDecision,
        PermissionRule,
        PermissionRuleSet,
    )
    from fusion_cli.engines.agent.capability_context import request_capability_messages
    from fusion_cli.engines.agent.team import max_agent_depth

    deps = _deps(tmp_path, RecordingSink())
    deps.capabilities = _library(tmp_path)
    deps.permission_rules = PermissionRuleSet(
        (PermissionRule("Agent", "reader-two", PermissionDecision.DENY),)
    )
    frames = request_capability_messages(
        [Message("system", "base")],
        deps,
        {"Agent"},
        offer_tools=True,
        depth=0,
        agents=deps.capabilities.agents(),
    )
    text = "\n".join(m.content for m in frames)
    assert "FIRST_AGENT_DESCRIPTION" in text and "SECOND_AGENT_DESCRIPTION" not in text
    limited = request_capability_messages(
        [Message("system", "base")],
        deps,
        {"Agent"},
        offer_tools=True,
        depth=max_agent_depth(deps),
        agents=deps.capabilities.agents(),
    )
    assert "FIRST_AGENT_DESCRIPTION" not in "\n".join(m.content for m in limited)


def test_legacy_catalog_uses_its_actual_parameter_name(tmp_path):
    from fusion_cli.tools.agent_catalog_index import agent_catalog_index

    text = agent_catalog_index(_library(tmp_path), count_tokens=len, invocation_tool="invoke_agent")
    assert "invoke_agent aracıyla (name)" in text
    assert "subagent_type" not in text


async def test_allowed_deferred_tool_remains_in_permission_inventory(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import capability_context
    from tests.test_tool_search_permission_projection import SAFE, _catalog

    deps = _deps(tmp_path, RecordingSink(), runtime={"lessons": False})
    deps.base_registry, _state = _catalog()
    frames, inventories = [], []
    real_line = capability_context.session_line

    def capture(names, teacher):
        inventories.append(set(names))
        return real_line(names, teacher)

    monkeypatch.setattr(capability_context, "session_line", capture)

    class Provider:
        async def stream(self, request):
            frames.append(request)
            yield StreamDone(model_result("Hello."))

    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: Provider())
    await loop.run_agent(
        "Hello.", deps, allowed_tools={"ToolSearch", SAFE}, self_review=False, verify=False
    )
    offered = {tool["function"]["name"] for tool in frames[0].tools}
    assert SAFE in inventories[0] and SAFE not in offered and "ToolSearch" in offered


def test_denied_catalog_description_is_not_counted_in_warning(tmp_path, caplog):
    from fusion_cli.tools.agent_catalog_index import agent_catalog_index

    agents = (
        Capability("allowed", "Short", tmp_path / "a", "session"),
        Capability("denied", "DENIED_LONG " * 10000, tmp_path / "b", "session"),
    )
    text = agent_catalog_index(
        None,
        count_tokens=lambda text: len(text),
        agents=agents,
        include=lambda item, name: name == "allowed",
    )
    assert "DENIED_LONG" not in text and not caplog.records
