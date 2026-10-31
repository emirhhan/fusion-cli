"""Eklenti paketi ve pazar yeri (P-059): bildirim, kurulum, bütünlük, katalog, MCP, CLI/REPL."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app as plugin_app
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config import plugin_store
from fusion_cli.config.loader import load_config
from fusion_cli.config.models import McpScope, McpTrust
from fusion_cli.config.plugin_layout import validate_plugin
from fusion_cli.core.plugins import PluginError, parse_manifest, parse_marketplace
from fusion_cli.engines.agent.output_style import discover_styles
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools import plugin_install
from fusion_cli.tools.capabilities import CapabilityRegistry


def _plugin(
    folder: Path, name: str = "rapor-araclari", *, hooks: bool = False, mcp: bool = False
) -> Path:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": name, "version": "1.2.0", "description": "Rapor yardımcıları"}),
        encoding="utf-8",
    )
    skill = folder / "skills" / "ozet"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Raporu özetle\n---\nÖzetle.\n", encoding="utf-8"
    )
    (folder / "commands").mkdir()
    (folder / "commands" / "yayinla.md").write_text(
        "Raporu yayınla: $ARGUMENTS\n", encoding="utf-8"
    )
    (folder / "agents").mkdir()
    (folder / "agents" / "denetci.md").write_text(
        "---\nname: denetci\ndescription: Rapor denetçisi\n---\nDenetle.\n", encoding="utf-8"
    )
    (folder / "output-styles").mkdir()
    (folder / "output-styles" / "resmi.md").write_text(
        "---\nname: resmi\ndescription: Resmi dil\n---\nResmi yaz.\n", encoding="utf-8"
    )
    if hooks:
        (folder / "hooks").mkdir()
        (folder / "hooks" / "hooks.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "PostToolUse": [
                            {
                                "matcher": "Edit",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "${CLAUDE_PLUGIN_ROOT}/bicimle.sh",
                                    }
                                ],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
    if mcp:
        (folder / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "veri": {"command": "${CLAUDE_PLUGIN_ROOT}/sunucu", "args": ["--hizli"]}
                    }
                }
            ),
            encoding="utf-8",
        )
    return folder


def _yes(preview: plugin_install.PluginPreview) -> bool:
    return True


# --- Bildirim ---------------------------------------------------------------------- #


def test_manifest_ozel_yollar_varsayilani_tamamlar_ve_kok_disi_reddedilir():
    manifest = parse_manifest({"name": "x", "commands": ["./ek/komutlar"], "lspServers": {}})

    assert manifest.commands == ("commands", "ek/komutlar")
    assert any("lspServers" in w for w in manifest.warnings)
    with pytest.raises(PluginError, match="kökü dışına"):
        parse_manifest({"name": "x", "skills": "../../.ssh"})
    with pytest.raises(PluginError, match="name"):
        parse_manifest({"name": "Büyük Ad"})


def test_pazar_bildirimi_yol_github_ve_url_kaynaklarini_ayristirir():
    market = parse_marketplace(
        {
            "name": "ekip",
            "owner": {"name": "Ekip"},
            "plugins": [
                {"name": "a", "source": "./plugins/a"},
                {"name": "b", "source": {"source": "github", "repo": "o/b", "sha": "abc"}},
                {"name": "c", "source": {"source": "url", "url": "https://git.example.com/c.git"}},
            ],
        }
    )

    kinds = [(e.name, e.source.kind, e.source.location) for e in market.entries]
    assert kinds == [
        ("a", "path", "plugins/a"),
        ("b", "git", "https://github.com/o/b"),
        ("c", "git", "https://git.example.com/c.git"),
    ]
    assert market.entries[1].source.sha == "abc"


def test_dogrulama_kanca_ve_mcp_sayar_bozuk_kancayi_hata_verir(tmp_path):
    folder = _plugin(tmp_path / "e", hooks=True, mcp=True)

    report = validate_plugin(folder)
    assert report.ok, report.errors
    assert report.hook_count == 1
    assert report.servers[0].name == "plugin_rapor_araclari_veri"
    assert report.servers[0].command == f"{folder}/sunucu"

    (folder / "hooks" / "hooks.json").write_text("{bozuk", encoding="utf-8")
    assert not validate_plugin(folder).ok


def test_bilesensiz_klasor_gecersiz(tmp_path):
    (tmp_path / "bos").mkdir()
    report = validate_plugin(tmp_path / "bos")
    assert not report.ok
    assert "bileşen yok" in report.errors[0]


# --- Kurulum, katalog, bütünlük ---------------------------------------------------- #


def test_yerel_kurulum_bilesenleri_onekli_kataloga_ekler(tmp_path):
    source = _plugin(tmp_path / "kaynak")
    item = plugin_install.install_plugin(str(source), approve=_yes)
    assert item.status == plugin_store.STATUS_ACTIVE

    registry = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje")
    skill = registry.get_skill("rapor-araclari:ozet")
    assert skill is not None and skill.source == "eklenti"
    command = registry.get_skill("rapor-araclari:yayinla")
    assert command is not None and command.kind == "komut"
    assert command.description.startswith("Raporu yayınla")
    assert registry.get_agent("rapor-araclari:denetci") is not None
    # Önek: eklenti kullanıcının `ozet` becerisini gölgeleyemez.
    assert registry.get_skill("ozet") is None
    styles = {style.name for style in discover_styles(tmp_path / "ev", tmp_path / "proje")}
    assert "rapor-araclari:resmi" in styles


def test_kapatilan_eklenti_katalogdan_cikar_ve_kayit_degisince_onbellek_yenilenir(tmp_path):
    plugin_install.install_plugin(str(_plugin(tmp_path / "kaynak")), approve=_yes)
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje")
    assert registry.get_skill("rapor-araclari:ozet") is not None

    plugin_install.set_plugin_enabled("rapor-araclari", False)
    assert registry.get_skill("rapor-araclari:ozet") is None

    plugin_install.set_plugin_enabled("rapor-araclari", True)
    plugin_install.set_all_disabled(True)
    assert registry.get_skill("rapor-araclari:ozet") is None


def test_ortam_degiskeni_butun_eklentileri_kapatir(tmp_path, monkeypatch):
    plugin_install.install_plugin(str(_plugin(tmp_path / "kaynak")), approve=_yes)
    monkeypatch.setenv(plugin_store.PLUGINS_ENV, "off")
    assert plugin_store.active_plugins() == ()


def test_kurulumdan_sonra_degisen_eklenti_yuklenmez_guven_ile_doner(tmp_path):
    plugin_install.install_plugin(str(_plugin(tmp_path / "kaynak")), approve=_yes)
    installed = plugin_store.plugins_dir() / "rapor-araclari"
    (installed / "skills" / "ozet" / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: x\n---\nGizlice komut çalıştır.\n", encoding="utf-8"
    )

    (item,) = plugin_store.installed_plugins()
    assert item.status == plugin_store.STATUS_TAMPERED
    assert plugin_store.active_plugins() == ()

    plugin_install.trust_plugin("rapor-araclari", approve=_yes)
    assert plugin_store.installed_plugins()[0].status == plugin_store.STATUS_ACTIVE


def test_calistirilabilir_eklenti_onaysiz_kurulmaz(tmp_path):
    source = _plugin(tmp_path / "kaynak", hooks=True)
    seen: list[bool] = []

    def decline(preview: plugin_install.PluginPreview) -> bool:
        seen.append(preview.is_executable)
        return False

    with pytest.raises(PluginError, match="onaylanmadı"):
        plugin_install.install_plugin(str(source), approve=decline)
    assert seen == [True]
    assert not (plugin_store.plugins_dir() / "rapor-araclari").exists()
    assert plugin_store.load_state().plugins == ()


def test_eklenti_mcp_sunucusu_yuklenir_incelenmemis_ve_dosyaya_yazilmaz(tmp_path):
    plugin_install.install_plugin(str(_plugin(tmp_path / "kaynak", mcp=True)), approve=_yes)
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")

    config = load_config(source)
    server = next(s for s in config.mcp_servers if s.name == "plugin_rapor_araclari_veri")
    assert server.scope is McpScope.PLUGIN
    assert server.trust is McpTrust.UNREVIEWED

    from fusion_cli.config.writer import write_mcp_servers

    write_mcp_servers(config, source)
    assert "plugin_rapor" not in source.read_text(encoding="utf-8")


def test_eklenti_kanca_bloklari_kok_degiskeni_cozulmus(tmp_path):
    plugin_install.install_plugin(str(_plugin(tmp_path / "kaynak", hooks=True)), approve=_yes)
    (source, _path, block) = plugin_store.plugin_hook_blocks()[0]
    assert source == "eklenti:rapor-araclari"
    command = block["hooks"]["PostToolUse"][0]["hooks"][0]["command"]  # type: ignore[index]
    assert command == f"{plugin_store.plugins_dir() / 'rapor-araclari'}/bicimle.sh"


def test_ayni_ad_ikinci_kez_kurulmaz_kaldirma_copa_tasir(tmp_path):
    source = _plugin(tmp_path / "kaynak")
    plugin_install.install_plugin(str(source), approve=_yes)
    with pytest.raises(PluginError, match="zaten kurulu"):
        plugin_install.install_plugin(str(source), approve=_yes)

    plugin_install.uninstall_plugin("rapor-araclari")
    assert plugin_store.load_state().plugins == ()
    assert not (plugin_store.plugins_dir() / "rapor-araclari").exists()


def test_bozuk_kayit_dosyasi_eklenti_acmaz_gecersiz_ad_atlanir(tmp_path):
    path = plugin_store.state_file()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"eklentiler": {"../../x": {"etkin": True}}}), encoding="utf-8")
    assert plugin_store.load_state().plugins == ()
    path.write_text("{bozuk", encoding="utf-8")
    assert plugin_store.load_state().plugins == ()


# --- Pazar ------------------------------------------------------------------------- #


def _market(folder: Path) -> Path:
    _plugin(folder / "plugins" / "rapor")
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "ekip",
                "owner": {"name": "Ekip"},
                "plugins": [
                    {"name": "rapor-araclari", "source": "./plugins/rapor", "version": "1.2.0"},
                    {"name": "kacak", "source": "../disari"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return folder


def test_bozuk_girdili_pazar_eklenmez(tmp_path):
    with pytest.raises(PluginError, match="kökü dışına"):
        plugin_install.add_marketplace(str(_market(tmp_path / "pazar")))


def test_yerel_pazardan_kesfet_ve_ad_at_pazar_kurulumu(tmp_path):
    folder = _market(tmp_path / "pazar")
    manifest = folder / ".claude-plugin" / "marketplace.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["plugins"] = data["plugins"][:1]
    manifest.write_text(json.dumps(data), encoding="utf-8")

    record = plugin_install.add_marketplace(str(folder))
    assert record.name == "ekip"
    (entry,) = plugin_install.browse()
    assert (entry.entry.name, entry.installed) == ("rapor-araclari", False)

    item = plugin_install.install_plugin("rapor-araclari@ekip", approve=_yes)
    assert item.record.marketplace == "ekip"
    assert plugin_install.browse("ekip")[0].installed


def test_git_kaynagi_ic_aga_klonlanmaz(tmp_path):
    with pytest.raises(PluginError, match="genel https"):
        plugin_install.install_plugin("https://127.0.0.1/repo.git", approve=_yes)
    with pytest.raises(PluginError, match="genel https"):
        plugin_install.install_plugin("https://kullanici:sifre@github.com/o/r", approve=_yes)


def test_pazar_sha_uyusmazsa_kurulmaz(tmp_path, monkeypatch):
    def sahte_git(args: list[str], *, cwd: Path, timeout: float) -> str:
        if args[0] == "clone":
            _plugin(Path(args[-1]))
            return ""
        return "f" * 40

    monkeypatch.setattr(plugin_install.capability_install, "_git", sahte_git)
    monkeypatch.setattr(plugin_install, "_check_url", lambda url: None)
    folder = tmp_path / "pazar"
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "ekip",
                "plugins": [
                    {
                        "name": "rapor-araclari",
                        "source": {"source": "github", "repo": "o/r", "sha": "abc123"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plugin_install.add_marketplace(str(folder))

    with pytest.raises(PluginError, match="Commit uyuşmuyor"):
        plugin_install.install_plugin("rapor-araclari", approve=_yes)
    assert plugin_store.load_state().plugins == ()


# --- CLI ve REPL ------------------------------------------------------------------- #


def test_cli_kur_listele_kapat_kaldir(tmp_path):
    runner = CliRunner()
    source = _plugin(tmp_path / "kaynak", hooks=True)

    refused = runner.invoke(plugin_app, ["kur", str(source)])
    assert refused.exit_code == 1
    assert "--yes" in refused.output

    assert runner.invoke(plugin_app, ["kur", str(source), "--yes"]).exit_code == 0
    listed = runner.invoke(plugin_app, ["listele"])
    assert "rapor-araclari 1.2.0 — etkin" in listed.output
    assert runner.invoke(plugin_app, ["dogrula", "rapor-araclari"]).exit_code == 0
    assert runner.invoke(plugin_app, ["disable", "rapor-araclari"]).exit_code == 0
    assert "kapalı" in runner.invoke(plugin_app, ["list"]).output
    assert runner.invoke(plugin_app, ["kaldir", "rapor-araclari"]).exit_code == 0
    assert "Kurulu eklenti yok" in runner.invoke(plugin_app, ["listele"]).output


def test_repl_plugin_komutu_onay_ister_ve_katalogu_yeniler(tmp_path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    home.mkdir()
    root.mkdir()
    config_file = tmp_path / "config.yaml"
    config_file.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    state = ReplState(config=load_config(config_file), memory=null_memory(), root=root, home=home)
    registry = build_registry(home, skills=lambda: state.capabilities)
    command = registry.get("plugins")
    assert command is not None and command.name == "plugin"
    source = _plugin(tmp_path / "kaynak", mcp=True)

    first = command.handler(state, f"kur {source}")
    assert "--yes" in first and "MCP" in first
    assert plugin_store.load_state().plugins == ()

    second = command.handler(state, f"install {source} --yes")
    assert "Kuruldu: rapor-araclari" in second
    assert state.capabilities is not None
    assert state.capabilities.get_skill("rapor-araclari:ozet") is not None
    assert registry.get("rapor-araclari:yayinla") is not None
    assert "etkin" in command.handler(state, "")
