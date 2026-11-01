"""Özelleştirilebilir durum satırı (P-069): JSON yükü, betik çalıştırma, /statusline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.input import ReplInput
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.status_line import (
    run_status_line,
    status_line_text,
    status_payload,
    statusline_command,
)
from fusion_cli.cli.repl.tui import format_status
from fusion_cli.config.loader import load_config
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.memory.factory import null_memory


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def test_json_yuku_claude_semasini_tasir(state: ReplState):
    """Alan adları Claude Code statusline "Full JSON schema" ile aynı (#191)."""
    payload = status_payload(state)
    zorunlu = {
        "cwd",
        "session_id",
        "transcript_path",
        "model",
        "workspace",
        "version",
        "output_style",
        "cost",
        "context_window",
        "exceeds_200k_tokens",
        "fast_mode",
        "thinking",
        "fusion",
    }
    assert zorunlu <= set(payload)
    assert payload["model"]["id"] == state.config.agent.model
    assert set(payload["model"]) == {"id", "display_name"}
    assert payload["workspace"]["project_dir"] == str(state.root)
    assert payload["workspace"]["added_dirs"] == []
    assert set(payload["cost"]) == {
        "total_cost_usd",
        "total_duration_ms",
        "total_api_duration_ms",
        "total_lines_added",
        "total_lines_removed",
    }
    assert set(payload["context_window"]) == {
        "total_input_tokens",
        "total_output_tokens",
        "context_window_size",
        "used_percentage",
        "remaining_percentage",
        "current_usage",
    }
    # İlk API çağrısından önce Claude'daki gibi null.
    assert payload["context_window"]["current_usage"] is None
    assert payload["session_id"] == state.conversation_id
    assert payload["fusion"]["approval_mode"] == "auto"
    # Belgede "may be absent": ad, ajan, PR, worktree yokken yazılmaz.
    assert not {"session_name", "agent", "pr", "worktree", "vim"} & set(payload)
    json.dumps(payload)


def test_adli_sohbet_session_name_tasir(state: ReplState):
    state.conversation_name = "oyun"
    assert status_payload(state)["session_name"] == "oyun"


def test_betik_stdin_json_alir_ilk_satir_doner(state: ReplState):
    komut = (
        'python3 -c "import json,sys; d=json.load(sys.stdin); '
        "print(d['model']['id']); print('ikinci')\""
    )
    assert run_status_line(komut, status_payload(state)) == state.config.agent.model


def test_hatali_ve_zaman_asimli_betik_bos_doner(state: ReplState, caplog):
    assert run_status_line("exit 3", status_payload(state)) == ""
    assert run_status_line("sleep 5", status_payload(state)) == ""
    assert "durum satırı betiği" in caplog.text


@pytest.mark.asyncio
async def test_ayarsizken_bos_eski_runtime_komutu_takma_ad(state: ReplState):
    from dataclasses import replace

    assert await status_line_text(state) == ""
    state.config = replace(
        state.config, runtime=replace(state.config.runtime, status_line_command="echo 'özel'")
    )
    assert await status_line_text(state) == "özel"


def test_statusline_istegi_modele_devreder(state: ReplState):
    assert build_registry().get("statusline") is not None
    note = statusline_command(state, "model adını ve git dalını göster")
    assert "statusline-setup" in note
    assert "model adını ve git dalını göster" in state.pending_task
    assert '"statusLine"' in state.pending_task
    statusline_command(state, "")
    assert "PS1" in state.pending_task


def test_durum_cubuklari_ozel_satiri_kacirarak_gosterir(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    reader = ReplInput(tmp_path / "h", [], mode=ApprovalMode.AUTO)
    reader.context = "agent · general"
    reader.custom_status = "<b>özel</b> & satır"
    html = reader.status_bar()
    assert (
        "&lt;b&gt;özel&lt;/b&gt; &amp; satır" in html.value and "agent · general" not in html.value
    )
    tui_html = format_status("auto", "agent", "bağlam %3", custom="<x> özel")
    assert "&lt;x&gt; özel" in tui_html and "bağlam %3" not in tui_html


@pytest.mark.asyncio
async def test_satir_ici_repl_butun_satirlari_ansi_ile_basar(state: ReplState):
    """#192: düz REPL de Claude Code gibi çok satırlı, ANSI renkli çıktıyı gösterir."""
    import io
    from dataclasses import replace

    from fusion_cli.cli.repl.status_line import show_status_block, status_line_block

    komut = "printf '\\033[32mbir\\033[0m\\niki\\n'"
    state.config = replace(
        state.config, runtime=replace(state.config.runtime, status_line_command=komut)
    )
    blok = await status_line_block(state)
    assert blok == "\x1b[32mbir\x1b[0m\niki"
    akis = io.StringIO()
    show_status_block(akis, blok)
    assert akis.getvalue() == "\x1b[32mbir\x1b[0m\niki\n"
    akis = io.StringIO()
    show_status_block(akis, "")
    assert akis.getvalue() == ""
