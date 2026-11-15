"""user kapsamı `~/.claude/settings.json`, managed kapsam ve bildirilen kaynak değişimi (#376)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_scopes, plugin_store
from fusion_cli.tools import plugin_declared, plugin_install


def _market(tmp_path: Path, name: str = "ekip", folder: str = "pazar") -> Path:
    market = tmp_path / folder
    plugin = market / "plugins" / "rapor"
    (plugin / "skills" / "ozet").mkdir(parents=True)
    (plugin / "skills" / "ozet" / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
    )
    (market / ".claude-plugin").mkdir()
    data = {
        "name": name,
        "owner": {"name": "E"},
        "plugins": [{"name": "rapor", "source": "./plugins/rapor"}],
    }
    (market / ".claude-plugin" / "marketplace.json").write_text(json.dumps(data), "utf-8")
    return market


def _user() -> dict[str, object]:
    return json.loads(plugin_scopes.user_settings_file().read_text("utf-8"))


def test_user_kurulum_ac_kapat_kaldir_claude_ayarina_yazar(tmp_path):
    runner = CliRunner()
    added = runner.invoke(app, ["marketplace", "add", str(_market(tmp_path))])
    assert added.exit_code == 0, added.output
    assert "user ayarlarında bildirildi" in " ".join(added.output.split())
    source = _user()["extraKnownMarketplaces"]["ekip"]["source"]
    assert source == {"source": "directory", "path": str(_market_path(tmp_path))}

    assert runner.invoke(app, ["install", "rapor@ekip"]).exit_code == 0
    assert _user()["enabledPlugins"] == {"rapor@ekip": True}
    assert runner.invoke(app, ["disable", "rapor@ekip"]).exit_code == 0
    assert _user()["enabledPlugins"] == {"rapor@ekip": False}
    assert runner.invoke(app, ["uninstall", "rapor@ekip"]).exit_code == 0
    assert _user()["enabledPlugins"] == {}
    assert runner.invoke(app, ["marketplace", "remove", "ekip"]).exit_code == 0
    assert "ekip" not in _user().get("extraKnownMarketplaces", {})


def _market_path(tmp_path: Path) -> Path:
    return (tmp_path / "pazar").resolve()


def test_claude_ayarindaki_false_kurulu_eklentiyi_kapatir(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path)))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    path = plugin_scopes.user_settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabledPlugins": {"rapor@ekip": False}}), "utf-8")

    assert [i.record.name for i in plugin_store.active_plugins(root=tmp_path)] == []


def test_managed_ayar_en_yuksek_oncelik_ve_degistirilemez(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path)))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    managed = plugin_scopes.managed_settings_file()
    managed.parent.mkdir(parents=True, exist_ok=True)
    managed.write_text(json.dumps({"enabledPlugins": {"rapor@ekip": True}}), "utf-8")
    local = tmp_path / ".claude" / "settings.local.json"
    local.parent.mkdir()
    local.write_text(json.dumps({"enabledPlugins": {"rapor@ekip": False}}), "utf-8")

    decision = plugin_scopes.resolve_enabled("rapor@ekip", "rapor", False, tmp_path)
    assert (decision.enabled, decision.scope) == (True, "managed")
    out = CliRunner().invoke(app, ["disable", "rapor@ekip", "--json"])
    payload = json.loads(out.output.strip().splitlines()[-1])
    assert payload["failureCode"] == "managed_settings_override"


def test_bildirilen_kaynak_degisince_pazar_yeniden_cekilir(tmp_path, monkeypatch):
    first = _market(tmp_path)
    second = _market(tmp_path, folder="yeni-pazar")
    plugin_install.add_marketplace(str(first))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    monkeypatch.chdir(tmp_path)
    plugin_scopes.update_user_settings(
        lambda raw: {
            **raw,
            "extraKnownMarketplaces": {
                "ekip": {"source": {"source": "directory", "path": str(second)}}
            },
        }
    )

    assert plugin_declared.sync_declared(tmp_path) == ("ekip",)

    record = plugin_store.load_state().marketplace("ekip")
    assert record is not None and record.source == str(second.resolve())
    assert plugin_store.load_state().plugin("rapor") is not None


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_managed_dosya_yolu_claude_ile_ayni(monkeypatch, platform):
    monkeypatch.undo()
    monkeypatch.setattr("sys.platform", platform)
    expected = {
        "darwin": "/Library/Application Support/ClaudeCode/managed-settings.json",
        "linux": "/etc/claude-code/managed-settings.json",
    }[platform]
    assert str(plugin_scopes.managed_settings_file()) == expected


def test_managed_drop_in_parcalari_okunur():
    managed = plugin_scopes.managed_settings_file()
    (managed.parent / "managed-settings.d").mkdir(parents=True)
    managed.write_text(json.dumps({"enabledPlugins": {"a@m": True, "b@m": True}}), "utf-8")
    (managed.parent / "managed-settings.d" / "10-ek.json").write_text(
        json.dumps({"enabledPlugins": {"b@m": False}}), "utf-8"
    )

    assert plugin_scopes.managed_values() == {"a@m": True, "b@m": False}
