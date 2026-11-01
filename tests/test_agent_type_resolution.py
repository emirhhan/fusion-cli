"""Agent aracında subagent_type Claude Code gibi çözülür (inceleme #4)."""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.tools.capabilities import CapabilityRegistry

from .fakes import ScriptedProvider, model_result
from .test_system_prompt_layers import _deps


def _agent_tool(monkeypatch, tmp_path, reply="bitti", **changes):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps = replace(deps, capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path), **changes)
    provider = ScriptedProvider([model_result(reply)])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    tool = build_agent_registry(deps, depth=0, run_agent=loop.run_agent).get("Agent")
    assert tool is not None
    return deps, tool, provider


async def test_bilinmeyen_tip_gecerli_ajanlari_sayan_hatayla_reddedilir(monkeypatch, tmp_path):
    deps, tool, provider = _agent_tool(monkeypatch, tmp_path)

    result = await tool.run(
        {"prompt": "Ara", "subagent_type": "nonexistent-agent", "run_in_background": False},
        deps.tool_context,
    )

    assert not result.ok
    assert "Agent type 'nonexistent-agent' not found" in result.output
    assert "general-purpose" in result.output and "Explore" in result.output
    assert not provider.seen_messages


async def test_tip_verilmezse_general_purpose_calisir(monkeypatch, tmp_path):
    deps, tool, _provider = _agent_tool(monkeypatch, tmp_path)
    started = []
    original = deps.publisher.publish

    def _record(event):
        if type(event).__name__ == "SubAgentStarted":
            started.append(event.persona)
        original(event)

    deps.publisher.publish = _record  # type: ignore[method-assign]

    result = await tool.run({"prompt": "Ara", "run_in_background": False}, deps.tool_context)

    assert result.ok, result.output
    assert started == ["general-purpose"]


async def test_general_purpose_yoksa_subagent_type_is_required(monkeypatch, tmp_path):
    deps, tool, provider = _agent_tool(monkeypatch, tmp_path, allowed_agent_types=("Explore",))

    result = await tool.run({"prompt": "Ara", "run_in_background": False}, deps.tool_context)

    assert not result.ok
    assert result.output.startswith(
        "subagent_type is required: the general-purpose agent is not available in this session."
    )
    assert "Available agents: Explore" in result.output
    assert not provider.seen_messages
