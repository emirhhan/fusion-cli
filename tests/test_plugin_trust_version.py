"""Claude Code eklenti güven modeli, sürüm hesabı ve eski sürüm temizliği (#392, #393, #408, #419).

Belge: code.claude.com/docs/en/plugins/loading.md — kullanıcı kapsamlı eklentinin kanca ve MCP'si
ek onay istemeden yüklenir; karma kilidi yok; sürüm manifest → girdi → commit[:12] → `unknown`;
aynı sürümde `update` hiçbir şey değiştirmez; eski sürüm klasörü `.orphaned_at` ile 14 gün kalır.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app as plugin_app
from fusion_cli.config import plugin_store
from fusion_cli.tools import plugin_install, plugin_update, plugin_version


def _yes(preview: plugin_install.PluginPreview) -> bool:
    return True


def _plugin(folder: Path, name: str = "bicimci", *, version: str = "1.2.0", hooks: bool = False):
    (folder / ".claude-plugin").mkdir(parents=True)
    manifest: dict[str, object] = {"name": name, "description": "Biçimleyici"}
    if version:
        manifest["version"] = version
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    skill = folder / "skills" / "ozet"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: ozet\ndescription: x\n---\nÖzet.\n", "utf-8")
    if hooks:
        _add_hooks(folder)
    return folder


def _add_hooks(folder: Path) -> None:
    (folder / "hooks").mkdir(exist_ok=True)
    (folder / "hooks" / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "bicimle"}]}]}}),
        encoding="utf-8",
    )


# --- #392, #419: güven modeli ------------------------------------------------------ #


def test_kurulumdan_sonra_degisen_kopya_yuklenir_karma_kilidi_yok(tmp_path):
    plugin_install.install_plugin(str(_plugin(tmp_path / "k", hooks=True)), approve=_yes)
    skill = plugin_store.plugins_dir() / "bicimci" / "skills" / "ozet" / "SKILL.md"
    skill.write_text("---\nname: ozet\ndescription: y\n---\nDüzenlendi.\n", encoding="utf-8")

    (item,) = plugin_store.installed_plugins()
    assert item.status == plugin_store.STATUS_ACTIVE
    assert [i.record.name for i in plugin_store.active_plugins()] == ["bicimci"]
    assert plugin_store.plugin_hook_blocks()


def test_sonradan_kanca_eklenen_eklentinin_kancasi_ek_onaysiz_yuklenir(tmp_path):
    plugin_install.install_plugin(str(_plugin(tmp_path / "k")), approve=_yes)
    record = plugin_store.load_state().plugin("bicimci")
    assert record is not None and record.exec_approved is False
    _add_hooks(plugin_store.plugins_dir() / "bicimci")

    (block,) = plugin_store.plugin_hook_blocks()
    assert block[0] == "eklenti:bicimci"


def test_cli_install_kanca_iceren_eklentide_yes_sormaz(tmp_path):
    source = _plugin(tmp_path / "k", hooks=True)

    result = CliRunner().invoke(plugin_app, ["install", str(source)])

    assert result.exit_code == 0, result.output
    assert plugin_store.load_state().plugin("bicimci") is not None


def test_trust_kullanimdan_kalkti_uyarisi_verir(tmp_path):
    plugin_install.install_plugin(str(_plugin(tmp_path / "k")), approve=_yes)

    result = CliRunner().invoke(plugin_app, ["trust", "bicimci", "--yes"])

    assert result.exit_code == 0, result.output
    assert "kullanımdan kalktı" in result.output


# --- #393: sürüm hesabı ve güncelleme ---------------------------------------------- #


def test_surum_sirasi_manifest_girdi_commit_unknown():
    assert plugin_version.resolve_version("1.0.0", "2.0.0", "abc" * 14) == "1.0.0"
    assert plugin_version.resolve_version("", "2.0.0", "abc" * 14) == "2.0.0"
    assert plugin_version.resolve_version("", "", "0123456789abcdef") == "0123456789ab"
    assert plugin_version.resolve_version("", "", "") == "unknown"
    subdir = plugin_version.resolve_version("", "", "0123456789abcdef", subdir="eklentiler/a")
    assert subdir.startswith("0123456789ab-") and subdir != "0123456789ab"


def test_ayni_surumde_update_icerigi_degistirmez(tmp_path):
    source = _plugin(tmp_path / "k")
    plugin_install.install_plugin(str(source), approve=_yes)
    (source / "skills" / "ozet" / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: x\n---\nYeni commit.\n", encoding="utf-8"
    )

    result = plugin_update.update_plugin("bicimci", approve=_yes)

    assert result.changed is False
    installed = plugin_store.plugins_dir() / "bicimci" / "skills" / "ozet" / "SKILL.md"
    assert "Özet." in installed.read_text(encoding="utf-8")
    out = CliRunner().invoke(plugin_app, ["update", "bicimci"])
    assert "bicimci is already at the latest version (1.2.0)." in out.output


def test_surumsuz_yerel_eklenti_unknown_kalir(tmp_path):
    plugin_install.install_plugin(str(_plugin(tmp_path / "k", version="")), approve=_yes)

    record = plugin_store.load_state().plugin("bicimci")
    assert record is not None and record.version == "unknown"


def test_ad_at_pazar_guncellemesi_once_git_pazarini_yeniler(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        plugin_update, "update_marketplace", lambda name, base=None: calls.append(name)
    )
    market = plugin_store.MarketplaceRecord("ekip", "https://example.com/ekip.git", "git", "/yok")
    local = plugin_store.MarketplaceRecord("yerel", "/yerel", "yerel", "/yerel")

    plugin_update.refresh_marketplace_for("eklenti@ekip", (market, local))
    plugin_update.refresh_marketplace_for("eklenti@yerel", (market, local))
    plugin_update.refresh_marketplace_for("/bir/klasor", (market, local))

    assert calls == ["ekip"]


# --- #408: kaldırma ve eski sürüm temizliği ---------------------------------------- #


def test_uninstall_kopyayi_orphaned_at_ile_birakir_14_gun_sonra_temizlenir(tmp_path):
    plugin_install.install_plugin(str(_plugin(tmp_path / "k")), approve=_yes)
    root = plugin_store.plugins_dir()

    plugin_install.uninstall_plugin("bicimci")

    assert not (root / "bicimci").exists()
    (orphan,) = plugin_version.orphaned_dirs(root)
    assert (orphan / plugin_version.ORPHAN_MARKER).is_file()
    plugin_install.install_plugin(str(tmp_path / "k"), approve=_yes)  # ad yeniden kurulabilir

    assert plugin_version.sweep_orphans(root, now=time.time()) == ()
    swept = plugin_version.sweep_orphans(root, now=time.time() + 15 * 86400)
    assert swept == (orphan,) and not orphan.exists()
