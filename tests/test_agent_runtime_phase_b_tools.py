"""Ajan aracının gerçek çalışma zamanı ve tür izin sınırları."""

from __future__ import annotations

import pytest

from fusion_cli.config.permission_rules import PermissionDecision, PermissionRule
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.tools.permission_match import matches

from .fakes import ScriptedProvider, model_result
from .test_system_prompt_layers import _deps


async def test_canonical_agent_invokes_real_child(monkeypatch, tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    provider = ScriptedProvider([model_result("Alt görev bitti.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    tool = registry.get("Agent")
    assert tool is not None
    assert {"prompt", "description", "subagent_type", "model"} <= set(tool.parameters["properties"])
    result = await tool.run(
        {
            "prompt": "Merhaba",
            "description": "Kısa görev",
            "subagent_type": "general-purpose",
            "run_in_background": False,
        },
        deps.tool_context,
    )
    assert result.ok and "Alt görev bitti." in result.output
    assert provider.seen_messages


@pytest.mark.parametrize(
    "tool,args",
    [
        ("Agent", {"subagent_type": "Explore"}),
        ("spawn_agent", {"uzman": "Explore"}),
        ("spawn_agents", {"gorevler": [{"uzman": "Explore", "task": "ara"}]}),
    ],
)
def test_agent_type_deny_covers_canonical_and_legacy(tool, args, tmp_path):
    rule = PermissionRule("Agent", "Explore", PermissionDecision.DENY)
    assert matches(rule, tool, args, tmp_path)


def test_session_metadata_contract_is_available(tmp_path):
    import inspect

    from fusion_cli.cli.session import run_agent_task
    from fusion_cli.engines.agent.team import Persona

    assert "session_persona" in inspect.signature(run_agent_task).parameters
    persona = Persona("ozel", "Özel", "", "")
    assert hasattr(persona, "hook_definitions")
    assert hasattr(_deps(tmp_path, "nvidia_nim/ornek-model"), "session_persona")


async def test_catalog_description_reaches_actual_main_provider(monkeypatch, tmp_path):
    from fusion_cli.tools.capabilities import Capability, CapabilityRegistry

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    agent = Capability(
        "arsivci",
        "Arşiv karşılaştırmasında özel uzmanlık 5937",
        tmp_path / "oturum.md",
        "cli",
        inline_prompt="Gizli gövde 7193",
    )
    deps.capabilities = CapabilityRegistry(tmp_path / "ev", tmp_path, session_agents=(agent,))
    provider = ScriptedProvider([model_result("Merhaba.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    await loop.run_agent("Merhaba", deps)
    system = provider.seen_messages[0][0].content
    assert "Arşiv karşılaştırmasında özel uzmanlık 5937" in system
    assert "Gizli gövde 7193" not in system


async def test_main_agent_type_scope_denies_legacy_and_builtin_alias(monkeypatch, tmp_path):
    from fusion_cli.config.permission_rules import PermissionRuleSet
    from fusion_cli.tools.capabilities import CapabilityRegistry

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.capabilities = CapabilityRegistry(tmp_path / "ev", tmp_path)
    deps.permission_rules = PermissionRuleSet(
        (PermissionRule("Agent", "Explore", PermissionDecision.DENY),)
    )
    provider = ScriptedProvider([])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    for name in ("Agent", "spawn_agent"):
        result = await registry.get(name).run(
            {"task": "Ara", "uzman": "explore", "run_in_background": False}, deps.tool_context
        )
        assert not result.ok or "engelliyor" in result.output
    assert provider.seen_messages == []
