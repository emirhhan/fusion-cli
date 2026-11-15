"""#419 boşlukları: eski 'değişmiş' kilidinin geçişi ve proje kapsamlı eklentinin MCP onayı.

Claude Code (https://code.claude.com/docs/en/plugins/loading.md "Trust check and component
limits for repository plugins"): kullanıcı kapsamlı eklentinin MCP sunucuları ek onaysız
yüklenir; proje kapsamlı (depodan gelen) eklentinin MCP sunucuları projenin `.mcp.json`'ıyla
aynı onaydan geçer. Fusion'da bu onay `fusion trust`'tır: tanım değişince yeniden onay gerekir.
"""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.config import plugin_store, trust
from fusion_cli.tools import plugin_install


def _plugin(folder: Path, name: str, *, mcp: bool = False) -> Path:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}), "utf-8")
    skill = folder / "skills" / "ozet"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8")
    if mcp:
        _mcp(folder, "--hizli")
    return folder


def _mcp(folder: Path, flag: str) -> None:
    (folder / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"veri": {"command": "sunucu", "args": [flag]}}}), "utf-8"
    )


def _old_version_state() -> None:
    path = plugin_store.state_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["surum"] = 1
    path.write_text(json.dumps(raw), encoding="utf-8")


def test_eski_surumde_degismis_kopya_gecisle_kapatilir_ve_bildirilir(tmp_path, caplog):
    plugin_install.install_plugin(str(_plugin(tmp_path / "a", "rapor")), approve=lambda _p: True)
    plugin_install.install_plugin(str(_plugin(tmp_path / "b", "temiz")), approve=lambda _p: True)
    copy = plugin_store.plugins_dir() / "rapor" / "skills" / "ozet" / "SKILL.md"
    copy.write_text("---\nname: ozet\ndescription: Ö\n---\nkötü\n", "utf-8")
    _old_version_state()

    active = [item.record.name for item in plugin_store.active_plugins()]

    assert active == ["temiz"]
    assert plugin_store.load_state().plugin("rapor").enabled is False
    assert "fusion plugin enable rapor" in caplog.text
    caplog.clear()
    assert [item.record.name for item in plugin_store.active_plugins()] == ["temiz"]
    assert "fusion plugin enable rapor" not in caplog.text  # geçiş bir kez


def test_guncel_surumde_kopya_degisse_de_yuklenir(tmp_path):
    plugin_install.install_plugin(str(_plugin(tmp_path / "a", "rapor")), approve=lambda _p: True)
    copy = plugin_store.plugins_dir() / "rapor" / "skills" / "ozet" / "SKILL.md"
    copy.write_text("---\nname: ozet\ndescription: Ö\n---\nyeni\n", "utf-8")

    assert [item.record.name for item in plugin_store.active_plugins()] == ["rapor"]


def _project_plugin(tmp_path: Path) -> tuple[Path, Path]:
    market = tmp_path / "pazar"
    plugin = _plugin(market / "plugins" / "rapor", "rapor", mcp=True)
    (market / ".claude-plugin").mkdir(parents=True)
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "ekip",
                "owner": {"name": "E"},
                "plugins": [{"name": "rapor", "source": "./plugins/rapor"}],
            }
        ),
        "utf-8",
    )
    plugin_install.add_marketplace(str(market))
    project = tmp_path / "proje"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"rapor@ekip": True}}), "utf-8"
    )
    return project, plugin


def _servers(project: Path) -> list[str]:
    return [server.name for server in plugin_store.plugin_mcp_servers(root=project)]


def test_proje_kapsamli_eklenti_mcp_tanimi_degisince_yeniden_onay_ister(tmp_path, caplog):
    project, plugin = _project_plugin(tmp_path)
    trust.trust_project(project)
    (name,) = _servers(project)

    _mcp(plugin, "--kotu")
    assert _servers(project) == []
    assert "fusion trust" in caplog.text

    trust.trust_project(project)
    assert _servers(project) == [name]


def test_kullanici_kapsamli_eklenti_mcp_onaysiz_yuklenir(tmp_path):
    plugin = _plugin(tmp_path / "a", "rapor", mcp=True)
    plugin_install.install_plugin(str(plugin), approve=lambda _p: True)
    _mcp(plugin_store.plugins_dir() / "rapor", "--yeni")

    assert len(plugin_store.plugin_mcp_servers()) == 1
