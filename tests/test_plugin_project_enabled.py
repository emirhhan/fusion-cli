"""Proje ayarında açılan ama burada kurulmamış eklenti (#376).

Claude Code (https://code.claude.com/docs/en/plugins/loading.md "Enabled in project settings but
not installed"): eklentinin tek `true`'su projenin `.claude/settings.json`'ındaysa ve pazar
girdisi göreli yollu ise kurulum kaydı gerekmeden pazarın kendisinden yüklenir; dış kaynaklıysa
yüklenmez, `Plugin "<ad>" is enabled in project settings but isn't installed here` bildirilir.
"""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.config import plugin_store, trust
from fusion_cli.tools import plugin_install


def _market(folder: Path, entries: list[dict[str, object]]) -> Path:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "ekip", "owner": {"name": "Ekip"}, "plugins": entries}),
        encoding="utf-8",
    )
    plugin = folder / "plugins" / "rapor"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "rapor"}), encoding="utf-8"
    )
    skill = plugin / "skills" / "ozet"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: ozet\ndescription: Özet\n---\nÖzet.\n", "utf-8")
    return folder


_RELATIVE = {"name": "rapor", "source": "./plugins/rapor"}
_EXTERNAL = {"name": "uzak", "source": {"source": "github", "repo": "acme/uzak"}}


def _project(tmp_path: Path, values: dict[str, bool], file: str = "settings.json") -> Path:
    project = tmp_path / "proje"
    path = project / ".claude" / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabledPlugins": values}), encoding="utf-8")
    return project


def _active(root: Path) -> list[str]:
    return [item.record.name for item in plugin_store.active_plugins(root=root)]


def test_proje_acinca_goreli_eklenti_kurulmadan_pazardan_yuklenir(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path / "pazar", [_RELATIVE])))
    project = _project(tmp_path, {"rapor@ekip": True})
    trust.trust_project(project)
    active = plugin_store.active_plugins(root=project)
    assert [item.record.name for item in active] == ["rapor"]
    assert Path(active[0].record.folder) == (tmp_path / "pazar" / "plugins" / "rapor").resolve()
    assert plugin_store.load_state().plugins == ()  # kurulum kaydı yazılmadı


def test_guvenilmeyen_proje_eklenti_acamaz_local_false_kapatir(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path / "pazar", [_RELATIVE])))
    project = _project(tmp_path, {"rapor@ekip": True})
    assert _active(project) == []
    trust.trust_project(project)
    local = project / ".claude" / "settings.local.json"
    local.write_text(json.dumps({"enabledPlugins": {"rapor@ekip": False}}), encoding="utf-8")
    trust.trust_project(project)
    assert _active(project) == []


def test_dis_kaynakli_eklenti_yuklenmez_ve_bildirilir(tmp_path, caplog):
    plugin_install.add_marketplace(str(_market(tmp_path / "pazar", [_RELATIVE, _EXTERNAL])))
    project = _project(tmp_path, {"uzak@ekip": True})
    trust.trust_project(project)
    assert _active(project) == []
    assert 'Plugin "uzak" is enabled in project settings but isn\'t installed here' in caplog.text


def test_kurulu_eklenti_iki_kez_yuklenmez(tmp_path):
    plugin_install.add_marketplace(str(_market(tmp_path / "pazar", [_RELATIVE])))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    project = _project(tmp_path, {"rapor@ekip": True})
    trust.trust_project(project)
    assert _active(project) == ["rapor"]


def _with_hook(tmp_path: Path) -> Path:
    plugin = tmp_path / "pazar" / "plugins" / "rapor"
    (plugin / "hooks").mkdir(parents=True, exist_ok=True)
    hook = {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/x.sh"}
    (plugin / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [hook]}]}}), encoding="utf-8"
    )
    return plugin


def test_proje_eklentisinin_kanca_koku_gercek_kaynak_klasoru(tmp_path, monkeypatch):
    """CLAUDE_PLUGIN_ROOT kayıt yazılmayan proje eklentisinde de kaynağı gösterir."""
    from fusion_cli.config.plugin_hooks import plugin_hooks

    plugin_install.add_marketplace(str(_market(tmp_path / "pazar", [_RELATIVE])))
    plugin = _with_hook(tmp_path)
    project = _project(tmp_path, {"rapor@ekip": True})
    trust.trust_project(project)
    monkeypatch.chdir(project)

    (command,), _skips = plugin_hooks(default_timeout_s=5.0)

    assert dict(command.env)["CLAUDE_PLUGIN_ROOT"] == str(plugin.resolve())


def test_proje_eklentisi_govdesinde_plugin_root_cozulur(tmp_path, monkeypatch):
    from fusion_cli.tools.plugin_capabilities import with_plugin_root

    plugin_install.add_marketplace(str(_market(tmp_path / "pazar", [_RELATIVE])))
    project = _project(tmp_path, {"rapor@ekip": True})
    trust.trust_project(project)
    monkeypatch.chdir(project)
    skill = tmp_path / "pazar" / "plugins" / "rapor" / "skills" / "ozet" / "SKILL.md"

    text = with_plugin_root("Kök=${CLAUDE_PLUGIN_ROOT}", skill)

    assert text == f"Kök={skill.parents[2].resolve()}"


def test_load_hooks_eklenti_kapsamini_verilen_kokten_cozer(tmp_path, monkeypatch):
    """#375: masaüstü oturumu `session.root` verir; süreç cwd'si başka dizin olabilir."""
    from fusion_cli.config.hooks import load_hooks

    plugin_install.add_marketplace(str(_market(tmp_path / "pazar", [_RELATIVE])))
    _with_hook(tmp_path)
    project = _project(tmp_path, {"rapor@ekip": True})
    trust.trust_project(project)
    elsewhere = tmp_path / "baska"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.delenv("FUSION_HOOKS", raising=False)

    hooks = load_hooks(project, default_timeout_s=5.0)

    assert [c.source for c in hooks.commands] == ["eklenti:rapor"]


def test_katalog_eklenti_kapsamini_verilen_kokten_cozer(tmp_path, monkeypatch):
    from fusion_cli.tools.capabilities import CapabilityRegistry

    plugin_install.add_marketplace(str(_market(tmp_path / "pazar", [_RELATIVE])))
    project = _project(tmp_path, {"rapor@ekip": True})
    trust.trust_project(project)
    elsewhere = tmp_path / "baska"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    names = [c.name for c in CapabilityRegistry(tmp_path / "ev", project).skills()]

    assert "rapor:ozet" in names
