"""REPL `/plugin` paneli ve Claude alt komut tablosu (Claude Code `/plugin`, #382, #379)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.cli.repl import plugin_command as repl_plugin
from fusion_cli.cli.repl import plugin_panel
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config import plugin_store
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools import plugin_install


def _market(tmp_path: Path) -> Path:
    market = tmp_path / "pazar"
    plugin = market / "plugins" / "rapor"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "rapor", "version": "1.0.0"}), "utf-8"
    )
    (plugin / "SKILL.md").write_text("---\nname: rapor\ndescription: R\n---\nR\n", "utf-8")
    (market / ".claude-plugin").mkdir(parents=True)
    entries = [{"name": "rapor", "source": "./plugins/rapor", "description": "Rapor yazar"}]
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "ekip", "owner": {"name": "E"}, "plugins": entries}), "utf-8"
    )
    return market


@pytest.fixture
def state(tmp_path, monkeypatch) -> ReplState:
    home, root = tmp_path / "ev", tmp_path / "proje"
    home.mkdir()
    root.mkdir()
    monkeypatch.chdir(root)
    config_file = tmp_path / "config.yaml"
    config_file.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    plugin_install.add_marketplace(str(_market(tmp_path)))
    return ReplState(config=load_config(config_file), memory=null_memory(), root=root, home=home)


def _script(*answers: str | None):
    seen: list[str] = []
    queue = list(answers)

    def choose(choices, title):
        seen.append(title)
        values = [c.value for c in choices]
        answer = queue.pop(0)
        assert answer is None or answer in values, (answer, values)
        return answer

    return choose, seen


def test_panel_discover_sekmesinde_acilir_kapsam_secip_kurar(state):
    choose, seen = _script("install:rapor@ekip", "scope:user:rapor@ekip")

    message = plugin_panel.run_sync(state, choose)

    assert seen[0].startswith("Eklentiler · Discover")
    assert "Kurulum kapsamı" in seen[1] and "Rapor yazar" in seen[1]
    assert "Kuruldu: rapor@ekip (kapsam: user" in message
    assert plugin_store.load_state().plugin("rapor") is not None


def test_panel_installed_kapat_ve_marketplaces_auto_update(state):
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    choose, _ = _script("tab:installed", "plugin:rapor@ekip", "disable:rapor@ekip")
    assert "kapalı" in plugin_panel.run_sync(state, choose)
    assert plugin_store.load_state().plugin("rapor").enabled is False

    choose, seen = _script("tab:markets", "market:ekip", "autoupdate:ekip")
    assert "auto-update açıldı" in plugin_panel.run_sync(state, choose)
    assert plugin_store.load_state().marketplace("ekip").auto_update is True
    choose, seen = _script("market:ekip", None)
    plugin_panel.run_sync(state, choose, start="markets")
    assert seen[-1] == "Pazar · ekip"


def test_panel_errors_sekmesi_ve_vazgecme(state):
    choose, seen = _script("tab:errors", None)
    assert plugin_panel.run_sync(state, choose) == plugin_panel.CLOSED
    assert "Yüklenemeyen eklenti yok" in seen[-1]


def test_start_key_paneli_acan_bicimler():
    assert plugin_panel.start_key("") == "discover"
    assert plugin_panel.start_key("manage") == "installed"
    assert plugin_panel.start_key("install rapor@ekip") == "install:rapor@ekip"
    assert plugin_panel.start_key("install ./yol") is None
    assert plugin_panel.start_key("list") is None


def test_alt_komut_tablosu_ve_takma_adlar(state):
    registry = build_registry(state.home, skills=lambda: state.capabilities)
    plugin = registry.get("plugin")
    assert registry.get("marketplace") is not None
    assert "Kullanım: /plugin" in plugin.handler(state, "help")
    assert "ekip" in registry.get("marketplace").handler(state, "list")
    assert "ekip" in plugin.handler(state, "market list")
    done = plugin.handler(state, "install rapor@ekip --scope user")
    assert "Kuruldu: rapor@ekip" in done, done
    assert "rapor" in plugin.handler(state, "ls --enabled")
    assert "Kurulu eklenti yok" in plugin.handler(state, "list --disabled")
    assert "Skills" in plugin.handler(state, "details rapor@ekip")
    assert "userConfig" in plugin.handler(state, "configure rapor@ekip")
    old = plugin.handler(state, "kapat rapor")
    assert "'/plugin kapat' kullanımdan kalktı; Claude Code adı: /plugin disable" in old


def test_install_dogrudan_kaynak_pazarda_yok_der(state, tmp_path):
    """#379: Claude `/plugin install <yol|URL|owner/repo>` hiçbir şey kurmaz."""
    folder = tmp_path / "pazar" / "plugins" / "rapor"
    message = repl_plugin.plugin_command(state, f"install {folder} --yes")
    assert "yapılandırılmış hiçbir pazarda yok" in message
    assert plugin_store.load_state().plugin("rapor") is None
    legacy = repl_plugin.plugin_command(state, f"kur {folder} --yes")
    assert "kullanımdan kalktı" in legacy and "Kuruldu: rapor" in legacy


def test_cli_install_dogrudan_kaynagi_reddeder_kur_eski_davranisi_surdurur(tmp_path):
    """#379: Claude `plugin install ./yol` → "not found in any configured marketplace" (1)."""
    from typer.testing import CliRunner

    from fusion_cli.cli.plugin_commands import app

    folder = tmp_path / "pazar" / "plugins" / "rapor"
    _market(tmp_path)
    runner = CliRunner()
    refused = runner.invoke(app, ["install", str(folder)])
    assert refused.exit_code == 1 and "hiçbir pazarda yok" in " ".join(refused.output.split())
    assert plugin_store.load_state().plugin("rapor") is None
    assert runner.invoke(app, ["kur", str(folder)]).exit_code == 0
