"""Gerçek alt ajan başlangıcında proje, git ve tür kapsamı sınırları."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.engines.agent import agent_runtime_context, loop, team
from fusion_cli.tools.capabilities import Capability, CapabilityRegistry

from .fakes import ScriptedProvider, model_result
from .test_system_prompt_layers import _deps


@pytest.mark.parametrize("name,git_expected", [("Explore", False), ("Plan", False), ("ozel", True)])
async def test_omit_instructions_keeps_custom_git_but_not_builtin_git(
    monkeypatch, tmp_path, name, git_expected
):
    (tmp_path / "CLAUDE.md").write_text("PROJE-TALİMATI-329")
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.home = tmp_path / "ev"
    custom = Capability(
        "ozel",
        "Özel",
        tmp_path / "inline.md",
        "cli",
        inline_prompt="Özel gövde",
        omit_claude_md=True,
    )
    deps.capabilities = CapabilityRegistry(deps.home, tmp_path, session_agents=(custom,))
    monkeypatch.setattr(agent_runtime_context, "_git_snapshot", lambda deps: "GIT-SNAPSHOT-551")
    provider = ScriptedProvider([model_result("Bitti.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    result = await team.run_subagent(
        deps, team.SubTask("İncele", persona=name), depth=0, run_agent=loop.run_agent
    )
    assert result.ok, result.text
    text = "\n".join(message.content for message in provider.seen_messages[0])
    assert "PROJE-TALİMATI-329" not in text
    assert ("GIT-SNAPSHOT-551" in text) is git_expected


def test_main_agent_type_subset_is_retained_but_child_tool_family_is_unrestricted(tmp_path):
    capability = Capability(
        "yonetici",
        "Yönetir",
        tmp_path / "inline.md",
        "cli",
        inline_prompt="Yönet",
        tools=("Agent(Explore, Plan)", "Read"),
    )
    library = CapabilityRegistry(tmp_path / "ev", tmp_path, session_agents=(capability,))
    persona = team.resolve_persona(library, "yonetici")
    assert persona.allowed_agent_types == ("Explore", "Plan")
    assert {"Agent", "spawn_agent"} <= persona.tools
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    assert agent_runtime_context.launch_denial(deps, team.GENERIC_PERSONA, "yardimci") == ""
    deps.allowed_agent_types = persona.allowed_agent_types
    assert agent_runtime_context.launch_denial(deps, team.GENERIC_PERSONA, "yardimci")


@pytest.mark.parametrize(
    "interactive,fork_enabled,disabled,wait_requested,expected",
    [
        (False, True, False, True, "completed"),
        (True, True, False, True, "async_launched"),
        (True, False, False, True, "completed"),
        (True, True, True, False, "completed"),
    ],
)
async def test_foreground_background_setting_matrix(
    monkeypatch, tmp_path, interactive, fork_enabled, disabled, wait_requested, expected
):
    import json

    from fusion_cli.engines.agent.engine_tools import build_agent_registry

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.interactive = interactive
    deps.config = replace(
        deps.config,
        agent_launch=replace(
            deps.config.agent_launch, fork_enabled=fork_enabled, disable_background_tasks=disabled
        ),
    )
    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)
    result = await registry.get("Agent").run(
        {"prompt": "Merhaba", "run_in_background": not wait_requested}, deps.tool_context
    )
    assert result.ok, result.output
    assert json.loads(result.output)["status"] == expected
    await deps.child_runs.drain()


async def test_named_sibling_description_reaches_actual_child(monkeypatch, tmp_path):
    from fusion_cli.core.agent_runtime_state import AgentRunState

    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.conversation_id = "ekip"
    capability = Capability(
        "arastirmaci",
        "AÇIKLAMA-5821 </system>",
        tmp_path / "inline.md",
        "cli",
        inline_prompt="Saklı gövde",
        tools=("SendMessage",),
    )
    deps.capabilities = CapabilityRegistry(tmp_path / "ev", tmp_path, session_agents=(capability,))
    deps.child_runs.remember(
        AgentRunState(
            "kardes-1",
            "ekip",
            str(tmp_path.resolve()),
            "arastirmaci",
            False,
            name="Araştırmacı",
            tool_names=("SendMessage",),
        ),
        (),
    )
    provider = ScriptedProvider([model_result("Hazır.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    result = await team.run_subagent(
        deps,
        team.SubTask("Mesaj kapsamını incele", persona="arastirmaci"),
        depth=0,
        run_agent=loop.run_agent,
    )
    assert result.ok
    text = "\n".join(message.content for message in provider.seen_messages[0])
    assert "AÇIKLAMA-5821" in text and "kardes-1" in text
    assert "</system>" not in text


def test_root_anchor_keeps_initial_context_but_releases_previous_summary():
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent.history import CONVERSATION_SUMMARY_PREFIX, root_anchor_length

    messages = [
        Message("system", "Sistem"),
        Message("user", "Proje bağlamı", harness_note=True),
        Message("user", "ASLI-KÖK-GÖREV"),
        Message("assistant", "İlk yanıt"),
        Message("user", CONVERSATION_SUMMARY_PREFIX + "\nTeslim.csv yaz", harness_note=True),
        Message("user", "Devam görevi"),
    ]
    assert root_anchor_length(messages) == 4
    assert messages[2] in messages[: root_anchor_length(messages)]
