"""Eklenti bildirimi ve pazar ayrıştırması Claude Code belgesiyle birebir (#378, #384, #385,
#397, #399, #402, #406, #411, #413, #418)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.config.plugin_layout import mcp_servers, validate_plugin
from fusion_cli.config.plugin_scan import scan_plugin
from fusion_cli.core.plugin_paths import reserved_level
from fusion_cli.core.plugins import PluginError, parse_manifest, parse_marketplace
from fusion_cli.tools import plugin_install
from fusion_cli.tools.capabilities import CapabilityRegistry


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _manifest(root: Path, data: dict[str, object]) -> Path:
    _write(root / ".claude-plugin" / "plugin.json", json.dumps(data))
    return root


def _market(entries: list[object], **extra: object) -> dict[str, object]:
    return {"name": "ekip", "owner": {"name": "Ekip"}, "plugins": entries, **extra}


# --- #378: kök kaynak './' ve '.' ------------------------------------------------- #


def test_kok_kaynak_nokta_ve_nokta_bolu_cokmez():
    market = parse_marketplace(
        _market([{"name": "a", "source": "./"}, {"name": "b", "source": "."}])
    )
    assert [e.source.location for e in market.entries] == [".", "."]
    assert parse_manifest({"name": "x", "skills": "./"}).skills == ("skills", ".")
    assert parse_manifest({"name": "x", "skills": "."}).skills == ("skills", ".")


def test_kok_skills_nokta_kokteki_skill_md_yi_yukler(tmp_path):
    root = _manifest(tmp_path / "tek", {"name": "tek", "skills": "./"})
    _write(root / "SKILL.md", "---\nname: tek\ndescription: Tek beceri\n---\nGövde\n")
    assert scan_plugin(root).skills == (root / "SKILL.md",)


# --- #384: varsayılanla birleşme ------------------------------------------------- #


def test_commands_agents_styles_varsayilanin_yerine_gecer_skills_eklenir(tmp_path):
    root = _manifest(
        tmp_path / "p",
        {"name": "p", "commands": "./ozel", "skills": "./ek-beceri", "agents": "./a/x.md"},
    )
    _write(root / "commands" / "eski.md", "eski")
    _write(root / "ozel" / "yeni.md", "yeni")
    _write(root / "skills" / "s1" / "SKILL.md", "---\nname: s1\ndescription: d\n---\n")
    _write(root / "ek-beceri" / "s2" / "SKILL.md", "---\nname: s2\ndescription: d\n---\n")
    _write(root / "agents" / "eski.md", "---\nname: eski\ndescription: d\n---\n")
    _write(root / "a" / "x.md", "---\nname: x\ndescription: d\n---\n")

    layout = scan_plugin(root)

    assert [name for name, _p in layout.commands] == ["yeni"]
    assert {p.parent.name for p in layout.skills} == {"s1", "s2"}
    assert layout.agents == (root / "a" / "x.md",)
    report = validate_plugin(root)
    assert any("Varsayılan commands/" in w for w in report.warnings)
    assert any("Varsayılan agents/" in w for w in report.warnings)


def test_varsayilan_klasordeki_dosyayi_gosteren_yol_uyari_vermez(tmp_path):
    root = _manifest(tmp_path / "p", {"name": "p", "commands": ["./commands/dagit.md"]})
    _write(root / "commands" / "dagit.md", "Dağıt")
    _write(root / "commands" / "diger.md", "Diğer")
    report = validate_plugin(root)
    assert report.layout is not None
    assert [name for name, _p in report.layout.commands] == ["dagit"]
    assert not any("Varsayılan" in w for w in report.warnings)


# --- #385, #402: bileşen biçimleri ve dosya yolları ------------------------------ #


def test_commands_haritasi_source_ve_content_kataloga_girer(tmp_path):
    root = _manifest(
        tmp_path / "harita",
        {
            "name": "harita",
            "commands": {
                "durum": {"source": "./komut/durum.md", "description": "Durumu göster"},
                "hakkinda": {"content": "Eklentiyi anlat.", "argumentHint": "[konu]"},
            },
        },
    )
    _write(root / "komut" / "durum.md", "Durum gövdesi")
    plugin_install.install_plugin(str(root), approve=lambda _p: True)

    registry = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje")
    durum = registry.get_skill("harita:durum")
    hakkinda = registry.get_skill("harita:hakkinda")
    assert durum is not None and durum.description == "Durumu göster"
    assert hakkinda is not None and hakkinda.argument_hint == "[konu]"


def test_commands_haritasi_source_ve_content_birlikte_gecersiz():
    with pytest.raises(PluginError, match="tam biri"):
        parse_manifest({"name": "x", "commands": {"a": {"source": "./a.md", "content": "b"}}})


def test_hooks_ve_mcp_karisik_dizi_kabul_edilir(tmp_path):
    hook = {"PostToolUse": [{"hooks": [{"type": "command", "command": "echo satir"}]}]}
    root = _manifest(
        tmp_path / "karisik",
        {
            "name": "karisik",
            "hooks": ["./ek/kanca.json", hook],
            "mcpServers": ["./ek/mcp.json", {"ikinci": {"command": "node"}}],
        },
    )
    _write(
        root / "ek" / "kanca.json",
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo x"}]}]}}),
    )
    _write(root / "ek" / "mcp.json", json.dumps({"mcpServers": {"bir": {"command": "node"}}}))
    report = validate_plugin(root)
    assert report.ok, report.errors
    assert report.hook_count == 2
    assert len(report.servers) == 2


def test_dosya_yolu_komut_ve_stil_yuklenir_olmayan_yol_hata(tmp_path):
    root = _manifest(
        tmp_path / "dosya",
        {
            "name": "dosya",
            "commands": ["./tek/dagit.md", "./yok/"],
            "outputStyles": "./stil/kisa.md",
        },
    )
    _write(root / "tek" / "dagit.md", "Dağıt")
    _write(root / "stil" / "kisa.md", "---\nname: kisa\ndescription: d\n---\nKısa yaz.")
    report = validate_plugin(root)
    assert report.layout is not None
    assert [name for name, _p in report.layout.commands] == ["dagit"]
    assert report.layout.output_styles == (root / "stil" / "kisa.md",)
    assert any("bulunamadı: ./yok" in error for error in report.errors)


def test_agents_klasor_kabul_etmez(tmp_path):
    root = _manifest(tmp_path / "ajan", {"name": "ajan", "agents": "./ozel-ajanlar"})
    _write(root / "ozel-ajanlar" / "a.md", "---\nname: a\ndescription: d\n---\n")
    report = validate_plugin(root)
    assert any(".md dosyası olmalı" in error for error in report.errors)


def test_skills_yoksa_kokteki_tek_skill_md_yuklenir(tmp_path):
    root = tmp_path / "kok-beceri"
    _write(root / "SKILL.md", "---\nname: kok-beceri\ndescription: d\n---\nGövde")
    assert scan_plugin(root).skills == (root / "SKILL.md",)


# --- #406: eklenti adı ----------------------------------------------------------- #


def test_buyuk_harf_serbest_kebab_disi_ad_uyari_ayrilmis_ad_hata():
    assert parse_manifest({"name": "Rapor_Araclari"}).name == "Rapor_Araclari"
    for bad in ("a b", "a@b", "a:b", "a/b", "..", "a‮b"):
        with pytest.raises(PluginError):
            parse_manifest({"name": bad})
    assert reserved_level("claude-tools") == "error"
    assert reserved_level("official-claude-tools") == "error"
    assert reserved_level("mcp-for-claude") == "warning"
    assert reserved_level("rapor") == ""


def test_dogrulama_kebab_uyarisi(tmp_path):
    root = _manifest(tmp_path / "x", {"name": "Rapor_X", "commands": "./k.md"})
    _write(root / "k.md", "k")
    assert any("kebab-case" in w for w in validate_plugin(root).warnings)


# --- #413: eski .fusion-plugin yolu ---------------------------------------------- #


def test_fusion_plugin_yolu_kullanimdan_kalkti_uyarisi(tmp_path):
    root = tmp_path / "eski"
    _write(root / ".fusion-plugin" / "plugin.json", json.dumps({"name": "eski"}))
    _write(root / "commands" / "a.md", "a")
    report = validate_plugin(root)
    assert report.ok
    assert any(".claude-plugin/plugin.json" in w for w in report.warnings)


# --- #418: yinelenen MCP adı ----------------------------------------------------- #


def test_sonra_tanimlanan_mcp_sunucusu_oncekinin_yerine_gecer(tmp_path):
    root = _manifest(tmp_path / "mcp", {"name": "mcp", "mcpServers": {"api": {"command": "yeni"}}})
    _write(root / ".mcp.json", json.dumps({"mcpServers": {"api": {"command": "eski"}}}))
    layout = scan_plugin(root)
    (server,) = mcp_servers(layout)
    assert server.command == "yeni"


# --- #397, #399, #411: pazar ----------------------------------------------------- #


def test_owner_name_zorunlu_yinelenen_ad_hata():
    with pytest.raises(PluginError, match=r"owner\.name"):
        parse_marketplace({"name": "ekip", "plugins": []})
    with pytest.raises(PluginError, match="yinelenen"):
        parse_marketplace(_market([{"name": "a", "source": "./a"}, {"name": "a", "source": "./b"}]))


def test_kaynak_kurallari_sha_git_ve_pluginroot():
    market = parse_marketplace(
        _market(
            [
                {"name": "ciplak", "source": "bicimlendir"},
                {"name": "bolu", "source": "ekip/bicim"},
                {"name": "kisa", "source": {"source": "github", "repo": "o/r", "sha": "abc1234"}},
                {"name": "eski", "source": {"source": "git", "url": "https://h/x.git"}},
            ],
            metadata={"pluginRoot": "./plugins"},
        )
    )
    assert [e.name for e in market.entries] == ["ciplak", "eski"]
    assert market.entries[0].source.location == "plugins/bicimlendir"
    assert any("'git' türü" in w for w in market.warnings)
    assert sum("atlandı" in w for w in market.warnings) == 2


@pytest.mark.parametrize(
    "name",
    ["claude-plugins-official", "inline", "skills-dir", "npm", "GitHub", "claudeai-x",
     "official-claude-plugins", "claude-plugins-v2", "pazarç"],
)  # fmt: skip
def test_ayrilmis_pazar_adlari_reddedilir(name):
    with pytest.raises(PluginError, match=r"ayrılmış|harf ya da rakam"):
        parse_marketplace(_market([], name=name))


def test_pazar_adinda_buyuk_harf_serbest():
    assert parse_marketplace(_market([], name="Ekip.Pazar_1")).name == "Ekip.Pazar_1"


# --- #377: ~/.claude/plugins ham kök değil ---------------------------------------- #


def _claude_install(home: Path, plugin_id: str, version: str, *, orphan: bool = False) -> Path:
    name, market = plugin_id.split("@")
    path = home / ".claude" / "plugins" / "cache" / market / name / version
    _write(path / "skills" / "ozet" / "SKILL.md", "---\nname: ozet\ndescription: d\n---\n")
    if orphan:
        _write(path / ".orphaned_at", "1")
    return path


def test_claude_eklentileri_yalniz_etkinse_onekle_yuklenir(tmp_path):
    home = tmp_path / "ev"
    acik = _claude_install(home, "acik@pazar", "1.0.0")
    kapali = _claude_install(home, "kapali@pazar", "1.0.0")
    _claude_install(home, "acik@pazar", "0.9.0", orphan=True)
    # Pazar klonundaki kurulmamış eklenti de taranmamalı.
    _write(
        home / ".claude" / "plugins" / "marketplaces" / "pazar" / "x" / "skills" / "y" / "SKILL.md",
        "---\nname: y\ndescription: d\n---\n",
    )
    installs = {
        "acik@pazar": [{"scope": "user", "installPath": str(acik)}],
        "kapali@pazar": [{"scope": "user", "installPath": str(kapali)}],
    }
    _write(
        home / ".claude" / "plugins" / "installed_plugins.json",
        json.dumps({"version": 2, "plugins": installs}),
    )
    _write(
        home / ".claude" / "settings.json", json.dumps({"enabledPlugins": {"kapali@pazar": False}})
    )

    registry = CapabilityRegistry(home, tmp_path / "proje")
    names = {skill.name for skill in registry.skills()}

    assert "acik:ozet" in names
    assert not {"ozet", "kapali:ozet", "y"} & names


# --- #375: eklenti kancaları çalışır -------------------------------------------- #


def test_eklenti_kancasi_yuklenir_ve_ortam_degiskenleriyle_calisir(tmp_path, monkeypatch):
    import asyncio

    from fusion_cli.config.hooks import hook_environment, load_hooks
    from fusion_cli.core.hooks.events import HookEvent
    from fusion_cli.engines.hooks.runner import run_hook

    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    out = tmp_path / "cikti.txt"
    names = '"$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PLUGIN_DATA" "$CLAUDE_PROJECT_DIR"'
    command = f'printf "%s|%s|%s" {names} > {out}'
    hook = {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}
    root = _manifest(tmp_path / "kancali", {"name": "kancali", "hooks": hook})
    plugin_install.install_plugin(str(root), approve=lambda _p: True)
    project = tmp_path / "proje"
    project.mkdir()

    hooks = load_hooks(project, home=tmp_path / "ev")
    (found,) = [c for c in hooks.commands if c.source == "eklenti:kancali"]
    assert found.event == HookEvent.STOP
    asyncio.run(run_hook(found, {}, cwd=project, environment=hook_environment(project)))

    plugin_root, data, project_dir = out.read_text().split("|")
    assert plugin_root.endswith("eklentiler/kancali")
    assert "/.veri/kancali" in data and Path(data).is_dir()
    assert project_dir == str(project)


# --- #404, #405: eklenti ajanları ----------------------------------------------- #


def test_alt_klasor_ajani_adi_ve_yok_sayilan_alanlar(tmp_path):
    root = _manifest(tmp_path / "ajanlar", {"name": "ajanlar"})
    _write(
        root / "agents" / "inceleme" / "guvenlik.md",
        "---\nname: guvenlik\ndescription: d\npermissionMode: bypassPermissions\n"
        "initialPrompt: başla\nmcpServers: [github]\n"
        "hooks:\n  Stop:\n    - hooks:\n        - type: command\n          command: echo x\n"
        "---\nİncele.\n",
    )
    plugin_install.install_plugin(str(root), approve=lambda _p: True)
    agent = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje").get_agent(
        "ajanlar:inceleme:guvenlik"
    )
    assert agent is not None
    assert agent.permission_mode == "" and agent.initial_prompt == ""
    assert agent.mcp_servers == () and agent.hooks == ()
    assert not agent.hook_definitions.commands


# --- #407, #409, #410, #417: CLI davranışları ----------------------------------- #


def test_cli_yeniden_kurma_zaten_acik_ve_hepsini_kapat(tmp_path):
    from typer.testing import CliRunner

    from fusion_cli.cli.plugin_commands import app
    from fusion_cli.config import plugin_store

    runner = CliRunner()
    for name in ("bir", "iki"):
        root = _manifest(tmp_path / name, {"name": name})
        _write(root / "commands" / "k.md", "k")
        assert runner.invoke(app, ["kur", str(root)]).exit_code == 0

    again = runner.invoke(app, ["kur", str(tmp_path / "bir")])
    assert again.exit_code == 0 and "zaten kurulu" in again.output
    already = runner.invoke(app, ["ac", "bir"])
    assert already.exit_code == 1 and "zaten açık" in already.output
    assert runner.invoke(app, ["kapat", "bir", "--all"]).exit_code == 1

    closed = runner.invoke(app, ["kapat", "--all"])
    assert closed.exit_code == 0 and "2 eklenti kapatıldı" in closed.output
    state = plugin_store.load_state()
    assert not state.all_disabled
    assert [record.enabled for record in state.plugins] == [False, False]


def test_pazar_guncelle_adsiz_hepsini_yeniler(tmp_path):
    from typer.testing import CliRunner

    from fusion_cli.cli.plugin_commands import app

    for name in ("a", "b"):
        _write(
            tmp_path / name / ".claude-plugin" / "marketplace.json",
            json.dumps(_market([], name=f"pazar-{name}")),
        )
        plugin_install.add_marketplace(str(tmp_path / name))
    result = CliRunner().invoke(app, ["pazar", "guncelle"])
    assert result.exit_code == 0 and "2 pazar güncellendi" in result.output


def test_claude_komut_adlari_birincil_ve_takma_adlar():
    from typer.testing import CliRunner

    from fusion_cli.cli.plugin_commands import app

    runner = CliRunner()
    shown = runner.invoke(app, ["--help"]).output
    for name in ("install", "uninstall", "enable", "disable", "list", "validate", "marketplace"):
        assert name in shown
    assert "│ kur " not in shown and "│ pazar " not in shown
    for alias in (["i", "--help"], ["rm", "--help"], ["remove", "--help"], ["kur", "--help"]):
        assert runner.invoke(app, alias).exit_code == 0
    assert runner.invoke(app, ["marketplace", "rm", "--help"]).exit_code == 0


# --- #389, #390: defaultEnabled ve bildirimsiz eklentinin adı -------------------- #


def test_bildirimsiz_eklenti_adi_klasorden_ve_pazar_girdisinden_gelir(tmp_path):
    from fusion_cli.config import plugin_store

    local = tmp_path / "Benim-Araclarim"
    _write(local / "commands" / "k.md", "k")
    assert plugin_install.install_plugin(str(local), approve=lambda _p: True).record.name == (
        "Benim-Araclarim"
    )
    market = tmp_path / "pazar"
    _write(market / "eklentiler" / "klasor" / "commands" / "k.md", "k")
    _write(
        market / ".claude-plugin" / "marketplace.json",
        json.dumps(_market([{"name": "girdi-adi", "source": "./eklentiler/klasor"}])),
    )
    plugin_install.add_marketplace(str(market))
    item = plugin_install.install_plugin("girdi-adi@ekip", approve=lambda _p: True)
    assert item.record.name == "girdi-adi"
    assert plugin_store.load_state().plugin("girdi-adi") is not None


def test_default_enabled_false_kapali_kurulur(tmp_path):
    root = _manifest(tmp_path / "kapali", {"name": "kapali", "defaultEnabled": False})
    _write(root / "commands" / "k.md", "k")
    item = plugin_install.install_plugin(str(root), approve=lambda _p: True)
    assert item.record.enabled is False
