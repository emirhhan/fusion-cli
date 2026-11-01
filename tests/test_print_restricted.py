"""`fusion -p --restricted` (#301): komut/kod araçları, ayar katmanları ve bypass kapalı."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run
from fusion_cli.cli.print_restricted import RESTRICTED_TOOLS
from fusion_cli.config.setting_sources import SETTING_SOURCES_ENV

runner = CliRunner()


@pytest.fixture(autouse=True)
def _sources(monkeypatch):
    # Koşu os.environ'a yazar; setenv + delenv test sonunda değişkeni kaldırır.
    monkeypatch.setenv(SETTING_SOURCES_ENV, "")
    monkeypatch.delenv(SETTING_SOURCES_ENV)


def _print(monkeypatch, args):
    calls: list[dict] = []

    async def _fake(task, config, **kwargs):
        import os

        calls.append({"config": config, "sources": os.environ.get(SETTING_SOURCES_ENV), **kwargs})
        return SimpleNamespace(
            final_text="tamam",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    return calls, runner.invoke(app_module.app, args)


def test_kisitli_kip_komut_ve_webfetch_araclarini_kaldirir(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "x", "--restricted"])
    assert result.exit_code == 0, result.output
    allowed = calls[0]["allowed_tools"]
    assert allowed is not None
    assert "run_shell" not in allowed and "web_fetch" not in allowed
    assert {"read_file", "edit_file", "write_file", "grep_search"} <= allowed
    assert allowed <= RESTRICTED_TOOLS


def test_tools_ile_tek_tek_verilen_bash_kalir_default_geri_getirmez(monkeypatch):
    calls, _ = _print(monkeypatch, ["-p", "x", "--restricted", "--tools", "Bash,Read"])
    assert "run_shell" in calls[0]["allowed_tools"]
    calls, _ = _print(monkeypatch, ["-p", "x", "--restricted", "--tools", "default"])
    assert "run_shell" not in calls[0]["allowed_tools"]


def test_kisitli_kip_dosya_araclarini_kokte_tutar_ve_ayar_katmanlarini_kapatir(monkeypatch):
    calls, _ = _print(monkeypatch, ["-p", "x", "--restricted"])
    runtime = calls[0]["config"].runtime
    assert runtime.block_reads_outside_root and runtime.block_writes_outside_root
    assert calls[0]["sources"] == ""


def test_kisitli_kip_settings_kurallarini_yine_uygular(monkeypatch):
    settings = json.dumps({"permissions": {"deny": ["Read(./gizli/**)"]}})
    calls, result = _print(monkeypatch, ["-p", "x", "--restricted", "--settings", settings])
    assert result.exit_code == 0, result.output
    assert any(rule.tool == "Read" for rule in calls[0]["extra_permission_rules"])


@pytest.mark.parametrize(
    "flags",
    [
        ["--permission-mode", "bypassPermissions"],
        ["--dangerously-skip-permissions"],
        ["--settings", json.dumps({"permissions": {"defaultMode": "bypassPermissions"}})],
    ],
)
def test_kisitli_kip_bypass_reddeder(monkeypatch, flags):
    calls, result = _print(monkeypatch, ["-p", "x", "--restricted", *flags])
    assert result.exit_code == 1
    assert "--restricted" in result.output and not calls


def test_init_bayraklari_dusmez_uyarir_init_only_konusma_baslatmaz(monkeypatch):
    calls, result = _print(monkeypatch, ["-p", "x", "--init", "--maintenance"])
    assert result.exit_code == 0, result.output
    assert "--init" in result.output and "--maintenance" in result.output and calls
    calls, result = _print(monkeypatch, ["-p", "--init-only"])
    assert result.exit_code == 0 and not calls
    assert "--init-only" in result.output
