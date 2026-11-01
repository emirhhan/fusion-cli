"""Claude Code `statusLine` ayarı, tetikleri ve çıktısı (#192)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from fusion_cli.cli.repl import status_line_runner as runner_module
from fusion_cli.cli.repl.status_line_runner import (
    StatusLineRunner,
    ansi_for_tui,
    format_output,
    run_script,
)
from fusion_cli.cli.repl.status_line_settings import (
    StatusLineSpec,
    parse_status_line,
    resolve_status_line,
)
from fusion_cli.cli.repl.tui import format_status

from .fakes import make_config


def test_statusline_nesnesi_okunur():
    spec = parse_status_line(
        {"type": "command", "command": "~/s.sh", "padding": 2, "refreshInterval": 0.2,
         "hideVimModeIndicator": True},
        "user",
    )
    assert spec == StatusLineSpec("~/s.sh", 2, 1, True, "user")
    assert parse_status_line({"type": "other", "command": "x"}, "user") is None
    assert parse_status_line({"command": " "}, "user") is None


def test_kullanici_claude_ayari_okunur_guvensiz_proje_okunmaz(tmp_path: Path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    (home / ".claude").mkdir(parents=True)
    (root / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"statusLine": {"type": "command", "command": "echo ev"}}), encoding="utf-8"
    )
    (root / ".claude" / "settings.json").write_text(
        json.dumps({"statusLine": {"type": "command", "command": "echo proje"}}), encoding="utf-8"
    )
    spec = resolve_status_line(make_config(memory_dir=tmp_path / "m"), root, home)
    assert spec is not None and spec.command == "echo ev"


def test_cok_satir_ansi_ve_padding_korunur():
    assert format_output("\x1b[32mbir\x1b[0m\niki\n\n", padding=1) == " \x1b[32mbir\x1b[0m\n iki"
    assert format_output("  \n") == ""


def test_osc8_sifir_genislikli_kacisa_sarilir():
    link = "\x1b]8;;https://x.com\x1b\\bağ\x1b]8;;\x1b\\"
    assert ansi_for_tui(link) == "\x01\x1b]8;;https://x.com\x1b\\\x02bağ\x01\x1b]8;;\x1b\\\x02"


def test_cok_satirli_cikti_yerlesik_cubugun_yerine_gecmez():
    html = format_status("auto", "agent", "bağlam %3", custom="bir\niki")
    assert "bağlam %3" in html


@pytest.mark.asyncio
async def test_betik_columns_lines_ve_stdin_alir(tmp_path: Path):
    spec = StatusLineSpec('python3 -c "import json,os,sys; d=json.load(sys.stdin); '
                          "print(d['a'], os.environ['COLUMNS'].isdigit(), "
                          "os.environ['LINES'].isdigit())\"")
    assert await run_script(spec, {"a": "x"}, cwd=str(tmp_path)) == "x True True"


@pytest.mark.asyncio
async def test_tetikler_debounce_edilir_suren_betik_iptal_edilir(tmp_path: Path, monkeypatch):
    calls: list[str] = []
    outputs: list[str] = []

    async def _run(spec, payload, *, cwd):
        calls.append(payload["n"])
        await asyncio.sleep(0.05)
        return f"çıktı {payload['n']}"

    monkeypatch.setattr(runner_module, "run_script", _run)
    counter = iter(range(100))
    runner = StatusLineRunner(
        lambda: StatusLineSpec("echo x"),
        lambda: {"n": str(next(counter))},
        outputs.append,
        cwd_source=lambda: str(tmp_path),
        debounce_s=0.05,
    )
    runner.request()  # komut ilk kez görülüyor: debounce atlanır
    await asyncio.sleep(0.01)
    for _ in range(3):
        runner.request()
    await asyncio.sleep(0.2)
    await runner.close()

    # İlk koşu iptal edildi, ardışık üç istek tek koşuya indi.
    assert outputs == [f"çıktı {calls[-1]}"]
    assert len(calls) == 2
