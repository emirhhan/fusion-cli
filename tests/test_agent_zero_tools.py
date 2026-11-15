"""'Agent would be spawned with zero tools' Claude Code'daki gruplarla (inceleme #5)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.tools.capabilities import CapabilityRegistry

from .fakes import ScriptedProvider, model_result
from .test_system_prompt_layers import _deps


async def _run(monkeypatch, tmp_path, tools: str, *, background: bool, extra: str = ""):
    folder = tmp_path / ".claude" / "agents"
    folder.mkdir(parents=True)
    (folder / "x.md").write_text(
        f"---\nname: x\ndescription: d\ntools: {tools}\n{extra}---\nGövde.", encoding="utf-8"
    )
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps = replace(deps, capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path))
    provider = ScriptedProvider([model_result("çalıştı")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    tool = build_agent_registry(deps, depth=0, run_agent=loop.run_agent).get("Agent")
    assert tool is not None
    result = await tool.run(
        {"prompt": "Ara", "subagent_type": "x", "run_in_background": background},
        deps.tool_context,
    )
    return result, provider


@pytest.mark.parametrize("background", (False, True))
async def test_alt_ajana_verilmeyen_araclar_sifir_aracla_reddedilir(
    monkeypatch, tmp_path, background
):
    result, provider = await _run(
        monkeypatch, tmp_path, "AskUserQuestion, Workflow", background=background
    )

    assert not result.ok
    assert result.output.startswith("Agent 'x' would be spawned with zero tools — refusing.")
    assert "not available to subagents [AskUserQuestion, Workflow]" in result.output
    assert not provider.seen_messages


async def test_arka_plan_suzgeci_bosaltirsa_reddedilir(monkeypatch, tmp_path):
    result, provider = await _run(monkeypatch, tmp_path, "ListAgents", background=True)

    assert not result.ok
    assert "not available to subagents [ListAgents]" in result.output
    assert not provider.seen_messages


async def test_disallowed_tools_hepsini_kaldirirsa_reddedilmez(monkeypatch, tmp_path):
    result, _provider = await _run(
        monkeypatch, tmp_path, "Read", background=False, extra="disallowedTools: Read\n"
    )

    assert "zero tools" not in result.output
