"""Claude Code Bash ayarları (#332, #351, #356, #357, #358).

Claude: `timeout` (ms) parametresi, BASH_DEFAULT_TIMEOUT_MS=2 dk / BASH_MAX_TIMEOUT_MS=10 dk,
satır içi çıktı ~30.000 (BASH_MAX_OUTPUT_LENGTH), CLAUDE_CODE_DISABLE_BACKGROUND_TASKS,
`run_in_background` ve `dangerouslyDisableSandbox` parametre adları.
"""

from __future__ import annotations

import subprocess

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import shell
from fusion_cli.tools.bash_settings import (
    output_limit,
    timeout_seconds,
    wants_background,
)
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.sandbox_runtime import asks_unsandboxed


def test_timeout_varsayilan_ve_tavan():
    assert timeout_seconds({}, {}) == 120.0
    assert timeout_seconds({"timeout": 5000}, {}) == 5.0
    assert timeout_seconds({"timeout": 10_000_000}, {}) == 600.0
    ortam = {"BASH_DEFAULT_TIMEOUT_MS": "30000", "BASH_MAX_TIMEOUT_MS": "60000"}
    assert timeout_seconds({}, ortam) == 30.0
    assert timeout_seconds({"timeout": 90_000}, ortam) == 60.0
    assert timeout_seconds({"timeout": "x"}, {}) == 120.0


def test_cikti_siniri_claude_degeri_ve_ortam():
    assert output_limit({}) == 30_000
    assert output_limit({"BASH_MAX_OUTPUT_LENGTH": "500"}) == 500
    assert output_limit({"BASH_MAX_OUTPUT_LENGTH": "-1"}) == 30_000


def test_arka_plan_adi_ve_kapatma_anahtari():
    assert wants_background({"run_in_background": True}, {})
    assert wants_background({"background": True}, {})  # eski ad
    assert not wants_background({"run_in_background": True}, {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"})


def test_sandbox_disi_parametre_claude_adi_ve_eski_ad():
    assert asks_unsandboxed({"dangerouslyDisableSandbox": True})
    assert asks_unsandboxed({"unsandboxed": True})
    assert not asks_unsandboxed({})


def test_run_shell_semasi_claude_adlarini_tasir():
    ozellikler = build_registry().get("run_shell").parameters["properties"]
    assert {"timeout", "run_in_background", "dangerouslyDisableSandbox"} <= set(ozellikler)
    assert "background" not in ozellikler and "unsandboxed" not in ozellikler


def test_run_shell_timeout_parametresini_uygular(tmp_path, monkeypatch):
    gorulen: list[float] = []

    def _sahte(command, *, timeout_s, **_):
        gorulen.append(timeout_s)
        return subprocess.CompletedProcess(command, 0, "tamam", "")

    monkeypatch.setattr(shell, "run_foreground", _sahte)
    sonuc = shell.run_shell({"command": "echo a", "timeout": 3000}, ToolContext(root=tmp_path))
    assert sonuc.ok and gorulen == [3.0]


def test_bashes_tasks_komutunun_diger_adi():
    """Claude Code: /bashes, /tasks'ın diğer adı (#333)."""
    from fusion_cli.cli.repl.commands import build_registry as build_commands

    komutlar = build_commands()
    assert komutlar.get("bashes") is not None
    assert komutlar.get("bashes").name == "tasks"
