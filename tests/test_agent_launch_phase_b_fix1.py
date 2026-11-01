from __future__ import annotations

import asyncio
import io
import json

import pytest
from rich.console import Console

from fusion_cli.appserver import session as app_session
from fusion_cli.appserver.protocol import Request
from fusion_cli.cli import session as cli_session
from fusion_cli.cli.repl import commands, persona_commands
from fusion_cli.cli.repl.loop import _agent_turn
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.concurrency import BackgroundTasks
from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.core.worktree import Worktree
from fusion_cli.engines import agent
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.memory.factory import null_memory
from tests.fakes import ScriptedProvider, make_config, model_result


def setup_persona(tmp_path):
    path = tmp_path / ".claude/agents/review.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nname: review\ndescription: Review\nmodel: sahte/persona\n"
        "effort: high\n---\nReview only."
    )


async def test_makbuzlu_rpc_uygulanmis_kisilik_modelini_kullanir(tmp_path, monkeypatch):
    setup_persona(tmp_path)
    config = make_config(
        memory_dir=tmp_path / "memory",
        task_model_map={},
        agent=ModelSpec("original", "sahte/original"),
    )
    monkeypatch.setattr(app_session, "load_config", lambda: config)
    provider = ScriptedProvider([model_result("Tamam.")])
    observed = []

    def build(spec, **kwargs):
        observed.append(spec.model)
        return provider

    monkeypatch.setattr(loop, "build_provider", build)
    session = app_session.AppSession(lambda packet: None, root=tmp_path, home=tmp_path / "home")
    try:
        assert session._apply_persona("review") is None
        result = await session._dispatch(
            Request("first", "tur.calistir", {"gorev": "Merhaba", "gonderim_id": "first"})
        )
        assert result["ok"], result
        assert session._state.main_config_applied
        assert session._state.config.agent.model == "sahte/persona"
        assert observed and observed[0] == "sahte/persona"
    finally:
        await session.close()


async def test_kisilik_sonrasi_ilk_tur_oncesi_acik_model_secimi_korunur(tmp_path, monkeypatch):
    setup_persona(tmp_path)
    state = ReplState(
        config=make_config(memory_dir=tmp_path / "memory", task_model_map={}),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "home",
    )
    persona_commands.persona(state, "review")
    assert state.persona is not None
    commands._model(state, "agent sahte/manual")
    assert state.config.agent.model == "sahte/manual"
    observed = []

    async def capture(task, deps, **kwargs):
        observed.append(deps.config.agent.model)
        return AgentOutcome("Tamam.", [], 0, ok=True)

    monkeypatch.setattr(agent, "run_agent", capture)
    try:
        await _agent_turn("Merhaba", state, Console(file=io.StringIO()), BackgroundTasks())
        assert observed == ["sahte/manual"]
    finally:
        await state.child_runs.close()


async def test_rpc_arac_kok_gecisinden_once_eski_ajanlari_kapatir(tmp_path, monkeypatch):
    config = make_config(memory_dir=tmp_path / "memory", task_model_map={})
    monkeypatch.setattr(app_session, "load_config", lambda: config)
    target = tmp_path / "other-root"
    target.mkdir()
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def background():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    session = app_session.AppSession(lambda packet: None, root=tmp_path, home=tmp_path / "home")
    owner = session._state.child_runs
    owner.start("old-child", background)
    await started.wait()

    async def capture(task, config, **kwargs):
        kwargs["worktree_switch"].request(Worktree("other", target, "other", tmp_path, "base"))
        return AgentOutcome(
            "Tamam.", [Message("user", task), Message("assistant", "Tamam.")], 0, ok=True
        )

    monkeypatch.setattr(cli_session, "run_agent_task", capture)
    try:
        result = await session._run_turn("Merhaba")
        assert result["ok"]
        assert session._state.root == target
        assert (
            session._state.child_runs is not owner
            and not owner.running("old-child")
            and cleaned.is_set()
        )
    finally:
        await session.close()
    assert cleaned.is_set()


@pytest.mark.parametrize(
    "hooks",
    [
        {"PreToolUse": {"hooks": [{"type": "command", "command": "SECRET_SENTINEL"}]}},
        {"PreToolUse": [{"hooks": {"type": "command", "command": "SECRET_SENTINEL"}}]},
        {
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": "SECRET_SENTINEL", "shell": "zsh"}]}
            ]
        },
        {"PreToolUse": [False]},
        {"PreToolUse": [{"hooks": [False]}]},
        {"PreToolUse": [{"matcher": ["SECRET_SENTINEL"], "hooks": []}]},
        ["SECRET_SENTINEL"],
    ],
)
def test_gecersiz_kanca_ana_cli_cagrisini_engeller(tmp_path, monkeypatch, hooks):
    from fusion_cli.cli import app as app_module
    from tests.test_headless import _agent

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        app_module, "_session_config", lambda: make_config(memory_dir=tmp_path / "memory")
    )
    raw = json.dumps({"denetci": {"prompt": "İncele.", "description": "d", "hooks": hooks}})
    seen, result = _agent(monkeypatch, ["Görev", "--agent", "denetci", "--agents", raw])
    assert result.exit_code == 2 and not seen
    assert "SECRET_SENTINEL" not in result.output


@pytest.mark.parametrize(
    "hooks",
    [
        {"PreToolUse": {"hooks": [{"type": "command", "command": "SECRET_SENTINEL"}]}},
        {"PreToolUse": [{"hooks": {"type": "command", "command": "SECRET_SENTINEL"}}]},
        {
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": "SECRET_SENTINEL", "shell": "zsh"}]}
            ]
        },
        {"PreToolUse": [False]},
        {"PreToolUse": [{"hooks": [False]}]},
        {"PreToolUse": [{"matcher": ["SECRET_SENTINEL"], "hooks": []}]},
        ["SECRET_SENTINEL"],
    ],
)
async def test_gecersiz_kanca_alt_ajan_cagrisini_engeller(tmp_path, monkeypatch, hooks):
    import yaml

    from fusion_cli.engines.agent.team import spawn_agent_tool
    from tests.test_team_settings import _deps

    path = tmp_path / ".claude/agents/denetci.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\n"
        + yaml.safe_dump({"name": "denetci", "description": "d", "hooks": hooks})
        + "---\nGövde."
    )
    deps, _ = _deps(tmp_path)

    async def forbidden(*args, **kwargs):
        pytest.fail("Geçersiz koruyucu kanca yürütücüye ulaşmamalı")

    outcome = await spawn_agent_tool(deps, depth=0, run_agent=forbidden).run(
        {"task": "incele", "uzman": "denetci"}, deps.tool_context
    )
    assert "desteklenmiyor" in outcome.output and "SECRET_SENTINEL" not in outcome.output


@pytest.mark.parametrize("hooks", [{}, {"PreToolUse": []}, {"PreToolUse": [{"hooks": []}]}])
def test_bos_gecerli_kanca_ajan_secimini_engellemez(tmp_path, hooks):
    from dataclasses import replace

    from fusion_cli.engines.agent.team import GENERIC_PERSONA
    from fusion_cli.engines.agent.team_settings import main_agent_config
    from fusion_cli.tools.frontmatter import normalize_agent_fields

    fields = normalize_agent_fields({"hooks": hooks})
    persona = replace(GENERIC_PERSONA, hook_definitions=fields["hook_definitions"])
    assert main_agent_config(make_config(), persona).agent.model


@pytest.mark.parametrize("surface", ["repl", "tui"])
async def test_arac_kok_gecisi_tum_terminal_yuzeylerinde_once_eski_gorevi_bekler(
    tmp_path, monkeypatch, surface
):
    from fusion_cli.cli.repl.tui_loop import _TuiSession

    state = ReplState(
        config=make_config(memory_dir=tmp_path / "memory"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "home",
    )
    target = tmp_path / "newroot"
    target.mkdir()
    switch = Worktree("new", target, "new", tmp_path, "base")
    old = state.child_runs
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def background():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            assert state.root == tmp_path
            cleaned.set()

    old.start("old-child", background)
    await started.wait()

    async def capture(task, deps, **kwargs):
        if surface == "repl":
            deps.tool_context.worktree_switch.request(switch)
        else:
            kwargs["tool_context"].worktree_switch.request(switch)
        return AgentOutcome("Tamam.", [], 0, ok=True)

    try:
        if surface == "repl":
            monkeypatch.setattr(agent, "run_agent", capture)
            await _agent_turn("Geç", state, Console(file=io.StringIO()), BackgroundTasks())
        else:
            monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", capture)
            await _TuiSession(state)._turn("Geç")
        assert cleaned.is_set() and state.root == target
        assert state.child_runs is not old and state.child_runs.persistent
    finally:
        await state.child_runs.close()
        await old.close()


async def test_kok_gecis_basarisiz_olursa_yeni_sahip_eski_kokte_tutar_bos_tur_korumali(
    tmp_path, monkeypatch
):
    from fusion_cli.cli.repl import worktrees
    from fusion_cli.core.worktree import WorktreeSwitch

    state = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "home"
    )
    old = state.child_runs
    assert await state.apply_worktree_switch(WorktreeSwitch()) == ""
    assert state.child_runs is old
    switch = WorktreeSwitch()
    switch.request(Worktree("new", tmp_path / "new", "new", tmp_path, "base"))
    monkeypatch.setattr(worktrees, "apply_switch_request", lambda state, switch: "")
    assert await state.apply_worktree_switch(switch) == ""
    assert state.root == tmp_path and state.child_runs is not old
    await state.child_runs.close()
