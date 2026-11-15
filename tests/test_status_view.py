"""`/status` ve `/context` (P-027): oturum durumu ve bağlam kırılımı."""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from fusion_cli.cli.repl import help_view
from fusion_cli.cli.repl.commands import RENDERED_COMMANDS, build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.status_view import (
    context_label,
    context_report,
    context_rows,
    status_rows,
)
from fusion_cli.cli.repl.tui import format_status
from fusion_cli.core.types import Message
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.fixture
def state(tmp_path):
    return ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def _console() -> Console:
    return Console(file=io.StringIO(), force_terminal=False, no_color=True, width=120)


def test_status_ve_context_kayitli_ve_kendi_ciktisini_basar():
    registry = build_registry()
    assert registry.get("status") is not None and registry.get("context") is not None
    assert {"status", "context"} <= RENDERED_COMMANDS


def test_status_satirlari_surum_model_kip_dizin_icerir(state):
    rows = dict(status_rows(state))
    assert rows["Motor"] == "agent"
    assert rows["İzin kipi"] == "auto"
    assert state.config.agent.model in rows["Model"]
    assert str(state.root) in rows["Dizin"]
    assert rows["Sohbet"] == state.conversation_id
    assert rows["MCP sunucuları"] == "(yok)"


def test_context_kirilimi_rolleri_ayri_sayar(state):
    state.history = [
        Message("system", "s" * 300),
        Message("user", "u" * 100),
        Message("assistant", "a" * 50),
        Message("tool", "t" * 150, tool_call_id="1", name="read_file"),
    ]
    report = context_report(state)
    assert (report.system_chars, report.user_chars, report.assistant_chars, report.tool_chars) == (
        300,
        100,
        50,
        150,
    )
    assert report.total_chars == 600 and report.message_count == 4
    assert 0 <= report.percent <= 100
    labels = [label for label, _ in context_rows(report)]
    assert labels[0] == "Sistem istemi" and "Toplam" in labels


def test_bos_gecmiste_sayac_bos_doluysa_yuzde_verir(state):
    assert context_label(state) == ""
    state.history = [Message("user", "merhaba " * 100)]
    label = context_label(state)
    assert label.startswith("bağlam %") and "tok" in label


@pytest.mark.asyncio
async def test_render_status_ve_context_basilir(state):
    state.history = [Message("user", "selam")]
    for name in ("status", "context"):
        console = _console()
        await help_view.render(name, state, build_registry(), console)
        out = console.file.getvalue()
        assert out.strip()
    assert "Bağlam penceresi" in out and "Toplam" in out


def test_tui_durum_satiri_baglam_sayacini_tasir():
    html = format_status("auto", "agent", "bağlam %12 · ~3k tok")
    assert "bağlam %12" in html
    assert "bağlam" not in format_status("auto", "agent")


def test_context_sistem_istemi_ve_arac_tanimlari_tahminle_sayilir(state):
    """Ölçüldü (31 Ekim): yeni oturumda `/context` 'Sistem 0 tok' gösteriyor, araç şemaları ve
    bekleyen `!`/`@` bağlamı hiç sayılmıyordu; sayaç gerçek doluluğu sistematik eksik gösteriyordu.
    """
    state.pending_blocks = ["x" * 400]
    report = context_report(state)
    assert report.system_estimated and report.system_chars > 1_000
    assert report.tool_schema_chars > 1_000 and report.pending_chars == 400
    rows = dict(context_rows(report))
    assert "Sistem istemi (tahmini)" in rows and "Araç tanımları (tahmini)" in rows
    assert "Bekleyen bağlam (!/@)" in rows
    # Gerçek sistem mesajı gelince tahmin yerine o sayılır.
    state.history = [Message("system", "s" * 300), Message("user", "u")]
    report = context_report(state)
    assert not report.system_estimated and report.system_chars == 300
    assert "Sistem istemi" in dict(context_rows(report))


def test_status_oturum_turu_ve_baglanti_satiri(state):
    """Claude Code `/status` (#225): Session kind ve bağlantı satırları."""
    rows = dict(status_rows(state))
    assert rows["Session kind"] == "interactive"
    assert rows["Bağlantı"]
    assert rows["Çıktı stili"] == "default"
