"""plugin list --json/--available, details, prune, install --scope/--marketplace/--json.

#376, #379, #380, #381, #415.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store, trust
from fusion_cli.tools import plugin_install

runner = CliRunner()


def _plugin(folder: Path, name: str) -> Path:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": name, "version": "1.0.0", "description": "Rapor yazar"}),
        encoding="utf-8",
    )
    skill = folder / "skills" / "ozet"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Özetle\n---\nÖzetle.\n", encoding="utf-8"
    )
    return folder


def _market(tmp_path: Path, names: tuple[str, ...] = ("rapor", "cizim")) -> Path:
    market = tmp_path / "pazar"
    for name in names:
        _plugin(market / "plugins" / name, name)
    (market / ".claude-plugin").mkdir(parents=True)
    entries = [
        {"name": n, "source": f"./plugins/{n}", "description": f"{n} eklentisi"} for n in names
    ]
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "ekip", "owner": {"name": "Ekip"}, "plugins": entries}),
        encoding="utf-8",
    )
    return market


def _yes(_preview: object) -> bool:
    return True


def test_list_json_kurulu_dizi_ve_available_nesnesi(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path)))
    plugin_install.install_plugin("rapor@ekip", approve=_yes)

    flat = json.loads(runner.invoke(app, ["list", "--json"]).output)
    assert [row["id"] for row in flat] == ["rapor@ekip"]
    row = flat[0]
    assert row["version"] == "1.0.0" and row["scope"] == "user" and row["enabled"] is True
    assert row["installPath"].endswith("rapor") and row["installedAt"].endswith("Z")

    both = json.loads(runner.invoke(app, ["list", "--json", "--available"]).output)
    assert [r["id"] for r in both["installed"]] == ["rapor@ekip"]
    assert both["available"] == [
        {
            "pluginId": "cizim@ekip",
            "name": "cizim",
            "marketplaceName": "ekip",
            "source": "./plugins/cizim",
            "description": "cizim eklentisi",
        }
    ]


def test_list_insan_ciktisi_ve_bos_mesaj(tmp_path):
    assert "Kurulu eklenti yok. Eklenti kurmak için `fusion plugin install`" in (
        runner.invoke(app, ["list"]).output
    )
    plugin_install.add_marketplace(str(_market(tmp_path)))
    plugin_install.install_plugin("rapor@ekip", approve=_yes)
    output = runner.invoke(app, ["list"]).output
    assert "Kurulu eklentiler:" in output and "rapor@ekip 1.0.0" in output


def test_details_envanter_ve_bulunamadi(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path)))
    plugin_install.install_plugin("rapor@ekip", approve=_yes)

    shown = runner.invoke(app, ["details", "rapor"])
    assert shown.exit_code == 0, shown.output
    for part in ("rapor@ekip 1.0.0", "Component inventory:", "Skills: 1", "Projected token cost"):
        assert part in shown.output
    missing = runner.invoke(app, ["details", "yok"])
    assert missing.exit_code == 1
    assert 'Eklenti "yok" bulunamadı' in missing.output


def test_prune_budanacak_yok_ve_autoremove():
    assert "Nothing to prune" in runner.invoke(app, ["prune", "-y"]).output
    dry = runner.invoke(app, ["autoremove", "--dry-run"]).output
    assert "(dry run — nothing removed)" in dry


def test_install_marketplace_pazari_ekleyip_kurar_json(tmp_path):
    market = _market(tmp_path)
    result = runner.invoke(app, ["install", "rapor", "--marketplace", str(market), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["command"] == "install" and payload["outcome"] == "ok"
    assert payload["pluginId"] == "rapor@ekip" and payload["scope"] == "user"
    again = runner.invoke(app, ["install", "cizim", "--marketplace", str(market)])
    assert again.exit_code == 0, again.output
    assert len(plugin_store.load_state().marketplaces) == 1  # aynı kaynak yeniden eklenmez
    bad = runner.invoke(app, ["install", "rapor@ekip", "--marketplace", str(market), "--json"])
    assert bad.exit_code == 1
    assert json.loads(bad.output.strip().splitlines()[-1])["outcome"] == "failed"


def test_install_scope_project_yalniz_projede_acar(tmp_path, monkeypatch):
    plugin_install.add_marketplace(str(_market(tmp_path)))
    project = tmp_path / "proje"
    project.mkdir()
    monkeypatch.chdir(project)
    trust.trust_project(project)

    result = runner.invoke(app, ["install", "rapor@ekip", "--scope", "project"])

    assert result.exit_code == 0, result.output
    assert "kapsam: project" in result.output
    settings = json.loads((project / ".claude" / "settings.json").read_text("utf-8"))
    assert settings["enabledPlugins"] == {"rapor@ekip": True}
    assert plugin_store.load_state().plugin("rapor").enabled is False  # user kapsamında kapalı
    # Güvenilir proje dosyasına Fusion'ın kendi yazımı güveni korur (write_enabled).
    assert [i.record.name for i in plugin_store.active_plugins(root=project)] == ["rapor"]
    again = runner.invoke(app, ["install", "rapor@ekip", "--scope", "project"])
    assert again.exit_code == 0
    assert "already installed (scope: project)" in again.output


def test_enable_disable_uninstall_json(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path)))
    plugin_install.install_plugin("rapor@ekip", approve=_yes)

    off = runner.invoke(app, ["disable", "rapor@ekip", "--json"])
    assert json.loads(off.output.splitlines()[-1])["outcome"] == "ok"
    twice = runner.invoke(app, ["disable", "rapor@ekip", "--json"])
    assert twice.exit_code == 1
    assert json.loads(twice.output.splitlines()[-1])["command"] == "disable"
    gone = runner.invoke(app, ["uninstall", "rapor@ekip", "--json"])
    assert json.loads(gone.output.splitlines()[-1])["command"] == "uninstall"


def test_dogrudan_kaynak_kurulumu_uyari_verir_kesfet_kalkti(tmp_path, caplog):
    source = _plugin(tmp_path / "kaynak", "tek")
    result = runner.invoke(app, ["install", str(source), "-y"])
    assert result.exit_code == 0, result.output
    assert "Doğrudan kaynaktan kurulum kullanımdan kalktı" in caplog.text
    discover = runner.invoke(app, ["discover"])
    assert "kullanımdan kalktı" in discover.output


# --- #403: yerel pazarın göreli eklentileri yerinde yüklenir --------------------- #


def test_yerel_pazar_eklentisi_yerinde_yuklenir_duzenleme_gorunur(tmp_path):
    market = _market(tmp_path)
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin("rapor@ekip", approve=_yes)
    source = market / "plugins" / "rapor"

    assert not (plugin_store.plugins_dir() / "rapor").exists()  # kopyalanmadı
    record = plugin_store.load_state().plugin("rapor")
    assert record.folder == str(source.resolve())
    extra = source / "skills" / "yeni"
    extra.mkdir()
    (extra / "SKILL.md").write_text("---\nname: yeni\ndescription: Yeni\n---\nY\n", "utf-8")
    (item,) = plugin_store.active_plugins()
    assert item.status == plugin_store.STATUS_ACTIVE  # düzenleme "değişmiş" kilidi DEĞİL
    assert len(item.layout.skills) == 2
    row = json.loads(runner.invoke(app, ["list", "--json"]).output)[0]
    assert row["readFromFolder"] == str(source.resolve())

    plugin_install.uninstall_plugin("rapor")
    assert source.is_dir()  # kaynak klasör çöpe taşınmaz


def test_marketplace_json_ve_turkce_ad_uyarisi(tmp_path):
    market = _market(tmp_path)
    added = runner.invoke(app, ["marketplace", "add", str(market), "--json"])
    payload = json.loads(added.output.strip().splitlines()[-1])
    assert payload == {
        "command": "marketplace-add",
        "outcome": "ok",
        "message": payload["message"],
        "marketplace": "ekip",
    }
    old = runner.invoke(app, ["listele"])
    assert "'listele' kullanımdan kalktı; Claude Code adı: fusion plugin list" in old.output
    gone = runner.invoke(app, ["pazar", "kaldir", "ekip", "--json"])
    assert "fusion plugin marketplace remove" in gone.output
    assert json.loads(gone.output.strip().splitlines()[-1])["command"] == "marketplace-remove"
    missing = runner.invoke(app, ["marketplace", "remove", "ekip", "--json"])
    assert missing.exit_code == 1


def test_fusion_plugins_ortam_degiskeni_uyarir(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(plugin_store, "_ENV_WARNED", [])
    monkeypatch.setenv("FUSION_PLUGINS", "off")
    assert plugin_store.plugins_disabled_by_environment() is True
    plugin_store.plugins_disabled_by_environment()
    assert caplog.text.count("FUSION_PLUGINS kullanımdan kalktı") == 1


def test_validate_ayrilmis_ad_hata_verir(tmp_path):
    root = _plugin(tmp_path / "x", "claude-araclar")
    result = runner.invoke(app, ["validate", str(root)])
    assert result.exit_code == 1, result.output
    assert "ayrılmış" in result.output


def test_girdi_adi_bildirim_adindan_farkli_ise_kimlik_ve_guncelleme_kaynagi(tmp_path):
    from fusion_cli.tools.plugin_update import update_source

    market = tmp_path / "pazar"
    _plugin(market / "plugins" / "rapor", "rapor")
    (market / ".claude-plugin").mkdir(parents=True)
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "ekip",
                "owner": {"name": "E"},
                "plugins": [{"name": "rapor-eklentisi", "source": "./plugins/rapor"}],
            }
        ),
        "utf-8",
    )
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin("rapor-eklentisi@ekip", approve=_yes)

    record = plugin_store.load_state().plugin("rapor")
    assert update_source(record) == "rapor-eklentisi@ekip"
    result = runner.invoke(app, ["disable", "rapor-eklentisi@ekip"])
    assert result.exit_code == 0, result.output
    assert plugin_store.load_state().plugin("rapor").enabled is False


def test_uninstall_prune_bagimlilik_yok(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path)))
    plugin_install.install_plugin("rapor@ekip", approve=_yes)
    result = runner.invoke(app, ["uninstall", "rapor", "--prune"])
    assert result.exit_code == 0, result.output
    assert "Nothing to prune" in result.output


def test_uninstall_scope_project_yalniz_o_kapsamdan_kaldirir(tmp_path, monkeypatch):
    plugin_install.add_marketplace(str(_market(tmp_path)))
    project = tmp_path / "proje"
    project.mkdir()
    monkeypatch.chdir(project)
    trust.trust_project(project)
    assert runner.invoke(app, ["install", "rapor@ekip", "--scope", "project"]).exit_code == 0

    done = runner.invoke(app, ["uninstall", "rapor@ekip", "--scope", "project", "--json"])

    assert done.exit_code == 0, done.output
    assert "Eklenti kaldırıldı: rapor (kapsam: project" in done.output
    assert json.loads(done.output.strip().splitlines()[-1])["scope"] == "project"
    settings = json.loads((project / ".claude" / "settings.json").read_text("utf-8"))
    assert settings["enabledPlugins"] == {}
    assert plugin_store.active_plugins(root=project) == ()
    again = runner.invoke(app, ["uninstall", "rapor@ekip", "--scope", "project"])
    assert again.exit_code == 1 and "project kapsamında kurulu değil" in again.output
