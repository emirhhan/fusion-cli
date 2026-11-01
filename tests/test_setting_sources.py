"""`--setting-sources` yalnız adı geçen ayar katmanlarını yükler (#296)."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run
from fusion_cli.config import setting_sources
from fusion_cli.config.agent_launch_compat import read_agent_launch
from fusion_cli.config.agent_launch_settings import AgentLaunchConfig
from fusion_cli.config.hooks import load_hooks, user_hooks_file
from fusion_cli.config.permission_rules import load_permission_rules

runner = CliRunner()
ENV = setting_sources.SETTING_SOURCES_ENV


@pytest.fixture
def home(monkeypatch, tmp_path):
    home = tmp_path / "ev"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    # setenv + delenv: test sonunda değişken yok sayılır (koşu os.environ'a yazar).
    monkeypatch.setenv(ENV, "")
    monkeypatch.delenv(ENV)
    return home


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _deny(tool):
    return {"permissions": {"deny": [tool]}}


def _project(tmp_path):
    root = tmp_path / "proje"
    _write(root / ".claude" / "settings.json", _deny("WebFetch"))
    _write(root / ".claude" / "settings.local.json", _deny("Write"))
    return root


def _tools(root):
    return {rule.tool for rule in load_permission_rules(root).rules}


def test_degisken_yoksa_butun_katmanlar_yuklenir(home, tmp_path):
    _write(home / ".claude" / "settings.json", _deny("Bash"))
    assert _tools(_project(tmp_path)) == {"Bash", "WebFetch", "Write"}


def test_yalniz_adi_gecen_kaynaklar_yuklenir(home, tmp_path, monkeypatch):
    _write(home / ".claude" / "settings.json", _deny("Bash"))
    root = _project(tmp_path)
    monkeypatch.setenv(ENV, "project")
    assert _tools(root) == {"WebFetch"}
    monkeypatch.setenv(ENV, "user,local")
    assert _tools(root) == {"Bash", "Write"}
    monkeypatch.setenv(ENV, "")
    assert _tools(root) == set()


def test_fusion_kullanici_kancalari_user_kaynagina_baglidir(home, tmp_path, monkeypatch):
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    hook = {"type": "command", "command": "echo x"}
    _write(user_hooks_file(), {"hooks": {"Stop": [{"hooks": [hook]}]}})
    assert load_hooks(tmp_path, home=home).commands
    monkeypatch.setenv(ENV, "project,local")
    assert not load_hooks(tmp_path, home=home).commands


def test_ajan_ayarlari_user_kaynagi_kapaliyken_okunmaz(home, tmp_path, monkeypatch):
    _write(home / ".claude" / "settings.json", {"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "haiku"}})
    loaded = read_agent_launch(AgentLaunchConfig(), home=home, root=tmp_path, environ={})
    monkeypatch.setenv(ENV, "project")
    narrowed = read_agent_launch(AgentLaunchConfig(), home=home, root=tmp_path, environ={})
    assert loaded != narrowed
    assert narrowed == read_agent_launch(
        AgentLaunchConfig(), home=tmp_path / "bos", root=tmp_path, environ={}
    )


def test_print_setting_sources_etkisiz_uyarisi_vermez_ve_listeyi_ayarlar(home, monkeypatch):
    seen: list[str | None] = []

    async def _fake(task, config, **kwargs):
        seen.append(os.environ.get(ENV))
        return SimpleNamespace(
            final_text="tamam",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    result = runner.invoke(app_module.app, ["-p", "x", "--setting-sources", "User, project"])
    assert result.exit_code == 0, result.output
    assert "etkisiz" not in result.output
    assert seen == ["user,project"]


def test_kok_komut_setting_sources_dogrular_ve_alt_komuta_uygular(home, monkeypatch, tmp_path):
    bad = runner.invoke(app_module.app, ["--setting-sources", "user,herkes", "permissions"])
    assert bad.exit_code == 1 and "herkes" in bad.output
    monkeypatch.chdir(tmp_path)
    good = runner.invoke(app_module.app, ["--setting-sources", "local", "permissions"])
    assert good.exit_code == 0, good.output
    assert os.environ.get(ENV) == "local"


def test_kok_komut_settings_env_kanca_ve_dizinleri_uygular(home, monkeypatch, tmp_path):
    from fusion_cli.config.readiness import Readiness

    seen: dict[str, object] = {}

    async def _repl(config, **kwargs):
        seen.update(kwargs, config=config, env=os.environ.get("FUSION_TEST_KOK"))
        return 0

    monkeypatch.setattr(app_module, "run_repl", _repl)
    monkeypatch.setattr(
        app_module, "evaluate", lambda *_a, **_k: SimpleNamespace(state=Readiness.READY)
    )
    monkeypatch.setenv("FUSION_TEST_KOK", "")
    extra = tmp_path / "ek"
    extra.mkdir()
    settings = {
        "env": {"FUSION_TEST_KOK": "1"},
        "disableAllHooks": True,
        "permissions": {"additionalDirectories": [str(extra)], "deny": ["Bash"]},
    }
    result = runner.invoke(app_module.app, ["--settings", json.dumps(settings)])
    assert result.exit_code == 0, result.output
    assert seen["env"] == "1"
    assert seen["config"].runtime.hooks_enabled is False
    assert extra in seen["extra_roots"]
    assert "permissions.deny" in result.output
