"""`--settings` Claude anahtarları ve `--setting-sources` doğrulaması (#296)."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run
from fusion_cli.engines.agent.approval import ApprovalMode

runner = CliRunner()


def _print(monkeypatch, args):
    calls: list[dict] = []

    async def _fake(task, config, **kwargs):
        calls.append({"config": config, **kwargs})
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


def test_settings_defaultmode_dizin_env_ve_kancalar(monkeypatch, tmp_path):
    monkeypatch.delenv("FUSION_TEST_AYAR", raising=False)
    settings = {
        "permissions": {"defaultMode": "acceptEdits", "additionalDirectories": [str(tmp_path)]},
        "env": {"FUSION_TEST_AYAR": "1"},
        "disableAllHooks": True,
    }
    calls, result = _print(monkeypatch, ["-p", "x", "--settings", json.dumps(settings)])
    assert result.exit_code == 0, result.output
    call = calls[0]
    assert call["mode"] is ApprovalMode.ACCEPT_EDITS
    assert tmp_path in call["extra_roots"]
    assert call["config"].runtime.hooks_enabled is False
    assert os.environ.pop("FUSION_TEST_AYAR") == "1"


def test_permission_mode_bayragi_settings_kipinden_onceliklidir(monkeypatch):
    settings = json.dumps({"permissions": {"defaultMode": "acceptEdits"}})
    calls, _ = _print(
        monkeypatch, ["-p", "x", "--settings", settings, "--permission-mode", "plan"]
    )
    assert calls[0]["mode"] is ApprovalMode.PLAN


def test_setting_sources_gecersiz_kaynak_hatadir(monkeypatch):
    _calls, result = _print(monkeypatch, ["-p", "x", "--setting-sources", "user,herkes"])
    assert result.exit_code == 1 and "herkes" in result.output
