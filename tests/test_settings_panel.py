"""Claude Code Settings paneli (#210, #225): Status · Config · Usage sekmeleri.

Argümansız `/config` Config sekmesini, `/status` Status sekmesini açar; ←/→ sekme değiştirir,
Config'te Enter değer listesini açar ve seçim `/config key=value` ile kalıcı uygulanır.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest

from fusion_cli.appserver.commands import command_choices
from fusion_cli.cli.repl import settings_panel
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import theme
from fusion_cli.ui.picker import Choice


@pytest.fixture(autouse=True)
def _koyuya_don():
    yield
    theme.apply_palette(theme.DEFAULT_THEME)


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


class _Script:
    def __init__(self, *answers: str | None) -> None:
        self.answers = list(answers)
        self.titles: list[str] = []
        self.rows: list[tuple[str, ...]] = []
        self.initials: list[str] = []

    def __call__(
        self, title: str, choices: Sequence[Choice], keys: tuple[str, ...], initial: str
    ) -> str | None:
        self.titles.append(title)
        self.rows.append(tuple(c.value for c in choices))
        self.initials.append(initial)
        return self.answers.pop(0)


def test_config_sekmesinde_secim_kalici_uygulanir(state: ReplState, tmp_path: Path) -> None:
    ask = _Script("editorMode", "vim", None)
    notes = settings_panel.run(state, ask)
    assert "[Config]" in ask.titles[0]
    assert ask.rows[0] == ("model", "theme", "outputStyle", "editorMode", "tui")
    assert ask.initials[1] == "normal"
    assert state.config.runtime.vim_mode is True
    assert load_config(tmp_path / "config.yaml").runtime.vim_mode is True
    assert "vim" in notes


def test_oklar_sekme_degistirir_status_ve_usage_bilgi_satirlari(state: ReplState) -> None:
    ask = _Script("right:theme", "left:info:0", "left:theme", "info:0")
    settings_panel.run(state, ask)
    assert "[Usage]" in ask.titles[1] and "[Config]" in ask.titles[2]
    assert "[Status]" in ask.titles[3]
    assert all(value.startswith("info:") for value in ask.rows[3])
    assert len(ask.titles) == 4  # Status'ta Enter paneli kapatır


def test_tema_secimi_claude_adiyla(state: ReplState) -> None:
    settings_panel.run(state, _Script("theme", "light", None))
    assert state.config.runtime.terminal_theme == "acik"
    assert settings_panel.config_values(state)["theme"] == "light"


def test_tui_degisince_panel_kapanir(state: ReplState) -> None:
    state.surface = "fullscreen"
    ask = _Script("tui", "default", "theme")
    settings_panel.run(state, ask)
    assert state.surface_switch == "inline" and len(ask.titles) == 2


def test_masaustu_ayar_ve_deger_adimlari(state: ReplState) -> None:
    first = command_choices(state, "config", "")
    assert first is not None and first["adim"] == "ayar"
    assert [row["deger"] for row in first["secenekler"]][:2] == ["model", "theme"]
    second = command_choices(state, "config", "editorMode")
    assert second is not None and second["devam"]["arguman_on_eki"] == "editorMode="
    assert command_choices(state, "config", "editorMode=vim") is None
    assert command_choices(state, "config", "runtime") is None


async def test_tui_status_paneli_status_sekmesinde_acar(state: ReplState) -> None:
    from fusion_cli.cli.repl.tui_loop import _TuiSession

    session = _TuiSession(state)
    gorev = asyncio.ensure_future(session._command("/status"))
    await asyncio.sleep(0.05)
    assert session.tui._mode == "choice"
    assert "[Status]" in session.tui._choice_title
    session.tui._resolve(None)
    await gorev


async def test_tui_argumansiz_config_paneli_acar(state: ReplState) -> None:
    from fusion_cli.cli.repl.tui_loop import _TuiSession

    session = _TuiSession(state)
    gorev = asyncio.ensure_future(session._command("/config"))
    await asyncio.sleep(0.05)
    assert "[Config]" in session.tui._choice_title
    session.tui._resolve(None)
    await gorev


async def test_satir_ici_status_paneli_terminalde_acar(
    state: ReplState, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rich.console import Console

    from fusion_cli.cli.repl import commands, loop

    seen: list[str] = []

    def fake_pick(choices, *, title, alt_keys=(), initial=""):
        seen.append(title)
        return None

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(commands, "pick", fake_pick)

    class _Reader:
        mode = None
        vim_mode = False

    registry = commands.build_registry()
    reader = _Reader()
    await loop._run_command("/status", state, registry, reader, Console(record=True))  # type: ignore[arg-type]
    assert seen and "[Status]" in seen[0]
