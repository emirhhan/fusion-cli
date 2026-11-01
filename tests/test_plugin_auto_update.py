"""Eklenti otomatik güncellemesi (Claude Code plugins/loading.md "When auto-update runs", #394).

Ağ YOK: pazarlar yerel klasördür; yerinde yüklenen eklentinin sürümü kaynakta değiştirilir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.config import trust
from fusion_cli.tools import plugin_auto_update, plugin_install

_ENVS = (
    "DISABLE_UPDATES",
    "DISABLE_AUTOUPDATER",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "FORCE_AUTOUPDATE_PLUGINS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENVS:
        monkeypatch.delenv(name, raising=False)


def _market(tmp_path: Path, name: str = "ekip") -> Path:
    market = tmp_path / name
    plugin = market / "plugins" / "rapor"
    (plugin / ".claude-plugin").mkdir(parents=True)
    _version(plugin, "1.0.0")
    (plugin / "skills" / "ozet").mkdir(parents=True)
    (plugin / "skills" / "ozet" / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
    )
    (market / ".claude-plugin").mkdir(parents=True)
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": name,
                "owner": {"name": "E"},
                "plugins": [{"name": "rapor", "source": "./plugins/rapor"}],
            }
        ),
        "utf-8",
    )
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin(f"rapor@{name}", approve=lambda _p: True)
    return plugin


def _version(plugin: Path, version: str) -> None:
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "rapor", "version": version}), "utf-8"
    )


def _declare(project: Path, auto: bool | None) -> None:
    entry: dict[str, object] = {
        "source": {"source": "directory", "path": str(project.parent / "ekip")}
    }
    if auto is not None:
        entry["autoUpdate"] = auto
    path = project / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"extraKnownMarketplaces": {"ekip": entry}}), "utf-8")
    trust.trust_project(project)


def test_ucuncu_taraf_pazar_varsayilan_kapali(tmp_path):
    plugin = _market(tmp_path)
    _version(plugin, "1.1.0")
    assert plugin_auto_update.auto_update_pass(tmp_path / "proje") == ()


def test_bildirimdeki_autoupdate_true_guncellenir_bildirim_metni(tmp_path):
    plugin = _market(tmp_path)
    project = tmp_path / "proje"
    _declare(project, True)
    _version(plugin, "1.1.0")
    assert plugin_auto_update.auto_update_pass(project) == ("rapor",)
    assert plugin_auto_update.NOTICE.format(name="rapor") == (
        "Plugin updated: rapor · Run /reload-plugins to apply"
    )
    assert plugin_auto_update.auto_update_pass(project) == ()  # zaten güncel


@pytest.mark.parametrize(
    "env", ["DISABLE_UPDATES", "DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"]
)
def test_ortam_degiskeni_kapatir_force_acar(tmp_path, monkeypatch, env):
    plugin = _market(tmp_path)
    project = tmp_path / "proje"
    _declare(project, True)
    _version(plugin, "1.1.0")
    monkeypatch.setenv(env, "1")
    assert plugin_auto_update.auto_update_pass(project) == ()
    monkeypatch.setenv("FORCE_AUTOUPDATE_PLUGINS", "1")
    assert plugin_auto_update.auto_update_pass(project) == ("rapor",)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("claude-plugins-official", True),
        ("knowledge-work-plugins", False),
        ("first-party-plugins", False),
        ("ekip", False),
    ],
)
def test_varsayilan_resmi_pazarlarda_acik(name, expected):
    assert plugin_auto_update.is_auto_update(name, {}) is expected


def test_bildirimdeki_false_resmi_varsayilani_ezer(tmp_path):
    from fusion_cli.tools.plugin_declared import DeclaredMarket

    declared = {
        "claude-plugins-official": DeclaredMarket("claude-plugins-official", "x", "project", False)
    }
    assert plugin_auto_update.is_auto_update("claude-plugins-official", declared) is False
