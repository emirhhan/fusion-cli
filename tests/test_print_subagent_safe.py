"""`--append-subagent-system-prompt(-file)` ve `--safe-mode` (#301)."""

from __future__ import annotations

import os
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run
from fusion_cli.engines.agent import loop, subagent_prompt
from fusion_cli.engines.agent.engine_tools import build_agent_registry

from .fakes import ScriptedProvider, model_result
from .test_system_prompt_layers import _deps

runner = CliRunner()


def _system_text(messages) -> str:
    return "\n".join(str(m.content) for m in messages if m.role == "system")


async def _child(deps) -> str:
    tool = build_agent_registry(deps, depth=0, run_agent=loop.run_agent).get("Agent")
    assert tool is not None
    await tool.run(
        {
            "prompt": "Merhaba",
            "description": "Kısa",
            "subagent_type": "general-purpose",
            "run_in_background": False,
        },
        deps.tool_context,
    )
    return ""


async def test_alt_ajan_istemine_oturum_metni_eklenir(monkeypatch, tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    provider = ScriptedProvider([model_result("bitti")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    with subagent_prompt.appended("HER ALT AJANA KURAL"):
        await _child(deps)
    assert "HER ALT AJANA KURAL" in _system_text(provider.seen_messages[0])


async def test_metin_verilmezse_alt_ajan_istemi_degismez(monkeypatch, tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    provider = ScriptedProvider([model_result("bitti")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    await _child(deps)
    assert "HER ALT AJANA KURAL" not in _system_text(provider.seen_messages[0])


def _print(monkeypatch, args):
    calls: list[dict] = []

    async def _fake(task, config, **kwargs):
        calls.append({"config": config, "append": subagent_prompt.current(), **kwargs})
        return SimpleNamespace(
            final_text="t",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    return calls, runner.invoke(app_module.app, args)


def test_p_bayragi_kosu_boyunca_alt_ajan_metnini_ayarlar(monkeypatch, tmp_path):
    rules = tmp_path / "kurallar.txt"
    rules.write_text("DOSYADAN KURAL", encoding="utf-8")
    calls, result = _print(
        monkeypatch, ["-p", "x", "--append-subagent-system-prompt-file", str(rules)]
    )
    assert result.exit_code == 0, result.output
    assert calls[0]["append"] == "DOSYADAN KURAL"
    assert subagent_prompt.current() == ""


def test_iki_alt_ajan_bayragi_birlesmez(monkeypatch, tmp_path):
    rules = tmp_path / "k.txt"
    rules.write_text("a", encoding="utf-8")
    _calls, result = _print(
        monkeypatch,
        [
            "-p",
            "x",
            "--append-subagent-system-prompt",
            "b",
            "--append-subagent-system-prompt-file",
            str(rules),
        ],
    )
    assert result.exit_code == 1 and "cannot be used together" in result.output


def test_safe_mode_ozellestirmeleri_kapatir_araclari_birakir(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SAFE_MODE", raising=False)
    raw = '{"mcpServers": {"dosya": {"command": "npx", "args": ["x"]}}}'
    calls, result = _print(monkeypatch, ["-p", "x", "--safe-mode", "--mcp-config", raw])
    assert result.exit_code == 0, result.output
    config = calls[0]["config"]
    assert config.runtime.hooks_enabled is False and config.mcp_servers == ()
    assert config.runtime.project_instructions is False
    assert calls[0]["allowed_tools"] is None
    assert type(calls[0]["memory"].lessons).__name__.startswith("Null")
    assert os.environ.pop("CLAUDE_CODE_SAFE_MODE") == "1"
