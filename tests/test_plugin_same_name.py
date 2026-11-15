"""Farklı pazarlardan aynı adlı eklentiler birlikte kurulur (Claude kimliği `ad@pazar`, #391)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store
from fusion_cli.config.plugin_store import PluginRecord, PluginState
from fusion_cli.core.plugins import PluginError
from fusion_cli.tools import plugin_install
from fusion_cli.tools.plugin_toggle import find_record


def _market(tmp_path: Path, market: str) -> Path:
    root = tmp_path / market
    folder = root / "plugins" / "rapor"
    (folder / "skills" / "ozet").mkdir(parents=True)
    (folder / "skills" / "ozet" / "SKILL.md").write_text(
        f"---\nname: ozet\ndescription: {market}\n---\nÖ\n", "utf-8"
    )
    (root / ".claude-plugin").mkdir()
    data = {
        "name": market,
        "owner": {"name": "E"},
        "plugins": [{"name": "rapor", "source": "./plugins/rapor"}],
    }
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(data), "utf-8")
    return root


def test_iki_pazardan_ayni_adli_eklenti_birlikte_kurulur(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path, "ekip")))
    plugin_install.add_marketplace(str(_market(tmp_path, "baska")))

    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    plugin_install.install_plugin("rapor@baska", approve=lambda _p: True)

    state = plugin_store.load_state()
    ids = sorted(plugin_store.plugin_id(r) for r in state.plugins)
    assert ids == ["rapor@baska", "rapor@ekip"]
    raw = json.loads(plugin_store.state_file().read_text("utf-8"))
    assert set(raw["eklentiler"]) == {"rapor", "rapor@baska"}
    assert raw["eklentiler"]["rapor@baska"]["ad"] == "rapor"
    with pytest.raises(PluginError, match="rapor@baska"):
        find_record(state, "rapor")


def test_ayni_pazardan_ikinci_kurulum_zaten_kurulu(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path, "ekip")))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)

    with pytest.raises(plugin_install.PluginAlreadyInstalledError):
        plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)


def test_ad_pazar_ile_kapatma_ve_kaldirma_yalniz_o_kurulumu_etkiler(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path, "ekip")))
    plugin_install.add_marketplace(str(_market(tmp_path, "baska")))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    plugin_install.install_plugin("rapor@baska", approve=lambda _p: True)
    runner = CliRunner()

    off = runner.invoke(app, ["disable", "rapor@baska"])
    assert off.exit_code == 0, off.output
    state = plugin_store.load_state()
    assert state.plugin("rapor@ekip").enabled is True
    assert state.plugin("rapor@baska").enabled is False

    out = runner.invoke(app, ["uninstall", "rapor@baska"])
    assert out.exit_code == 0, out.output
    left = plugin_store.load_state().plugins
    assert [plugin_store.plugin_id(r) for r in left] == ["rapor@ekip"]


def test_anahtarli_kayit_klasoru_ve_eski_kayit_geriye_uyumlu(tmp_path):
    record = PluginRecord(name="rapor", marketplace="baska", key="rapor@baska")
    assert plugin_store.plugin_folder(record, tmp_path) == tmp_path / "rapor@baska"
    plugin_store.save_state(PluginState((PluginRecord(name="eski"), record)), tmp_path)

    loaded = plugin_store.load_state(tmp_path)

    assert loaded.plugin("eski").store_key == "eski"
    assert loaded.plugin("rapor@baska") == record
    assert loaded.without_plugin("rapor@baska").plugin("eski") is not None
    assert plugin_store.same_name_key(loaded, "rapor", "ucuncu") == "rapor@ucuncu"
    assert plugin_store.same_name_key(loaded, "rapor", "baska") is None
    assert not plugin_store.valid_store_key("../x@y")
