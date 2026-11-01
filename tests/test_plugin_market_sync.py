"""Pazar `renames` ve `forceRemoveDeletedPlugins` (Claude host-marketplace, #397)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store
from fusion_cli.tools import plugin_install
from fusion_cli.tools.plugin_market_sync import resolve_rename


def _market(tmp_path: Path, plugins: list[dict[str, object]], **extra: object) -> Path:
    market = tmp_path / "pazar"
    for name in ("rapor", "cizim"):
        folder = market / "plugins" / name
        (folder / "skills" / "ozet").mkdir(parents=True, exist_ok=True)
        (folder / "skills" / "ozet" / "SKILL.md").write_text(
            "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
        )
    (market / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    data = {"name": "ekip", "owner": {"name": "E"}, "plugins": plugins, **extra}
    (market / ".claude-plugin" / "marketplace.json").write_text(json.dumps(data), "utf-8")
    return market


def test_renames_zinciri_en_eski_addan_izlenir():
    renames = {"a": "b", "b": "c", "x": "", "dongu": "dongu2", "dongu2": "dongu"}
    assert resolve_rename("a", renames, {"c"}) == "c"
    assert resolve_rename("x", renames, {"c"}) == ""
    assert resolve_rename("yok", renames, {"c"}) is None
    assert resolve_rename("dongu", renames, {"c"}) is None


def test_yeniden_adlandirilan_eklenti_yeni_adla_surer(tmp_path):
    entry = {"name": "rapor", "source": "./plugins/rapor"}
    plugin_install.add_marketplace(str(_market(tmp_path, [entry])))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    renamed = {"name": "rapor-yeni", "source": "./plugins/rapor"}
    _market(tmp_path, [renamed], renames={"rapor": "rapor-yeni"})

    out = CliRunner().invoke(app, ["marketplace", "update", "ekip"])

    assert out.exit_code == 0, out.output
    assert 'rapor: Renamed to "rapor-yeni" in the "ekip" marketplace' in out.output
    record = plugin_store.load_state().plugin("rapor")
    assert record is not None and record.source == "rapor-yeni@ekip"


def test_force_remove_silinen_girdinin_kurulumunu_kaldirir(tmp_path):
    entries = [
        {"name": "rapor", "source": "./plugins/rapor"},
        {"name": "cizim", "source": "./plugins/cizim"},
    ]
    plugin_install.add_marketplace(str(_market(tmp_path, entries)))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    plugin_install.install_plugin("cizim@ekip", approve=lambda _p: True)
    _market(tmp_path, entries[1:])

    kept = CliRunner().invoke(app, ["marketplace", "update", "ekip"])
    assert kept.exit_code == 0 and plugin_store.load_state().plugin("rapor") is not None

    _market(tmp_path, entries[1:], forceRemoveDeletedPlugins=True)
    out = CliRunner().invoke(app, ["marketplace", "update", "ekip"])

    assert '"rapor": Removed from marketplace' in out.output
    assert plugin_store.load_state().plugin("rapor") is None
    assert plugin_store.load_state().plugin("cizim") is not None


def test_oturum_basinda_esleme_ve_yerinde_klasor_yeni_girdiye_tasinir(tmp_path):
    """#397: Claude renames'i her oturum başında uygular; yerinde eklentinin yolu da taşınır."""
    from fusion_cli.tools.plugin_market_sync import sync_all

    entry = {"name": "rapor", "source": "./plugins/rapor"}
    market = _market(tmp_path, [entry])
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    (market / "plugins" / "rapor").rename(market / "plugins" / "rapor-yeni")
    renamed = {"name": "rapor-yeni", "source": "./plugins/rapor-yeni"}
    _market(tmp_path, [renamed], renames={"rapor": "rapor-yeni"})

    notes = sync_all()

    assert notes == ('rapor: Renamed to "rapor-yeni" in the "ekip" marketplace',)
    record = plugin_store.load_state().plugin("rapor")
    assert record.source == "rapor-yeni@ekip"
    assert record.folder == str((market / "plugins" / "rapor-yeni").resolve())
    assert sync_all() == ()


def test_repl_marketplace_update_esleme_bildirimlerini_gosterir(tmp_path):
    from fusion_cli.cli.repl.plugin_command import plugin_command
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.config.loader import load_config
    from fusion_cli.memory.factory import null_memory

    entry = {"name": "rapor", "source": "./plugins/rapor"}
    plugin_install.add_marketplace(str(_market(tmp_path, [entry])))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    _market(tmp_path, [{"name": "cizim", "source": "./plugins/cizim"}], renames={"rapor": None})
    config = tmp_path / "c.yaml"
    config.write_text("runtime:\n  max_tokens: 4096\n", "utf-8")
    state = ReplState(
        config=load_config(config), memory=null_memory(), root=tmp_path, home=tmp_path
    )
    out = plugin_command(state, "marketplace update ekip")
    assert 'rapor: Removed from the "ekip" marketplace' in out
