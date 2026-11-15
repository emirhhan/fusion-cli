"""`/model <ad>` doğrudan geçer ve varsayılan olarak kaydeder (#211, Claude Code commands)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fusion_cli.cli.repl.commands import build_registry, model_command_result
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory

_CONFIG = """
agent:
  name: ana
  model: openrouter/qwen/qwen3-coder
candidates:
  - name: hizli
    model: groq/llama-3.3-70b
  - name: claude
    model: anthropic/claude-sonnet-4-5
task_model_map:
  general: hizli
  code: hizli
  reasoning: hizli
  agent: hizli
"""


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text(_CONFIG, encoding="utf-8")
    return ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def _saved_agent(state: ReplState) -> str:
    data = yaml.safe_load(Path(state.config.source).read_text("utf-8"))  # type: ignore[arg-type]
    return data["agent"]["model"]


def _run(state: ReplState, argument: str) -> str:
    command = build_registry().get("model")
    assert command is not None
    return command.handler(state, argument)


def test_tam_kimlik_agent_modelini_degistirir_ve_kaydeder(state: ReplState) -> None:
    cikti = _run(state, "openai/gpt-5")

    assert state.config.agent.model == "openai/gpt-5"
    assert _saved_agent(state) == "openai/gpt-5"
    assert "openai/gpt-5" in cikti


def test_claude_takma_adi_aday_ailesine_cozulur(state: ReplState) -> None:
    _run(state, "sonnet")
    assert state.config.agent.model == "anthropic/claude-sonnet-4-5"
    assert _saved_agent(state) == "anthropic/claude-sonnet-4-5"


def test_aday_adi_kabul_edilir(state: ReplState) -> None:
    _run(state, "hizli")
    assert state.config.agent.model == "groq/llama-3.3-70b"


def test_claude_dash_kimligi_anthropic_onekini_alir(state: ReplState) -> None:
    _run(state, "claude-opus-4-1")
    assert state.config.agent.model == "anthropic/claude-opus-4-1"


def test_cozulemeyen_ad_degistirmez(state: ReplState) -> None:
    once = state.config
    cikti = _run(state, "opus")
    assert state.config is once
    assert "opus" in cikti


def test_eski_agent_alt_komutu_hala_calisir_ve_kaydetmez(state: ReplState) -> None:
    result = model_command_result(state, ["agent", "openai/gpt-5"])
    assert result.ok and result.config.agent.model == "openai/gpt-5"
    assert _saved_agent(state) == "openrouter/qwen/qwen3-coder"


def test_masaustu_yolu_da_kaydeder(state: ReplState) -> None:
    result = model_command_result(state, ["openai/gpt-5"])
    assert result.ok
    assert _saved_agent(state) == "openai/gpt-5"
