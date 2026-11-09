"""Opt-in metadata budgets preserve discoverability and current authority."""

from dataclasses import replace

import pytest

from fusion_cli.core.errors import ConfigError
from fusion_cli.engines.agent.capability_context import request_capability_messages
from fusion_cli.engines.agent.engine_tools import _find_agent_tool
from fusion_cli.tools.agent_catalog_index import agent_catalog_index
from fusion_cli.tools.capabilities import Capability, CapabilityRegistry
from tests.fakes import RecordingSink, make_config
from tests.test_agent_loop import _deps


def _agents(tmp_path):
    return tuple(
        Capability(
            f"expert-{i}",
            f"DESCRIPTION_{i} " + "detail " * 1200,
            tmp_path / str(i),
            "session",
            inline_prompt="SECRET_BODY",
        )
        for i in range(12)
    )


def test_budget_preserves_every_name_and_body_is_not_loaded(tmp_path):
    agents = _agents(tmp_path)
    full = agent_catalog_index(None, agents=agents, count_tokens=len)
    compact = agent_catalog_index(None, agents=agents, count_tokens=len, max_chars=2200)
    assert len(compact) <= 2200
    assert len(compact) < len(full) / 10
    assert all(item.name in compact for item in agents)
    assert "select:" in compact and "SECRET_BODY" not in compact
    tiny = agent_catalog_index(None, agents=agents, count_tokens=len, max_chars=10)
    assert all(item.name in tiny for item in agents)
    assert "asgari" in tiny


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_budget_config_rejects_invalid_types_and_negative(value):
    with pytest.raises(ConfigError):
        replace(make_config().runtime, agent_catalog_chars=value)


def test_request_only_compacts_with_current_discovery_route(tmp_path):
    deps = _deps(tmp_path, RecordingSink(), runtime={"agent_catalog_chars": 1600})
    agents = _agents(tmp_path)

    def project(names):
        return request_capability_messages(
            [], deps, names, offer_tools=True, depth=0, agents=agents
        )[0].content

    compact = project({"Agent", "find_agent"})
    full = project({"Agent"})
    assert len(compact) < len(full) / 10
    assert "detail " * 100 in full


def test_exact_descriptor_pages_and_scope_are_current(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    agents = _agents(tmp_path)
    library = CapabilityRegistry(
        tmp_path / "home",
        tmp_path,
        session_agents=agents,
        disabled_builtin_agents=frozenset({"*"}),
        extra_agent_sources=False,
    )
    tool = _find_agent_tool(library, deps=deps, depth=0)
    deps.allowed_agent_types = ("expert-10",)
    result = tool.run({"query": "expert"}, deps.tool_context)
    assert "expert-10" in result.output and "expert-0 " not in result.output
    exact = tool.run({"query": "select:expert-10"}, deps.tool_context)
    assert "DESCRIPTION_10" in exact.output and "next_offset" in exact.output
    assert "SECRET_BODY" not in exact.output
    denied = tool.run({"query": "select:expert-1"}, deps.tool_context)
    assert "DESCRIPTION_1" not in denied.output
    deps.allowed_agent_types = ()
    revoked = tool.run({"query": "select:expert-10", "offset": 3000}, deps.tool_context)
    assert "DESCRIPTION_10" not in revoked.output and "detail" not in revoked.output


def test_exact_lookup_cannot_resurrect_hidden_legacy_fallback(tmp_path):
    library = CapabilityRegistry(
        tmp_path / "home", tmp_path, disabled_builtin_agents=frozenset({"*"})
    )
    # Legacy get_agent remains compatible for other consumers; discovery must use visibility.
    assert library.get_agent("kodcu") is not None
    assert not library.agents()
    result = _find_agent_tool(library).run(
        {"query": "select:kodcu"}, _deps(tmp_path, RecordingSink()).tool_context
    )
    assert not result.ok
