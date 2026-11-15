"""Ana oturum istemi gerçek CLI, REPL, TUI ve RPC çağıranlarından geçer."""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.concurrency import BackgroundTasks
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.memory.factory import null_memory

from .fakes import make_config
from .test_session_agent_prompt_parity import _persona


def _state(tmp_path):
    return ReplState(
        config=make_config(),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
        persona=_persona(),
    )


async def test_repl_turn_forwards_replacement_and_clears_it(monkeypatch, tmp_path):
    from fusion_cli.cli.repl.loop import _agent_turn
    from fusion_cli.engines import agent

    received = []

    async def capture(task, deps, **kwargs):
        received.append(kwargs)
        return AgentOutcome("Tamam.", [], 0, ok=True)

    monkeypatch.setattr(agent, "run_agent", capture)
    state = _state(tmp_path)
    background = BackgroundTasks()
    console = Console(file=io.StringIO())
    await _agent_turn("Merhaba", state, console, background)
    state.persona = None
    await _agent_turn("Devam", state, console, background)
    assert received[0]["system_prompt"] == _persona().prompt
    assert _persona().prompt not in received[0]["extra_system"]
    assert received[1]["system_prompt"] is None


async def test_tui_turn_forwards_persona_and_skill_context(monkeypatch, tmp_path):
    from fusion_cli.cli.repl.tui_loop import _TuiSession

    received = []

    async def capture(task, config, **kwargs):
        received.append(kwargs)
        return AgentOutcome("Tamam.", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", capture)
    state = _state(tmp_path)
    state.pending_digest = "DEVIR_NOTU_123"
    session = _TuiSession(state)
    await session._turn("Merhaba")
    assert received[0]["system_prompt"] == _persona().prompt
    assert "DEVIR_NOTU_123" in received[0]["extra_system"]
    assert _persona().prompt not in received[0]["extra_system"]


@pytest.mark.parametrize("mode", ["kod", "sohbet"])
async def test_rpc_keeps_explicit_chat_prompt_precedence(monkeypatch, tmp_path, mode):
    from fusion_cli.appserver.session import CHAT_SYSTEM_PROMPT, AppSession
    from fusion_cli.cli import session as cli_session

    received = []

    async def capture(task, config, **kwargs):
        received.append(kwargs)
        return AgentOutcome("Tamam.", [], 0, ok=True)

    monkeypatch.setattr(cli_session, "run_agent_task", capture)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    session._state.persona = _persona()
    session._workspace_mode = mode
    await session._run_turn("Merhaba")
    assert received[0]["system_prompt"] == (
        _persona().prompt if mode == "kod" else CHAT_SYSTEM_PROMPT
    )
    assert _persona().prompt not in received[0]["extra_system"]


async def test_fork_turn_explicit_prompt_wins_without_rewriting_parent(monkeypatch, tmp_path):
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent import loop, team_fork

    from .fakes import ScriptedProvider, model_result
    from .test_system_prompt_layers import _deps

    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    history = [Message("system", "ESKI_ISTEM"), Message("user", "önceki görev")]
    result = await team_fork.run_forked_turn(
        "Merhaba",
        _deps(tmp_path, "nvidia_nim/ornek-model"),
        history=history,
        system_prompt="ACIK_ISTEM",
    )
    assert provider.seen_messages[0][0].content.startswith("ACIK_ISTEM")
    assert result.messages[0].content == "ESKI_ISTEM"
