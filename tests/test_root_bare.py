"""Kök komutta (etkileşimli) `--bare` (#298)."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import launch_prompts as lp
from fusion_cli.cli.print_runtime import BARE_TOOLS
from fusion_cli.cli.repl.persona_commands import PersonaTurn
from fusion_cli.config.loader import load_config

runner = CliRunner()


def _skill(base: Path, name: str) -> None:
    folder = base / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: deneme\n---\ngövde\n", encoding="utf-8"
    )


def test_kok_bare_ozellestirmeleri_kapatir(monkeypatch):
    from fusion_cli.config.readiness import Readiness

    monkeypatch.delenv("CLAUDE_CODE_SIMPLE", raising=False)
    seen: dict[str, object] = {}

    async def _repl(config, **kwargs):
        seen.update(kwargs, config=config)
        return 0

    monkeypatch.setattr(app_module, "run_repl", _repl)
    monkeypatch.setattr(
        app_module, "evaluate", lambda *_a, **_k: SimpleNamespace(state=Readiness.READY)
    )
    result = runner.invoke(app_module.app, ["--bare"])
    assert result.exit_code == 0, result.output
    config = seen["config"]
    assert config.runtime.hooks_enabled is False and config.mcp_servers == ()
    assert config.runtime.project_instructions is False
    assert config.runtime.auto_memory is False
    assert config.runtime.skill_index_chars == 0
    assert config.agent_launch.disable_background_tasks is True
    assert type(seen["memory"].lessons).__name__.startswith("Null")
    spec = seen["launch_prompts"]
    assert isinstance(spec, lp.LaunchSpec) and spec.bare and not spec.snapshot
    assert os.environ.pop("CLAUDE_CODE_SIMPLE") == "1"


def test_bare_repl_katalogu_ve_arac_kumesi(monkeypatch, tmp_path):
    home, project, extra = tmp_path / "ev", tmp_path / "proje", tmp_path / "ek"
    for path in (home, project, extra):
        path.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)
    _skill(project, "proje-beceri")
    _skill(extra, "ek-beceri")
    state = SimpleNamespace(
        config=load_config(),
        conversation_id="c1",
        extra_roots=(extra,),
        session_agents=(),
        capabilities=None,
    )
    state.launch_prompts = lp.bind(
        state, lp.LaunchSpec(lp.LaunchPrompts(), bare=True), resumed=None
    )
    names = {item.name for item in state.capabilities.skills()}
    assert "ek-beceri" in names and "proje-beceri" not in names
    turn = lp.apply_to_turn(PersonaTurn(allowed_tools={"read_file", "web_search"}), state)
    assert turn.allowed_tools == {"read_file"}
    assert lp.apply_to_turn(PersonaTurn(), state).allowed_tools == set(BARE_TOOLS)


def test_bare_olmayan_acilis_arac_kumesini_degistirmez(tmp_path):
    state = SimpleNamespace(config=SimpleNamespace(memory_dir=tmp_path), conversation_id="c1")
    state.launch_prompts = lp.bind(state, lp.LaunchSpec(lp.LaunchPrompts()), resumed=None)
    assert lp.apply_to_turn(PersonaTurn(), state).allowed_tools is None
