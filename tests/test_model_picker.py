"""Argümansız `/model` seçicisi (#211, Claude Code ModelPicker).

Enter kaydeder, `s` yalnız oturum, sol/sağ effort; Fusion rol alt komutları `/models`'ta,
eski `/model agent` bir kez uyarır.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml

from fusion_cli.cli.repl import commands, model_picker
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.core.reasoning import ReasoningEffort
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui.picker import Choice

_CONFIG = """
agent:
  name: ana
  model: openrouter/qwen/qwen3-coder
candidates:
  - name: hizli
    model: groq/llama-3.3-70b
  - name: yerel
    model: ollama/qwen:7b
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


class _Script:
    """Sırayla verilen cevapları dönen sahte seçici; çağrıları kaydeder."""

    def __init__(self, *answers: str | None) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, tuple[str, ...], str]] = []

    def __call__(
        self, choices: Sequence[Choice], *, title: str, alt_keys=(), initial: str = ""
    ) -> str | None:
        self.calls.append((title, tuple(c.value for c in choices), initial))
        return self.answers.pop(0)


def test_enter_secilen_modeli_kaydeder(state: ReplState) -> None:
    picker = _Script("groq/llama-3.3-70b")
    cikti = commands.model_picker_command(state, picker)
    assert state.config.agent.model == "groq/llama-3.3-70b"
    assert _saved_agent(state) == "groq/llama-3.3-70b"
    assert "kaydedildi" in cikti
    assert picker.calls[0][1][0] == "openrouter/qwen/qwen3-coder"
    assert picker.calls[0][2] == "openrouter/qwen/qwen3-coder"


def test_s_yalniz_oturum_icin_kaydetmez(state: ReplState) -> None:
    cikti = commands.model_picker_command(state, _Script("s:ollama/qwen:7b"))
    assert state.config.agent.model == "ollama/qwen:7b"
    assert _saved_agent(state) == "openrouter/qwen/qwen3-coder"
    assert "yalnız bu oturum" in cikti


def test_oklar_effortu_degistirir_ve_ayni_satirda_yeniden_acar(state: ReplState) -> None:
    state.config = model_picker.apply(
        state.config,
        model_picker.PickResult(state.config.agent.model, ReasoningEffort.MEDIUM, True),
    )[0]
    picker = _Script("right:groq/llama-3.3-70b", "right:groq/llama-3.3-70b", "s:groq/llama-3.3-70b")
    cikti = commands.model_picker_command(state, picker)
    assert state.config.runtime.reasoning_effort is ReasoningEffort.XHIGH
    assert "effort: medium" in picker.calls[0][0] and "effort: high" in picker.calls[1][0]
    assert picker.calls[1][2] == "groq/llama-3.3-70b"
    assert "xhigh" in cikti


def test_effort_uclarda_durur() -> None:
    assert model_picker.step_effort(ReasoningEffort.AUTO, -1) is ReasoningEffort.AUTO
    assert model_picker.step_effort(ReasoningEffort.MAX, 1) is ReasoningEffort.MAX


def test_esc_vazgecer(state: ReplState) -> None:
    once = state.config
    assert "yapılmadı" in commands.model_picker_command(state, _Script(None))
    assert state.config is once


def test_borulu_girdide_liste_basar(state: ReplState, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    cikti = build_registry().get("model").handler(state, "")  # type: ignore[union-attr]
    assert "agent : openrouter/qwen/qwen3-coder" in cikti


def test_models_rol_alt_komutlari_ve_eski_model_alt_komutu_uyarir(state: ReplState) -> None:
    registry = build_registry()
    models = registry.get("models")
    model = registry.get("model")
    assert models is not None and model is not None
    assert "Kullanım: /models" in models.handler(state, "sonnet")
    assert "hakem modeli" in models.handler(state, "judge groq/llama-3.3-70b")
    ilk = model.handler(state, "agent openai/gpt-5")
    assert state.config.agent.model == "openai/gpt-5" and "/models agent" in ilk
    assert "/models" not in model.handler(state, "agent openai/gpt-4o")


async def test_tui_model_seciciyi_modalda_acar(state: ReplState) -> None:
    from fusion_cli.cli.repl.tui_loop import _TuiSession

    session = _TuiSession(state)
    answers = iter(["left:openrouter/qwen/qwen3-coder", "openrouter/qwen/qwen3-coder"])
    seen: list[tuple[str, tuple[str, ...], str]] = []

    async def fake_choice(title, choices, *, alt_keys=(), searchable=False, initial=""):
        seen.append((title, alt_keys, initial))
        return next(answers)

    session.tui.await_choice = fake_choice  # type: ignore[method-assign]
    await session._command("/model")
    assert seen[0][1] == model_picker.ALT_KEYS
    assert state.config.runtime.reasoning_effort is model_picker.step_effort(
        load_config(Path(state.config.source)).runtime.reasoning_effort,
        -1,  # type: ignore[arg-type]
    )
