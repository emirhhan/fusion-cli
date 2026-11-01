"""Eklenti `dependencies`: kurulumda kendiliğinden kur/aç, `prune` ile buda (#389, #380, #397)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store
from fusion_cli.tools import plugin_install

runner = CliRunner()


def _plugin(folder: Path, name: str, deps: list[object] | None = None) -> None:
    (folder / ".claude-plugin").mkdir(parents=True)
    manifest: dict[str, object] = {"name": name, "version": "1.0.0"}
    if deps:
        manifest["dependencies"] = deps
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), "utf-8")
    (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: A\n---\nA\n", "utf-8")


def _market(root: Path, name: str, plugins: dict[str, list[object]], **extra: object) -> Path:
    for plugin, deps in plugins.items():
        _plugin(root / "plugins" / plugin, plugin, deps)
    (root / ".claude-plugin").mkdir(parents=True)
    entries = [{"name": p, "source": f"./plugins/{p}"} for p in plugins]
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": name, "owner": {"name": "E"}, "plugins": entries, **extra}), "utf-8"
    )
    return root


def test_bagimlilik_kendiliginden_kurulur_ve_prune_ile_budanir(tmp_path):
    market = _market(
        tmp_path / "pazar",
        "ekip",
        {"rapor": ["yardimci", {"name": "ortak"}], "yardimci": [], "ortak": []},
    )
    plugin_install.add_marketplace(str(market))

    done = runner.invoke(app, ["install", "rapor@ekip"])

    assert done.exit_code == 0, done.output
    assert "Bağımlılık kuruldu: yardimci@ekip" in done.output
    state = plugin_store.load_state()
    assert state.plugin("yardimci").dependency is True
    assert state.plugin("ortak").enabled is True
    assert state.plugin("rapor").dependency is False

    kept = runner.invoke(app, ["prune", "--dry-run"])
    assert "Nothing to prune" in kept.output
    runner.invoke(app, ["uninstall", "rapor@ekip"])
    dry = runner.invoke(app, ["prune", "--dry-run"])
    assert "ortak, yardimci" in dry.output and "dry run" in dry.output
    assert plugin_store.load_state().plugin("ortak") is not None
    pruned = runner.invoke(app, ["autoremove", "-y"])
    assert "ortak, yardimci" in pruned.output
    assert plugin_store.load_state().plugins == ()


def test_kapali_bagimlilik_acilir_ve_elle_kurulan_budanmaz(tmp_path):
    market = _market(tmp_path / "pazar", "ekip", {"rapor": ["yardimci"], "yardimci": []})
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin("yardimci@ekip", approve=lambda _p: True)
    plugin_install.set_plugin_enabled("yardimci", False)

    done = runner.invoke(app, ["install", "rapor@ekip"])

    assert "Bağımlılık açıldı: yardimci@ekip" in done.output
    assert plugin_store.load_state().plugin("yardimci").enabled is True
    runner.invoke(app, ["uninstall", "rapor@ekip", "--prune"])
    assert plugin_store.load_state().plugin("yardimci") is not None  # elle kurulmuştu


def test_baska_pazardaki_bagimlilik_izin_listesi_ister(tmp_path):
    other = _market(tmp_path / "diger", "diger", {"ortak": []})
    plugin_install.add_marketplace(str(other))
    closed = _market(tmp_path / "pazar", "ekip", {"rapor": ["ortak@diger"]})
    plugin_install.add_marketplace(str(closed))

    refused = runner.invoke(app, ["install", "rapor@ekip"])

    flat = " ".join(refused.output.split())
    assert refused.exit_code == 0 and "allowCrossMarketplaceDependenciesOn" in flat
    assert plugin_store.load_state().plugin("ortak") is None
    runner.invoke(app, ["uninstall", "rapor@ekip"])
    runner.invoke(app, ["marketplace", "remove", "ekip"])
    opened = _market(
        tmp_path / "pazar2",
        "ekip",
        {"rapor": ["ortak@diger"]},
        allowCrossMarketplaceDependenciesOn=["diger"],
    )
    plugin_install.add_marketplace(str(opened))
    allowed = runner.invoke(app, ["install", "rapor@ekip"])
    assert "Bağımlılık kuruldu: ortak@diger" in allowed.output, allowed.output


def test_ayni_adli_bagimlilik_baska_pazarda_kuruluyken_prune_yalniz_kendininkini_budar(tmp_path):
    """#389/#391: budama ve kapanış ad@pazar kimliğiyle; çıplak ad belirsizliği hata vermez."""
    other = _market(tmp_path / "diger", "diger", {"yardimci": []})
    market = _market(tmp_path / "pazar", "ekip", {"rapor": ["yardimci"], "yardimci": []})
    plugin_install.add_marketplace(str(other))
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin("yardimci@diger", approve=lambda _p: True)
    done = runner.invoke(app, ["install", "rapor@ekip"])
    assert done.exit_code == 0, done.output
    assert plugin_store.load_state().plugin("yardimci@ekip").dependency is True

    kept = runner.invoke(app, ["prune", "--dry-run"])
    assert "Nothing to prune" in kept.output, kept.output
    runner.invoke(app, ["uninstall", "rapor@ekip"])
    pruned = runner.invoke(app, ["prune", "-y"])

    assert pruned.exit_code == 0, pruned.output
    left = [plugin_store.plugin_id(r) for r in plugin_store.load_state().plugins]
    assert left == ["yardimci@diger"]
