"""Proje `.mcp.json` sunucu onayı Claude Code gibi (#246)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from fusion_cli.config import loader, mcp_policy, trust
from fusion_cli.config import mcp_project_approval as approval
from fusion_cli.config.models import McpScope


@pytest.fixture
def izole(tmp_path, monkeypatch):
    kok = tmp_path / "proje"
    kok.mkdir()
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.chdir(kok)
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    kullanici = tmp_path / "xdg" / "fusion-cli" / "config.yaml"
    monkeypatch.setattr(loader, "user_config_candidates", lambda: (kullanici,))
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "guven.json")
    monkeypatch.setattr(mcp_policy, "managed_dir", lambda: tmp_path / "yonetilen")
    approval.set_noninteractive(False)
    yield kok
    approval.set_noninteractive(False)


def _mcp(kok, *names):
    servers = {name: {"command": "npx", "args": ["-y", name]} for name in names}
    (kok / ".mcp.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _settings(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _project_names():
    config = loader.load_config()
    return [s.name for s in config.mcp_servers if s.scope is McpScope.PROJECT]


def test_onaysiz_sunucu_etkilesimli_oturumda_yuklenmez_ve_bekler(izole):
    _mcp(izole, "github")
    assert _project_names() == []
    assert [s.name for s in approval.pending_project_servers(izole)] == ["github"]


def test_sunucu_basina_onay_yalniz_o_sunucuyu_acar(izole):
    _mcp(izole, "github", "linear")
    approval.record_choice(izole, "github", approval.CHOICE_ONE)
    assert _project_names() == ["github"]
    assert [s.name for s in approval.pending_project_servers(izole)] == ["linear"]


def test_hepsini_kullan_gelecekteki_sunuculari_da_acar(izole):
    _mcp(izole, "github")
    approval.record_choice(izole, "github", approval.CHOICE_ALL)
    _mcp(izole, "github", "yeni")
    assert _project_names() == ["github", "yeni"]


def test_reddedilen_sunucu_hic_sorulmaz_ve_yuklenmez(izole):
    _mcp(izole, "github")
    approval.record_choice(izole, "github", approval.CHOICE_NO)
    assert _project_names() == []
    assert approval.pending_project_servers(izole) == ()


def test_reset_project_choices_secimleri_siler(izole):
    _mcp(izole, "github")
    approval.record_choice(izole, "github", approval.CHOICE_NO)
    assert approval.reset_project_choices(izole) is True
    assert [s.name for s in approval.pending_project_servers(izole)] == ["github"]
    assert approval.reset_project_choices(izole) is False


def test_kullanici_ayari_enabled_mcpjson_servers_guvenilmeyen_klasorde_de_gecer(izole):
    _mcp(izole, "github", "linear")
    _settings(
        izole.parent / "ev" / ".claude" / "settings.json", {"enabledMcpjsonServers": ["linear"]}
    )
    assert _project_names() == ["linear"]


def test_proje_ayari_guvenilmeyen_klasorde_onay_veremez(izole):
    _mcp(izole, "github")
    _settings(izole / ".claude" / "settings.json", {"enableAllProjectMcpServers": True})
    assert _project_names() == []
    trust.trust_project(izole)
    _mcp(izole, "github", "yeni")  # .mcp.json değişti; klasör güveni sürer
    assert _project_names() == ["github", "yeni"]


def test_disabled_mcpjson_servers_her_kaynaktan_ve_her_kipte_reddeder(izole):
    _mcp(izole, "github")
    trust.trust_project(izole)
    _settings(izole / ".claude" / "settings.json", {"disabledMcpjsonServers": ["github"]})
    approval.set_noninteractive(True)
    assert _project_names() == []


def test_yonetilen_ayar_onayi_gecer(izole, tmp_path):
    _mcp(izole, "github")
    _settings(
        tmp_path / "yonetilen" / "managed-settings.json", {"enabledMcpjsonServers": ["github"]}
    )
    assert _project_names() == ["github"]


def test_etkilesimsiz_kipte_guvenilen_klasorde_sormadan_yuklenir(izole):
    _mcp(izole, "github")
    trust.trust_project(izole)
    _mcp(izole, "github", "yeni")  # dosya güveni düştü, klasör güveni duruyor
    assert _project_names() == []
    approval.set_noninteractive(True)
    assert _project_names() == ["github", "yeni"]


def test_etkilesimsiz_kipte_guvenilmeyen_klasor_kurali_korunur(izole):
    _mcp(izole, "github")
    approval.set_noninteractive(True)
    assert _project_names() == []


def test_fusion_trust_ile_guvenilen_dosya_onaylanmis_sayilir(izole):
    _mcp(izole, "github")
    trust.trust_project(izole)
    assert _project_names() == ["github"]


def test_istem_secimleri_kaydeder(izole):
    _mcp(izole, "a", "b", "c")
    answers = iter([approval.CHOICE_ONE, approval.CHOICE_NO, approval.CHOICE_ONE])
    asked = approval.prompt_pending(izole, lambda server: next(answers))
    assert [s.name for s in asked] == ["a", "b", "c"]
    assert _project_names() == ["a", "c"]


def test_istemde_hepsi_secilince_kalanlar_sorulmaz(izole):
    _mcp(izole, "a", "b")
    asked = approval.prompt_pending(izole, lambda server: approval.CHOICE_ALL)
    assert [s.name for s in asked] == ["a"]
    assert _project_names() == ["a", "b"]


def test_cli_reset_project_choices(izole):
    from fusion_cli.cli.app import app

    _mcp(izole, "github")
    approval.record_choice(izole, "github", approval.CHOICE_ONE)
    result = CliRunner().invoke(app, ["mcp", "reset-project-choices"])
    assert result.exit_code == 0, result.output
    assert "sıfırlandı" in result.output
    assert _project_names() == []


def test_konsol_istemi_gecersiz_yaniti_yeniden_sorar(izole):
    import io

    from rich.console import Console

    from fusion_cli.cli.mcp_approval_prompt import ask_with_console

    _mcp(izole, "github")
    answers = iter(["", "9", "2"])
    out = io.StringIO()
    ask = ask_with_console(Console(file=out, width=200), read=lambda _prompt: next(answers))
    server = approval.pending_project_servers(izole)[0]
    assert ask(server) == approval.CHOICE_ONE
    assert "Yeni MCP sunucusu bulundu (.mcp.json): github" in out.getvalue()
