"""`/config key=value ...` Claude ayar adları, çoklu çift, `/settings` takma adı (#210) ve
`/vim` yerine `editorMode` (#217)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages, theme


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


@pytest.fixture(autouse=True)
def _palet_geri_yukle():
    once = theme.CURRENT_THEME
    yield
    theme.apply_palette(once)


def _saved(state: ReplState) -> dict:
    return yaml.safe_load(Path(state.config.source).read_text("utf-8"))  # type: ignore[arg-type]


def _config(state: ReplState, argument: str, name: str = "config") -> str:
    command = build_registry().get(name)
    assert command is not None
    return command.handler(state, argument)


def test_settings_config_takma_adidir() -> None:
    registry = build_registry()
    assert registry.get("settings") is registry.get("config")


def test_birden_cok_cift_tek_komutta_yazilir(state: ReplState) -> None:
    cikti = _config(state, "runtime.max_tokens=8192 runtime.agent_max_steps=40")

    assert state.config.runtime.max_tokens == 8192
    assert state.config.runtime.agent_max_steps == 40
    assert "runtime.max_tokens" in cikti and "runtime.agent_max_steps" in cikti


def test_editor_mode_vim_kipini_acar_ve_kaydeder(state: ReplState) -> None:
    _config(state, "editorMode=vim")
    assert state.config.runtime.vim_mode is True
    assert _saved(state)["runtime"]["vim_mode"] is True

    _config(state, "editorMode=normal")
    assert state.config.runtime.vim_mode is False


def test_theme_claude_adlari_terminal_paletine_eslenir(state: ReplState) -> None:
    _config(state, "theme=light")
    assert state.config.runtime.terminal_theme == "acik"
    _config(state, "theme=dark-daltonized")
    assert state.config.runtime.terminal_theme == "daltonizm"


def test_output_style_anahtari(state: ReplState) -> None:
    _config(state, "outputStyle=explanatory")
    assert state.config.runtime.output_style == "explanatory"


def test_model_anahtari_model_komutuna_gider(state: ReplState) -> None:
    _config(state, "model=openai/gpt-5")
    assert state.config.agent.model == "openai/gpt-5"


def test_gecersiz_cift_digerlerini_durdurmaz(state: ReplState) -> None:
    cikti = _config(state, "editorMode=emacs runtime.max_tokens=1234")
    assert state.config.runtime.max_tokens == 1234
    assert "emacs" in cikti


def test_help_bayragi_kullanim_basar(state: ReplState) -> None:
    assert _config(state, "--help") == messages.CONFIG_HELP


def test_vim_komutu_kullanimdan_kalkti_uyarir(state: ReplState) -> None:
    ilk = _config(state, "on", name="vim")
    ikinci = _config(state, "off", name="vim")

    assert ilk.startswith(messages.VIM_DEPRECATED)
    assert messages.VIM_DEPRECATED not in ikinci
    assert state.config.runtime.vim_mode is False
