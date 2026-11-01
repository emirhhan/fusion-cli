"""Ana ajan ayarları gerçek başlatma yoluna uygulanır."""

from __future__ import annotations

import dataclasses

from fusion_cli.core.reasoning import ReasoningEffort
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import team_settings
from fusion_cli.engines.agent.team import GENERIC_PERSONA
from tests.fakes import make_config


def test_ana_ajan_modeli_ve_eforu_ana_yapilandirmaya_uygulanir_ortam_force_uygulanmaz():
    config = make_config()
    from fusion_cli.config.agent_launch_settings import AgentLaunchConfig

    config = dataclasses.replace(
        config,
        candidates=(ModelSpec("haiku", "sahte/haiku"),),
        agent_launch=AgentLaunchConfig(subagent_model="sonnet", force_subagent_model=True),
    )
    persona = dataclasses.replace(GENERIC_PERSONA, model="haiku", effort="high")
    assert hasattr(team_settings, "main_agent_config")
    chosen = team_settings.main_agent_config(config, persona)
    assert chosen.agent.model == "sahte/haiku"
    assert chosen.runtime.reasoning_effort is ReasoningEffort.HIGH
    assert config.agent.model != chosen.agent.model


def test_gercek_headless_cli_persona_ayarlarini_ve_ilk_istemi_yurutucuye_tasir(
    tmp_path, monkeypatch
):
    from fusion_cli.cli import app as app_module
    from tests.test_headless import _agent

    monkeypatch.chdir(tmp_path)
    config = make_config(memory_dir=tmp_path / "memory")
    monkeypatch.setattr(app_module, "_session_config", lambda: config)
    agent = tmp_path / ".claude" / "agents" / "denetci.md"
    agent.parent.mkdir(parents=True)
    agent.write_text(
        "---\nname: denetci\ndescription: inceler\nmodel: sahte/istenen\n"
        "initialPrompt: Önce incele.\neffort: high\nmaxTurns: 3\n---\nGövde."
    )
    seen, result = _agent(monkeypatch, ["Kullanıcı görevi", "--agent", "denetci"])
    assert result.exit_code == 0, result.output
    assert seen.get("session_persona") is not None
    assert seen["session_persona"].model == "sahte/istenen"
    assert seen["task"] == "Önce incele.\n\nKullanıcı görevi"


async def test_gercek_repl_ilk_istemi_bir_kez_ekler_ve_tipli_personayi_tasir(tmp_path, monkeypatch):
    import io

    from rich.console import Console

    from fusion_cli.cli.repl.loop import _agent_turn
    from fusion_cli.core.concurrency import BackgroundTasks
    from fusion_cli.engines import agent
    from fusion_cli.engines.agent.loop import AgentOutcome
    from tests.test_session_prompt_callers import _state

    state = _state(tmp_path)
    state.persona = dataclasses.replace(
        state.persona, initial_prompt="İlk istek.", model="sahte/istenen"
    )
    seen = []

    async def capture(task, deps, **kwargs):
        seen.append((task, deps.session_persona))
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr(agent, "run_agent", capture)
    background = BackgroundTasks()
    console = Console(file=io.StringIO())
    await _agent_turn("Görev", state, console, background)
    await _agent_turn("Devam", state, console, background)
    assert seen[0] == ("İlk istek.\n\nGörev", state.persona)
    assert seen[1] == ("Devam", state.persona)


async def test_gercek_tui_tipli_personayi_ve_ilk_gorevi_yurutucuye_tasir(tmp_path, monkeypatch):
    from fusion_cli.cli.repl.tui_loop import _TuiSession
    from fusion_cli.engines.agent.loop import AgentOutcome
    from tests.test_session_prompt_callers import _state

    state = _state(tmp_path)
    state.persona = dataclasses.replace(state.persona, initial_prompt="İlk görev.")
    seen = []

    async def capture(task, config, **kwargs):
        seen.append((task, kwargs["session_persona"]))
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", capture)
    session = _TuiSession(state)
    await session._turn("Kullanıcı görevi")
    assert seen == [("İlk görev.\n\nKullanıcı görevi", state.persona)]


async def test_gercek_rpc_tipli_personayi_ve_ilk_gorevi_yurutucuye_tasir(tmp_path, monkeypatch):
    from fusion_cli.appserver.session import AppSession
    from fusion_cli.cli import session as cli_session
    from fusion_cli.engines.agent.loop import AgentOutcome

    seen = []

    async def capture(task, config, **kwargs):
        seen.append((task, kwargs["session_persona"]))
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr(cli_session, "run_agent_task", capture)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    session._state.persona = dataclasses.replace(GENERIC_PERSONA, initial_prompt="İlk görev.")
    await session._run_turn("Kullanıcı görevi")
    await session._run_turn("Devam")
    assert seen == [
        ("İlk görev.\n\nKullanıcı görevi", session._state.persona),
        ("Devam", session._state.persona),
    ]


def test_agents_json_gercek_cli_yolunda_proje_ajanini_golgeler(tmp_path, monkeypatch):
    import json

    from fusion_cli.cli import app as app_module
    from tests.test_headless import _agent

    monkeypatch.chdir(tmp_path)
    config = make_config(memory_dir=tmp_path / "memory")
    monkeypatch.setattr(app_module, "_session_config", lambda: config)
    agent = tmp_path / ".claude" / "agents" / "denetci.md"
    agent.parent.mkdir(parents=True)
    agent.write_text("---\nname: denetci\ndescription: proje\n---\nPROJE")
    raw = json.dumps(
        {"denetci": {"description": "CLI", "prompt": "CLI_GOVDE", "model": "sahte/cli"}}
    )
    seen, result = _agent(monkeypatch, ["Görev", "--agents", raw, "--agent", "denetci"])
    assert result.exit_code == 0, result.output
    assert seen["session_persona"].prompt == "CLI_GOVDE"
    assert seen["session_persona"].source == "cli"
    managed = tmp_path / "managed" / "agents"
    managed.mkdir(parents=True)
    (managed / "denetci.md").write_text(
        "---\nname: denetci\ndescription: yönetilen\n---\nYONETILEN"
    )
    config = dataclasses.replace(
        config,
        agent_launch=dataclasses.replace(config.agent_launch, managed_agent_roots=(str(managed),)),
    )
    seen, result = _agent(monkeypatch, ["Görev", "--agents", raw, "--agent", "denetci"])
    assert result.exit_code == 0, result.output
    assert seen["session_persona"].prompt == "YONETILEN"


def test_acik_etkin_model_kisiligin_tanimiyla_ezilmez(tmp_path):
    from fusion_cli.engines.agent.agent_launch_runtime import prepare_main_agent
    from tests.test_team_settings import _deps

    deps, _ = _deps(tmp_path)
    explicit = ModelSpec("açık", "sahte/kullanici")
    deps.active_model_override = explicit
    persona = dataclasses.replace(GENERIC_PERSONA, model="sahte/tanim")
    prepare_main_agent(deps, persona)
    assert deps.active_model_override is explicit
    assert deps.config.agent is explicit


async def test_kisilik_ayarlari_bir_kez_uygulanir_sonraki_kullanici_secimini_ezmez(
    tmp_path, monkeypatch
):
    import io

    from rich.console import Console

    from fusion_cli.cli.repl.loop import _agent_turn
    from fusion_cli.core.concurrency import BackgroundTasks
    from fusion_cli.engines import agent
    from fusion_cli.engines.agent.loop import AgentOutcome
    from tests.test_session_prompt_callers import _state

    state = _state(tmp_path)
    state.persona = dataclasses.replace(state.persona, model="sahte/tanim", effort="high")
    seen = []

    async def capture(task, deps, **kwargs):
        seen.append(deps.config)
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr(agent, "run_agent", capture)
    background = BackgroundTasks()
    console = Console(file=io.StringIO())
    await _agent_turn("Görev", state, console, background)
    assert seen[-1].agent.model == "sahte/tanim"
    selected = dataclasses.replace(
        state.config,
        agent=ModelSpec("kullanıcı", "sahte/sonraki"),
        runtime=dataclasses.replace(state.config.runtime, reasoning_effort=ReasoningEffort.LOW),
    )
    state.config = selected
    await _agent_turn("Devam", state, console, background)
    assert seen[-1].agent.model == "sahte/sonraki"
    assert seen[-1].runtime.reasoning_effort is ReasoningEffort.LOW
