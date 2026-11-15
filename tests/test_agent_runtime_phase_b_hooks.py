"""Ajan tanımı kancaları gerçek döngüde yalnız kendi ömründe çalışır."""

from __future__ import annotations

from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet, HookVerdict
from fusion_cli.engines.agent import loop, team
from fusion_cli.engines.hooks.session import HookSession

from .fakes import ScriptedProvider, model_result
from .test_system_prompt_layers import _deps


async def test_child_stop_hooks_are_scoped_and_translated(monkeypatch, tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.home = tmp_path / "ev"
    definition = deps.home / ".claude/agents/uzman.md"
    definition.parent.mkdir(parents=True)
    definition.write_text("Ajan.")
    original = HookSession(tmp_path, loader=lambda: HookSet())
    deps.hooks = original
    persona = team.Persona(
        "uzman",
        "Uzman",
        "u",
        "gri",
        source="claude",
        definition_path=definition,
        hook_definitions=HookSet((HookCommand(HookEvent.STOP, "", "yerel-stop", 1),)),
    )
    monkeypatch.setattr(team, "resolve_persona", lambda *args: persona)
    provider = ScriptedProvider([model_result("Tamamlandı.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    observed = []

    async def emit(self, event, *, subjects=(), fields=None):
        observed.extend((event, item.command) for item in self.current().for_event(event, subjects))
        return HookVerdict()

    monkeypatch.setattr(HookSession, "emit", emit)
    result = await team.run_subagent(deps, team.SubTask("Görev"), depth=0, run_agent=loop.run_agent)
    assert result.ok
    assert (HookEvent.SUBAGENT_STOP, "yerel-stop") in observed
    assert original.current().commands == ()
    assert deps.hooks is original


async def test_main_persona_hooks_apply_once_across_turns(monkeypatch, tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.home = tmp_path / "ev"
    definition = deps.home / ".claude/agents/uzman.md"
    definition.parent.mkdir(parents=True)
    definition.write_text("Ajan.")
    deps.session_persona = team.Persona(
        "uzman",
        "Uzman",
        "u",
        "gri",
        source="claude",
        definition_path=definition,
        hook_definitions=HookSet((HookCommand(HookEvent.USER_PROMPT_SUBMIT, "", "ana-kanca", 1),)),
    )
    provider = ScriptedProvider([model_result("Bir."), model_result("İki.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    counts = []

    async def emit(self, event, *, subjects=(), fields=None):
        if event is HookEvent.USER_PROMPT_SUBMIT:
            counts.append(len(self.current().for_event(event, subjects)))
        return HookVerdict()

    monkeypatch.setattr(HookSession, "emit", emit)
    first = await loop.run_agent("Bir", deps)
    await loop.run_agent("İki", deps, history=first.messages)
    assert counts == [1, 1]


async def test_inline_mcp_isolated_registry_and_awaited_cleanup(monkeypatch, tmp_path):
    from contextlib import asynccontextmanager

    from fusion_cli.config.models import McpServerConfig
    from fusion_cli.core.tools import Tool, ToolResult

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.home = tmp_path / "ev"
    definition = deps.home / ".claude/agents/uzman.md"
    definition.parent.mkdir(parents=True)
    definition.write_text("Ajan")
    persona = team.Persona(
        "uzman",
        "Uzman",
        "u",
        "gri",
        source="claude",
        definition_path=definition,
        inline_mcp_servers=(McpServerConfig("yerel", command="sahte"),),
    )
    monkeypatch.setattr(team, "resolve_persona", lambda *args: persona)
    lifecycle = []

    @asynccontextmanager
    async def connector(config, registry):
        lifecycle.append("açıldı")
        registry.register_or_replace(
            Tool(
                "yerel__oku",
                "Sahte yerel araç",
                {"type": "object"},
                lambda args, context: ToolResult("kanıt"),
            )
        )
        try:
            yield
        finally:
            lifecycle.append("kapandı")

    deps.mcp_connector = connector
    seen = []

    async def run(task, child, **kwargs):
        seen.append(child.base_registry.names())
        return loop.AgentOutcome("Tamam", [])

    result = await team.run_subagent(deps, team.SubTask("Görev"), depth=0, run_agent=run)
    assert result.ok and lifecycle == ["açıldı", "kapandı"]
    assert "yerel__oku" in seen[0] and "yerel__oku" not in deps.base_registry.names()


async def test_main_hook_lifetime_survives_fresh_turn_dependencies(monkeypatch, tmp_path):
    from dataclasses import replace

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.home = tmp_path / "ev"
    definition = deps.home / ".claude/agents/uzman.md"
    definition.parent.mkdir(parents=True)
    definition.write_text("Ajan")
    deps.hooks = HookSession(tmp_path, loader=lambda: HookSet())
    deps.session_persona = team.Persona(
        "uzman",
        "Uzman",
        "u",
        "gri",
        source="claude",
        definition_path=definition,
        hook_definitions=HookSet((HookCommand(HookEvent.SESSION_START, "", "bir-kez", 1),)),
    )
    events = []

    async def emit(self, event, *, subjects=(), fields=None):
        events.extend(command.command for command in self.current().for_event(event, subjects))
        return HookVerdict()

    monkeypatch.setattr(HookSession, "emit", emit)
    provider = ScriptedProvider([model_result("Bir"), model_result("İki")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    first = await loop.run_agent("Bir", deps)
    next_turn = replace(deps, main_metadata_applied=False, budget=None)
    await loop.run_agent("İki", next_turn, history=first.messages)
    assert events.count("bir-kez") == 1


async def test_subagent_stop_has_actual_saved_transcript_and_identity(monkeypatch, tmp_path):
    import asyncio
    import json
    from pathlib import Path

    from fusion_cli.engines.agent.engine_tools import build_agent_registry

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.hooks = HookSession(tmp_path, loader=HookSet)
    provider = ScriptedProvider([model_result("SON-KANIT-7823")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    observed = []

    async def emit(self, event, *, subjects=(), fields=None):
        if event is HookEvent.SUBAGENT_STOP:
            observed.append(dict(fields or {}))
            path = Path(fields["agent_transcript_path"])
            assert await asyncio.to_thread(path.is_file)
            assert "SON-KANIT-7823" in await asyncio.to_thread(path.read_text)
        return HookVerdict()

    monkeypatch.setattr(HookSession, "emit", emit)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    result = await registry.get("Agent").run(
        {"prompt": "Kanıtı tamamla", "run_in_background": False}, deps.tool_context
    )
    assert result.ok, result.output
    receipt = json.loads(result.output)
    assert observed[0]["agent_id"] == receipt["agentId"]
    assert observed[0]["agent_transcript_path"] == receipt["transcriptPath"]
