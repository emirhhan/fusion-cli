"""Eklenti kapsamları, kaldırma verisi, pazar kaldırma, /reload-plugins, validate.

#376, #383, #396, #408, #412.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store, trust
from fusion_cli.config.plugin_data import plugin_data_dir
from fusion_cli.core.plugins import PluginError
from fusion_cli.tools import plugin_install

runner = CliRunner()


def _plugin(folder: Path, name: str = "rapor") -> Path:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": name, "version": "1.0.0"}), encoding="utf-8"
    )
    skill = folder / "skills" / "ozet"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Özetle\n---\nÖzetle.\n", encoding="utf-8"
    )
    return folder


def _yes(_preview: object) -> bool:
    return True


def _install(tmp_path: Path, name: str = "rapor") -> None:
    plugin_install.install_plugin(str(_plugin(tmp_path / f"kaynak-{name}", name)), approve=_yes)


def _settings(root: Path, name: str, values: dict[str, bool]) -> Path:
    path = root / ".claude" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabledPlugins": values}), encoding="utf-8")
    return path


def _active(root: Path) -> list[str]:
    return [item.record.name for item in plugin_store.active_plugins(root=root)]


# --- #376: enabledPlugins katmanları -------------------------------------------- #


def test_proje_false_her_zaman_uygulanir_true_yalniz_guvenilirse(tmp_path):
    _install(tmp_path)
    project = tmp_path / "proje"
    _settings(project, "settings.json", {"rapor": False})
    assert _active(project) == []

    plugin_install.set_plugin_enabled("rapor", False, scope="user", root=tmp_path / "bos")
    _settings(project, "settings.json", {"rapor": True})
    assert _active(project) == []  # güvenilmeyen dosya eklenti açamaz
    trust.trust_project(project)
    assert _active(project) == ["rapor"]


def test_local_projeyi_ezer_ve_kapsam_algilanir(tmp_path):
    _install(tmp_path)
    project = tmp_path / "proje"
    _settings(project, "settings.json", {"rapor": True})
    trust.trust_project(project)

    written = plugin_install.set_plugin_enabled("rapor", False, scope="local", root=project)
    assert written == "local"
    assert _active(project) == []
    local = json.loads((project / ".claude" / "settings.local.json").read_text("utf-8"))
    assert local["enabledPlugins"] == {"rapor": False}
    # Fusion'ın yazdığı güvenilir dosya güvenilir kalır: local `true` geri açar.
    assert plugin_install.set_plugin_enabled("rapor", True, root=project) == "local"
    assert _active(project) == ["rapor"]


def test_dusuk_oncelikli_kapsam_hata_verir_zaten_acik_hata(tmp_path):
    _install(tmp_path)
    project = tmp_path / "proje"
    _settings(project, "settings.json", {"rapor": False})
    with pytest.raises(PluginError, match="project kapsamında kurulu, user değil"):
        plugin_install.set_plugin_enabled("rapor", True, scope="user", root=project)
    with pytest.raises(PluginError, match="Geçersiz kapsam"):
        plugin_install.set_plugin_enabled("rapor", True, scope="managed", root=project)
    with pytest.raises(PluginError, match='"rapor" zaten açık'):
        plugin_install.set_plugin_enabled("rapor", True, root=tmp_path / "bos")


def test_proje_yazimi_mevcut_anahtarlari_korur(tmp_path):
    _install(tmp_path)
    project = tmp_path / "proje"
    path = project / ".claude" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"permissions": {"allow": ["Read"]}}), encoding="utf-8")

    plugin_install.set_plugin_enabled("rapor", False, scope="project", root=project)

    saved = json.loads(path.read_text("utf-8"))
    assert saved == {"permissions": {"allow": ["Read"]}, "enabledPlugins": {"rapor": False}}
    assert not trust.is_project_settings_trusted(project)  # güvensiz dosya güvenilir olmadı


def test_cli_enable_disable_scope_ciktisi(tmp_path, monkeypatch):
    _install(tmp_path)
    project = tmp_path / "proje"
    project.mkdir()
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["disable", "rapor", "--scope", "local"])
    assert result.exit_code == 0, result.output
    assert "Eklenti kapatıldı: rapor (kapsam: local)" in result.output
    again = runner.invoke(app, ["disable", "rapor"])
    assert again.exit_code == 1 and "zaten kapalı" in again.output
    assert runner.invoke(app, ["disable", "--all", "--scope", "user"]).exit_code == 1


# --- #408: kaldırma ve veri klasörü --------------------------------------------- #


def test_kaldirma_veriyi_siler_keep_data_korur(tmp_path):
    _install(tmp_path, "bir")
    _install(tmp_path, "iki")
    for name in ("bir", "iki"):
        (plugin_data_dir(name, create=True) / "durum.json").write_text("{}", encoding="utf-8")

    plugin_install.uninstall_plugin("bir")
    plugin_install.uninstall_plugin("iki", keep_data=True)

    assert not plugin_data_dir("bir").exists()
    assert (plugin_data_dir("iki") / "durum.json").is_file()
    assert plugin_store.load_state().plugins == ()


def test_cli_uninstall_kapsam_ve_mesaj(tmp_path):
    _install(tmp_path)
    wrong = runner.invoke(app, ["uninstall", "rapor", "--scope", "project"])
    assert wrong.exit_code == 1 and "project kapsamında kurulu değil" in wrong.output
    done = runner.invoke(app, ["uninstall", "rapor", "--keep-data"])
    assert done.exit_code == 0, done.output
    assert "Eklenti kaldırıldı: rapor (kapsam: user" in done.output
    assert "veri korundu" in done.output


# --- #396: pazar kaldırma ondan kurulan eklentileri kaldırır -------------------- #


def test_pazar_kaldirma_kurulu_eklentileri_de_kaldirir(tmp_path):
    market = tmp_path / "pazar"
    _plugin(market / "plugins" / "rapor")
    (market / ".claude-plugin").mkdir(parents=True)
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "ekip",
                "owner": {"name": "Ekip"},
                "plugins": [{"name": "rapor", "source": "./plugins/rapor"}],
            }
        ),
        encoding="utf-8",
    )
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin("rapor@ekip", approve=_yes)
    _install(tmp_path, "baska")

    result = runner.invoke(app, ["marketplace", "remove", "ekip"])

    assert result.exit_code == 0, result.output
    assert "Ayrıca bu pazardan 1 eklenti kaldırıldı:" in result.output
    assert [r.name for r in plugin_store.load_state().plugins] == ["baska"]


# --- #383: /reload-plugins ------------------------------------------------------ #


def test_reload_plugins_ozet_satiri(tmp_path):
    from types import SimpleNamespace

    from fusion_cli.cli.repl.reload_plugins import reload_plugins_command
    from fusion_cli.config.loader import load_config
    from fusion_cli.tools.capabilities import CapabilityRegistry

    _install(tmp_path)
    config_file = tmp_path / "config.yaml"
    config_file.write_text("{}\n", encoding="utf-8")
    state = SimpleNamespace(
        config=load_config(config_file),
        capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path / "proje"),
    )
    text = reload_plugins_command(state, "")  # type: ignore[arg-type]
    assert text.startswith("Yeniden yüklendi: 1 eklenti · 1 beceri ·")
    assert "0 eklenti MCP sunucusu" in text
    assert reload_plugins_command(state, "--bilinmeyen").startswith("Kullanım")  # type: ignore[arg-type]


# --- #412: plugin validate ------------------------------------------------------ #


def test_validate_eklenti_uyari_strict_ve_json(tmp_path):
    root = _plugin(tmp_path / "p", "Rapor_Araci")
    (root / "CLAUDE.md").write_text("x", encoding="utf-8")

    loose = runner.invoke(app, ["validate", str(root)])
    assert loose.exit_code == 0, loose.output
    assert "Doğrulama uyarılarla başarılı" in loose.output
    assert "description alanı yok" in loose.output and "CLAUDE.md" in loose.output

    strict = runner.invoke(app, ["validate", str(root), "--strict", "--json"])
    assert strict.exit_code == 1
    report = json.loads(strict.output.strip().splitlines()[-1])
    assert report["success"] is False and report["strict"] is True
    assert report["target"].endswith("plugin.json") and report["advice"] == []
    assert any("author" in w for w in report["manifest"]["warnings"])


def test_validate_pazar_bildirimini_dogrular_ve_hata_1_doner(tmp_path):
    market = tmp_path / "pazar"
    (market / ".claude-plugin").mkdir(parents=True)
    file = market / ".claude-plugin" / "marketplace.json"
    file.write_text(json.dumps({"name": "ekip", "plugins": []}), encoding="utf-8")

    bad = runner.invoke(app, ["validate", str(market)])
    assert bad.exit_code == 1
    assert "Pazar bildirimi doğrulanıyor" in bad.output and "Doğrulama başarısız" in bad.output

    file.write_text(json.dumps({"name": "ekip", "owner": {"name": "E"}, "plugins": []}), "utf-8")
    good = runner.invoke(app, ["validate", str(file)])
    assert good.exit_code == 0 and "✔ Doğrulama başarılı" in good.output


def test_validate_olmayan_yol_cikis_2_stdout_bos(tmp_path):
    result = runner.invoke(app, ["validate", str(tmp_path / "yok")])
    assert result.exit_code == 2
    assert "beklenmeyen hata" in result.output


# --- #416: mods ve workflows açıkça desteklenmiyor ------------------------------ #


def test_workflows_ve_mods_desteklenmiyor_diye_raporlanir(tmp_path):
    root = _plugin(tmp_path / "p")
    (root / "workflows").mkdir()
    (root / "workflows" / "yayinla.js").write_text("export default 1", encoding="utf-8")
    (root / "hooks").mkdir()
    (root / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {}, "modules": ["./mod.js"]}), encoding="utf-8"
    )
    result = runner.invoke(app, ["validate", str(root)])
    assert "workflows/ (Claude iş akışları) Fusion'da desteklenmiyor" in result.output
    assert "'modules' (Claude mod'ları) Fusion'da desteklenmiyor" in result.output


def test_validate_girdi_surumu_plugin_json_ile_celisirse_uyarir(tmp_path):
    """Claude: `Entry declares version "x" but <yol>/plugin.json says "y"…` uyarısı (#398)."""
    market = tmp_path / "pazar"
    (market / ".claude-plugin").mkdir(parents=True)
    _plugin(market / "plugins" / "rapor")  # plugin.json version 1.0.0
    entry = {"name": "rapor", "source": "./plugins/rapor", "version": "2.0.0"}
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {"name": "ekip", "owner": {"name": "E"}, "description": "d", "plugins": [entry]}
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["validate", str(market)])
    assert result.exit_code == 0, result.output
    assert 'Entry declares version "2.0.0" but' in result.output
    assert 'plugin.json says "1.0.0". At install time, plugin.json wins' in result.output


def _two_plugin_market(tmp_path):
    market = tmp_path / "pazar"
    _plugin(market / "plugins" / "rapor")
    _plugin(market / "plugins" / "ozet", "ozet")
    (market / ".claude-plugin").mkdir(parents=True)
    entries = [
        {"name": "rapor", "source": "./plugins/rapor"},
        {"name": "ozet", "source": "./plugins/ozet"},
    ]
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "ekip", "owner": {"name": "Ekip"}, "plugins": entries}),
        encoding="utf-8",
    )
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin("rapor@ekip", approve=_yes)
    plugin_install.install_plugin("ozet@ekip", approve=_yes)


def test_pazar_kaldirmada_biri_basarisiz_olursa_pazar_kalir_ve_yeniden_denenebilir(
    tmp_path, monkeypatch
):
    from fusion_cli.core.plugins import PluginError

    _two_plugin_market(tmp_path)
    real = plugin_install.uninstall_plugin

    def flaky(name, **kwargs):
        if name.startswith("rapor"):
            raise PluginError("kilitli")
        return real(name, **kwargs)

    monkeypatch.setattr(plugin_install, "uninstall_plugin", flaky)
    with pytest.raises(PluginError, match="rapor"):
        plugin_install.remove_marketplace("ekip")
    state = plugin_store.load_state()
    assert state.marketplace("ekip") is not None  # yeniden denenebilir
    assert [r.name for r in state.plugins] == ["rapor"]  # öteki yine kaldırıldı

    monkeypatch.setattr(plugin_install, "uninstall_plugin", real)
    assert plugin_install.remove_marketplace("ekip") == ("rapor",)
    assert plugin_store.load_state().marketplace("ekip") is None
