"""Eklenti `settings.json` `agent` varsayılanı (Claude plugins-reference, #389)."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.config.loader import load_config
from fusion_cli.config.plugin_settings import plugin_default_agent
from fusion_cli.tools import plugin_install


def _plugin(tmp_path: Path, agent: str) -> Path:
    folder = tmp_path / "guvenlik"
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "guvenlik"}), "utf-8"
    )
    (folder / "agents").mkdir()
    (folder / "agents" / "denetci.md").write_text(
        "---\nname: denetci\ndescription: Denetler\n---\nDenetle.\n", "utf-8"
    )
    (folder / "settings.json").write_text(json.dumps({"agent": agent}), "utf-8")
    return folder


def test_etkin_eklentinin_agent_ayari_ana_ajan_varsayilani_olur(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plugin_install.install_plugin(str(_plugin(tmp_path, "denetci")), approve=lambda _p: True)

    assert plugin_default_agent(tmp_path) == "guvenlik:denetci"
    config_file = tmp_path / "config.yaml"
    config_file.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    assert load_config(config_file).agent_launch.default_agent == "guvenlik:denetci"


def test_kapali_eklentinin_agent_ayari_uygulanmaz(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    item = plugin_install.install_plugin(str(_plugin(tmp_path, "denetci")), approve=lambda _p: True)
    plugin_install.set_plugin_enabled(item.record.name, False, root=tmp_path)

    assert plugin_default_agent(tmp_path) == ""
