"""`/context [all]` (#207): ızgara, pencere yüzdesi, öneriler, `all`."""

from __future__ import annotations

import io
from dataclasses import replace

import pytest
from rich.console import Console

from fusion_cli.cli.repl import context_view, help_view
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.status_view import context_report
from fusion_cli.core.types import Message
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.fixture
def state(tmp_path):
    return ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def _out(state: ReplState, argument: str = "") -> str:
    console = Console(file=io.StringIO(), force_terminal=False, no_color=True, width=200)
    context_view.render(state, console, argument)
    return console.file.getvalue()


def test_izgara_yuz_hucre_ve_pencereye_gore_baslik(state: ReplState):
    state.history = [Message("user", "a" * 3000), Message("assistant", "b" * 3000)]
    report = context_report(state)
    grid = context_view.grid_lines(report)
    assert len(grid) == 5
    joined = " ".join(grid)
    assert joined.count(context_view.FILLED) + joined.count(context_view.FREE) == 100
    out = _out(state)
    assert "tahmini" in out and "Boş alan" in out and "Kullanıcı" in out


def test_olculen_token_ve_arac_agirligi_onerisi(state: ReplState):
    state.history = [Message("user", "x"), Message("tool", "ç" * 50_000)]
    state.cost.last_prompt_tokens = 12_345
    out = _out(state)
    assert "12,345" in out and "ölçülen" in out
    assert "Araç çıktıları" in out


def test_pencere_asiminda_uyari(state: ReplState):
    report = context_report(state)
    window = report.window_tokens or report.threshold_chars // 3
    tips = context_view.suggestions(replace(report), window + 500)
    assert any("aşıyor" in tip and "/compact" in tip for tip in tips)


def test_all_kirilimi_genisletir_ve_render_arguman_tasir(state: ReplState):
    state.history = [Message("user", "büyük kalem\n" + "y" * 900)]
    assert "En büyük kalemler" not in _out(state)
    out = _out(state, "all")
    assert "En büyük kalemler" in out and "büyük kalem" in out and "Toplam" in out


async def test_help_view_all_argumani_ulasir(state: ReplState):
    state.history = [Message("user", "z" * 300)]
    console = Console(file=io.StringIO(), force_terminal=False, no_color=True, width=200)
    await help_view.render("context", state, build_registry(), console, "all")
    assert "En büyük kalemler" in console.file.getvalue()
