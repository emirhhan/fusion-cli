"""Kapsam önceliği, yerleşik roller ve açıklamadan otomatik yönlendirme dizini."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fusion_cli.engines.agent.team import GENERIC_PERSONA, resolve_persona
from fusion_cli.tools.capabilities import Capability, CapabilityRegistry


def _agent(folder: Path, name: str = "denetci", body: str = "Talimat") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    path.write_text(f"---\nname: {name}\ndescription: {body}\n---\n{body}", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "name",
    ["Explore", "Plan", "general-purpose", "claude", "statusline-setup", "claude-code-guide"],
)
def test_uyumluluk_rolleri_gercek_kisilik_ve_miras_modelle_cozulur(
    tmp_path: Path, name: str
) -> None:
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path)

    agent = registry.get_agent(name)
    persona = resolve_persona(registry, name)

    assert agent is not None and agent.source == "fusion" and agent.description
    # Claude Code: statusline-setup Sonnet, claude-code-guide Haiku; ötekiler ana modeli alır.
    expected_model = {"statusline-setup": "sonnet", "claude-code-guide": "haiku"}
    assert agent.model == expected_model.get(name, "inherit") or agent.model == ""
    assert persona is not GENERIC_PERSONA and persona.prompt
    assert "Fusion" in persona.prompt
    if name in {"Explore", "Plan"}:
        assert persona.tools is not None and "write_file" not in persona.tools
        assert "edit_file" not in persona.tools
    if name in {"Explore", "Plan"}:
        # Claude Code Explore ve Plan: salt okur araçlar; Write/Edit yasak, Bash var (izin
        # kurallarıyla; Plan plan kipinde yalnız okuyan komutları çalıştırır).
        assert "run_shell" in persona.tools
    if name == "Explore":
        assert "quick" in agent.description and "very thorough" in agent.description


def test_eski_turkce_roller_ve_kucuk_harf_takma_adlari_korunur(tmp_path: Path) -> None:
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path)

    assert registry.get_agent("Explore") == registry.get_agent("explore")
    assert registry.get_agent("Plan") == registry.get_agent("plan")
    for name in ("kodcu", "mimar", "testci", "tasarimci", "arastirmaci", "yonetmen"):
        assert registry.get_agent(name) is not None


def test_ozel_exact_explore_tanimi_yerlesik_takma_addan_once_gelir(tmp_path: Path) -> None:
    path = _agent(tmp_path / ".claude/agents", "Explore", "Özel keşif")

    agent = CapabilityRegistry(tmp_path / "ev", tmp_path).get_agent("Explore")

    assert agent is not None and agent.path == path


@pytest.mark.parametrize("winner", ["managed", "cli", "project", "user"])
def test_tum_desteklenen_kapsamlar_resmi_oncelikle_cozulur(tmp_path: Path, winner: str) -> None:
    home, root, managed = tmp_path / "ev", tmp_path / "proje", tmp_path / "yonetilen"
    _agent(home / ".claude/agents", body="Kullanıcı")
    sessions: tuple[Capability, ...] = ()
    managed_roots: tuple[Path, ...] = ()
    expected = "Kullanıcı"
    if winner != "user":
        _agent(root / ".claude/agents", body="Proje")
        expected = "Proje"
    if winner in {"managed", "cli"}:
        sessions = (
            Capability("denetci", "Oturum", root / "oturum.md", "cli", inline_prompt="CLI"),
        )
        expected = "CLI"
    if winner == "managed":
        _agent(managed, body="Yönetilen")
        managed_roots, expected = (managed,), "Yönetilen"
    registry = CapabilityRegistry(home, root, managed_roots=managed_roots, session_agents=sessions)

    persona = resolve_persona(registry, "denetci")

    assert persona.prompt == expected
    assert len([item for item in registry.agents() if item.name == "denetci"]) == 1


def test_ic_ice_proje_kokleri_en_yakin_tanimi_secer_ve_kullanici_alt_dizini_taranir(
    tmp_path: Path,
) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    working = root / "paket" / "src"
    working.mkdir(parents=True)
    _agent(root / ".claude/agents", body="Üst proje")
    nearest = _agent(root / "paket/.claude/agents", body="Yakın proje")
    user = _agent(home / ".claude/agents/inceleme", name="guvenlik", body="Güvenlik")
    registry = CapabilityRegistry(home, root, working_directory=working)

    selected = registry.get_agent("denetci")
    security = registry.get_agent("guvenlik")

    assert selected is not None and selected.path == nearest
    assert security is not None and security.path == user


def test_inline_bos_prompt_ve_kopyalanan_registry_scope_girdilerini_korur(tmp_path: Path) -> None:
    from fusion_cli.tools.capabilities import agent_prompt

    inline = Capability("bos", "Boş", tmp_path / "yok.md", "cli", inline_prompt="")
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path, session_agents=(inline,))

    assert agent_prompt(inline) == ""
    assert registry.with_extra_roots(()).get_agent("bos") == inline


def test_aciklama_dizini_govdeyi_yuklemez_ve_buyuk_dizinde_ajan_dusurmez(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from fusion_cli.tools.agent_catalog_index import agent_catalog_index

    path = _agent(tmp_path / ".claude/agents", body="Güvenlik için proaktif inceleme")
    path.write_text(path.read_text() + "\nGİZLİ AJAN GÖVDESİ", encoding="utf-8")
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path)
    with caplog.at_level(logging.WARNING):
        index = agent_catalog_index(registry, count_tokens=lambda text: 15_001)

    assert "denetci" in index and "Güvenlik için proaktif inceleme" in index
    assert "GİZLİ AJAN GÖVDESİ" not in index
    assert "Agent aracıyla" in index and "spawn_agent" not in index
    assert "description" not in index
    # Claude Code'un 6 yerleşiği + özel ajan; hiçbiri dizinden düşmez (#25).
    assert len(registry.agents()) >= 7
    assert any(getattr(record, "token_sayisi", 0) == 15_001 for record in caplog.records)


def test_canonical_arac_adlari_eski_takma_adlarla_ayni_aileye_cozulur() -> None:
    from fusion_cli.tools.capabilities import map_tools

    assert {"Agent", "spawn_agent", "spawn_agents"} <= (map_tools(("Agent",)) or set())
    assert map_tools(("Task",)) == map_tools(("Agent",))
    assert {"SendMessage", "send_message"} <= (map_tools(("SendMessage",)) or set())
    assert {"ListAgents", "list_agents"} <= (map_tools(("ListAgents",)) or set())
    assert {"TaskStop", "stop_agent"} <= (map_tools(("TaskStop",)) or set())


def test_plugin_ajaninda_desteklenmeyen_yurutulebilir_alanlar_temizlenir(tmp_path: Path) -> None:
    from fusion_cli.core.hooks.events import HookSet
    from fusion_cli.tools import capabilities

    path = _agent(tmp_path / "eklenti/agents", body="Eklenti")
    path.write_text(
        "---\nname: denetci\ndescription: Denetçi\npermissionMode: bypassPermissions\n"
        "initialPrompt: Çalıştır\nmcpServers: sunucu\n"
        "hooks:\n  PreToolUse:\n    - hooks:\n        - type: command\n"
        "          command: echo denetle\n---\nEklenti",
        encoding="utf-8",
    )

    agent = capabilities._to_capability(path, "eklenti", fallback="denetci")

    assert agent.permission_mode == "" and agent.initial_prompt == ""
    assert agent.hooks == () and agent.hook_definitions == HookSet()
    assert agent.mcp_servers == () and agent.inline_mcp_servers == ()


def test_ic_ice_plugin_ajani_scoped_adla_cozulur_ve_kok_disi_bag_taranmaz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fusion_cli.config.plugin_layout import scan_plugin
    from fusion_cli.config.plugin_store import STATUS_ACTIVE, InstalledPlugin, PluginRecord
    from fusion_cli.tools import plugin_capabilities

    plugin = tmp_path / "paket"
    manifest = plugin / ".claude-plugin/plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"name":"paket"}', encoding="utf-8")
    _agent(plugin / "agents/inceleme", name="guvenlik", body="Güvenlik denetimi")
    outside = _agent(tmp_path / "disarisi", name="sizan", body="Dış dosya")
    (plugin / "agents/inceleme/sizan.md").symlink_to(outside)
    layout = scan_plugin(plugin)
    installed = InstalledPlugin(PluginRecord("paket"), layout, STATUS_ACTIVE)
    monkeypatch.setattr(plugin_capabilities, "active_plugins", lambda: (installed,))
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje")

    agent = registry.get_agent("paket:inceleme:guvenlik")

    assert agent is not None and agent.source == "eklenti"
    assert resolve_persona(registry, agent.name).prompt == "Güvenlik denetimi"
    assert not any("sizan" in item.name for item in registry.agents())


def test_dizin_ayri_kaynaklari_cagrilabilir_nitelikli_adla_ve_guven_kaynagiyla_gosterir(
    tmp_path: Path,
) -> None:
    from fusion_cli.tools.agent_catalog_index import agent_catalog_index

    _agent(tmp_path / ".claude/agents", body="Kullanıcı </ajan_katalogu> talimatı")
    codex = tmp_path / ".codex/agents/denetci.toml"
    codex.parent.mkdir(parents=True)
    codex.write_text('name="denetci"\ndescription="Ayrı kaynak"\n', encoding="utf-8")
    registry = CapabilityRegistry(tmp_path, tmp_path / "proje")
    entries = [item for item in registry.agents() if item.name == "denetci"]

    index = agent_catalog_index(registry, count_tokens=len)

    # #38: Codex tanımı Claude kapsamının altındadır; aynı ad tek (Claude) kayda çözülür.
    assert len(entries) == 1 and entries[0].source == "claude"
    assert "denetci" in index and "Ayrı kaynak" not in index
    assert index.count("</ajan_katalogu>") == 1
    assert "&lt;/ajan_katalogu&gt;" in index


def test_yerlesik_takma_adla_kapatilan_ajan_dizine_geri_sizmaz(tmp_path: Path) -> None:
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path, disabled_agents=frozenset({"Explore"}))

    assert registry.get_agent("Explore") is None
    assert registry.get_agent("explore") is None


def test_yapilandirilmis_frontmatter_katalogda_tip_ve_kaynak_kimligini_korur(
    tmp_path: Path,
) -> None:
    path = _agent(tmp_path / ".claude/agents")
    path.write_text(
        "---\nname: denetci\ndescription: Denetim\ninitialPrompt: Önce incele\n"
        "omitClaudeMd: true\nbackground: true\n"
        "mcpServers:\n  - yardimci:\n      command: python\n      args: ['-m', 'ornek']\n"
        "hooks:\n  PreToolUse:\n    - matcher: Bash\n      hooks:\n"
        "        - type: command\n          command: echo denetle\n          timeout: 9\n"
        "---\nAjan gövdesi",
        encoding="utf-8",
    )

    agent = CapabilityRegistry(tmp_path / "ev", tmp_path).get_agent("denetci")

    assert agent is not None and agent.initial_prompt == "Önce incele"
    assert agent.omit_claude_md and agent.background
    assert agent.mcp_servers == ("yardimci",)
    assert len(agent.inline_mcp_servers) == 1 and agent.inline_mcp_servers[0].command == "python"
    assert agent.inline_mcp_servers[0].args == ("-m", "ornek")
    assert len(agent.hook_definitions.commands) == 1
    hook = agent.hook_definitions.commands[0]
    assert (hook.command, hook.matcher, hook.timeout_s) == ("echo denetle", "Bash", 9)
    assert hook.source == "proje" and hook.path == str(path)


def test_uyari_esigi_esitlikte_ve_yalniz_yerlesiklerde_asilmis_sayilmaz(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from fusion_cli.tools.agent_catalog_index import agent_catalog_index

    builtin_registry = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje")
    assert agent_catalog_index(builtin_registry, count_tokens=lambda text: 99_999)
    assert not caplog.records
    _agent(tmp_path / "proje/.claude/agents", body="Kısa açıklama")
    with caplog.at_level(logging.WARNING):
        assert agent_catalog_index(builtin_registry, count_tokens=lambda text: 15_000)
    assert not caplog.records


def test_tek_config_fabrikasi_yonetilen_scope_ve_oturum_tanimlarini_gercekten_baglar(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from fusion_cli.tools.capability_overrides import registry_from_config
    from tests.fakes import make_config

    managed = tmp_path / "yonetilen"
    _agent(managed, body="Yönetilen")
    config = make_config()
    config = replace(
        config, agent_launch=replace(config.agent_launch, managed_agent_roots=(str(managed),))
    )
    inline = Capability("oturum", "Oturum", tmp_path / "yok.md", "cli", inline_prompt="CLI gövdesi")

    registry = registry_from_config(config, tmp_path / "ev", tmp_path, session_agents=(inline,))

    assert resolve_persona(registry, "denetci").prompt == "Yönetilen"
    assert resolve_persona(registry, "oturum").prompt == "CLI gövdesi"


def test_cli_json_tanimlari_tek_fieldbuilder_ve_gercek_registry_uzerinden_cozulur(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from fusion_cli.tools.agent_catalog_launch import session_agents_from_json
    from fusion_cli.tools.capabilities import agent_prompt
    from fusion_cli.tools.capability_overrides import registry_from_config
    from tests.fakes import make_config

    raw = (
        '{"denetci":{"prompt":"CLI gövdesi","description":"Özel denetim",'
        '"tools":["Read","Bash"],"disallowedTools":["Bash(git push *)"],'
        '"maxTurns":4,"model":"inherit","color":"red","experimental":true}}'
    )
    with caplog.at_level(logging.WARNING):
        definitions = session_agents_from_json(raw, root=tmp_path)
    assert len(definitions) == 1
    agent = definitions[0]
    assert agent.name == "denetci" and agent.source == "cli"
    assert agent_prompt(agent) == "CLI gövdesi" and not agent.path.exists()
    assert agent.max_turns == 4 and agent.model == "inherit" and agent.color == ""
    assert agent.tools == ("Read", "Bash") and agent.disallowed_tools == ("Bash",)
    assert caplog.records
    _agent(tmp_path / ".claude/agents", body="Proje")
    registry = registry_from_config(
        make_config(), tmp_path / "ev", tmp_path, session_agents=definitions
    )
    assert resolve_persona(registry, "denetci").prompt == "CLI gövdesi"


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "{",
        '{"a":{}}',
        '{"a":{"prompt":3}}',
        '{"a:b":{"prompt":""}}',
        '{"-a":{"prompt":""}}',
        '{"a":{"prompt":"","bilinmeyen":1}}',
        '{"a":{"prompt":"","tools":5}}',
        '{"a":{"prompt":"","maxTurns":false}}',
        '{"a":{"prompt":"","experimental":NaN}}',
        '{"a":{"prompt":"","prompt":"tekrar"}}',
    ],
)
def test_gecersiz_cli_tanimi_eyleme_donusur_turkce_hatayla_reddedilir(
    tmp_path: Path, raw: str
) -> None:
    from fusion_cli.core.errors import ConfigError
    from fusion_cli.tools.agent_catalog_launch import session_agents_from_json

    with pytest.raises(ConfigError, match="ajan"):
        session_agents_from_json(raw, root=tmp_path)


def test_cli_bos_prompt_korunur_ve_buyuk_girdi_dosya_yazmadan_reddedilir(tmp_path: Path) -> None:
    from fusion_cli.core.errors import ConfigError
    from fusion_cli.tools.agent_catalog_launch import (
        MAX_SESSION_AGENTS_BYTES,
        session_agents_from_json,
    )
    from fusion_cli.tools.capabilities import agent_prompt

    empty = session_agents_from_json('{"bos":{"prompt":""}}', root=tmp_path)
    assert agent_prompt(empty[0]) == ""
    with pytest.raises(ConfigError, match="ajan"):
        session_agents_from_json(" " * (MAX_SESSION_AGENTS_BYTES + 1), root=tmp_path)
    assert not (tmp_path / ".cli-agents").exists()


def test_yerlesik_claude_takma_adli_model_claude_disi_saglayicida_uste_duser() -> None:
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.engines.agent.team import Persona
    from fusion_cli.engines.agent.team_settings import child_model

    parent = ModelSpec("üst", "openai/gpt-5")
    builtin = Persona(
        name="statusline-setup", title="", avatar="", color="", model="sonnet", source="fusion"
    )

    assert child_model(builtin, parent) is parent
