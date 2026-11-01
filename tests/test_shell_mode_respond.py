"""`!` kabuk kipi: çıktı bağlama girince model kendiliğinden yanıtlar (#219).

Claude Code: `respondToBashCommands: false` (settings.json) yalnız bağlama ekler.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from rich.console import Console

from fusion_cli.cli.repl import loop as loop_module
from fusion_cli.cli.repl.loop import run_shell_prefix_line
from fusion_cli.cli.repl.shell_mode import responds_to_bash_commands
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages

from .fakes import make_config


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    root = tmp_path / "proje"
    root.mkdir()
    return ReplState(config=make_config(), memory=null_memory(), root=root, home=tmp_path / "ev")


def _console() -> Console:
    return Console(file=io.StringIO(), force_terminal=False, no_color=True, width=120)


def _ayar(path: Path, value: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"respondToBashCommands": value}), encoding="utf-8")


async def test_varsayilan_cikti_sonrasi_yanit_turu_hazirlanir(state) -> None:
    await run_shell_prefix_line("echo selam", state, _console())

    task, _mode = state.take_pending()
    assert "echo selam" in task
    assert state.pending_blocks  # çıktı yine bağlamda


async def test_ayar_kapaliyken_yalniz_baglama_eklenir(state) -> None:
    _ayar(state.root / ".claude" / "settings.json", False)
    console = _console()

    await run_shell_prefix_line("echo selam", state, console)

    assert state.take_pending() == ("", state.pending_mode)
    assert messages.SHELL_PREFIX_CONTEXT_NOTE in console.file.getvalue()


def test_yerel_katman_projeyi_ezer(state) -> None:
    _ayar(state.home / ".claude" / "settings.json", False)
    assert responds_to_bash_commands(state.root, state.home) is False
    _ayar(state.root / ".claude" / "settings.local.json", True)
    assert responds_to_bash_commands(state.root, state.home) is True


async def test_satir_ici_yol_kabuktan_sonra_turu_baslatir(state, monkeypatch) -> None:
    calls: list[str] = []

    async def sahte_tur(task, state, console, background, *, mode=None, **_):
        calls.append(task)
        return False

    monkeypatch.setattr(loop_module, "_run_turn", sahte_tur)
    from fusion_cli.cli.repl.commands import build_registry
    from fusion_cli.core.concurrency import BackgroundTasks

    class _Okuyucu:
        mode = state.approval
        interactive = False
        custom_status = ""

        def __getattr__(self, name):
            return lambda *a, **k: None

    await loop_module._handle(
        "!echo selam", state, build_registry(), _Okuyucu(), _console(), BackgroundTasks()
    )

    assert len(calls) == 1 and "echo selam" in calls[0]
