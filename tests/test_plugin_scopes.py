"""Eklenti kapsamları, kaldırma verisi, pazar kaldırma ve /reload-plugins (#376, #383, #396, #408)."""

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
