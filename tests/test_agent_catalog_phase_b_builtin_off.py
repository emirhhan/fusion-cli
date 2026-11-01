"""CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS yalnız yerleşik Explore/Plan'ı kaldırır (#33)."""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.config.agent_launch_compat import read_agent_launch
from fusion_cli.config.agent_launch_settings import AgentLaunchConfig
from fusion_cli.tools.capability_overrides import registry_from_config
from tests.fakes import make_config


def test_ortam_degiskeni_tipli_yapilandirmaya_alinir(tmp_path):
    loaded = read_agent_launch(
        AgentLaunchConfig(),
        home=tmp_path / "ev",
        root=tmp_path,
        environ={"CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS": "1"},
    )
    assert loaded.disable_explore_plan_agents is True
    assert AgentLaunchConfig().disable_explore_plan_agents is False


def test_yerlesik_explore_plan_kalkar_ozel_tanim_ve_digerleri_kalir(tmp_path):
    folder = tmp_path / ".claude" / "agents"
    folder.mkdir(parents=True)
    (folder / "explore.md").write_text(
        "---\nname: Explore\ndescription: özel keşif\nmodel: haiku\n---\nAra.", encoding="utf-8"
    )
    config = make_config(memory_dir=tmp_path / "bellek")
    config = replace(
        config, agent_launch=replace(config.agent_launch, disable_explore_plan_agents=True)
    )
    registry = registry_from_config(config, tmp_path / "ev", tmp_path)

    explore = registry.get_agent("Explore")
    assert explore is not None and explore.source != "fusion"
    assert registry.get_agent("Plan") is None and registry.get_agent("plan") is None
    assert registry.get_agent("general-purpose") is not None


def test_sdk_ortam_degiskeni_etkilesimsiz_kipte_tum_yerlesikleri_kaldirir(tmp_path):
    loaded = read_agent_launch(
        AgentLaunchConfig(),
        home=tmp_path / "ev",
        root=tmp_path,
        environ={"CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1"},
    )
    assert loaded.disable_builtin_agents is True
    config = replace(make_config(memory_dir=tmp_path / "bellek"), agent_launch=loaded)
    folder = tmp_path / ".claude" / "agents"
    folder.mkdir(parents=True)
    (folder / "denetci.md").write_text(
        "---\nname: denetci\ndescription: inceler\n---\nİncele.", encoding="utf-8"
    )

    headless = registry_from_config(config, tmp_path / "ev", tmp_path, headless=True)
    interactive = registry_from_config(config, tmp_path / "ev", tmp_path)

    assert {item.source for item in headless.agents()} == {"proje"} or all(
        item.source != "fusion" for item in headless.agents()
    )
    assert headless.get_agent("denetci") is not None
    assert headless.get_agent("general-purpose") is None
    # Claude Code'da etkileşimli oturum bu değişkeni okumaz.
    assert interactive.get_agent("general-purpose") is not None


def test_claude_agent_ayari_uyari_basmadan_okunur(tmp_path, caplog):
    import json
    import logging

    settings = tmp_path / "ev" / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"agent": "denetci"}), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        loaded = read_agent_launch(
            AgentLaunchConfig(), home=tmp_path / "ev", root=tmp_path, environ={}
        )

    assert loaded.default_agent == "denetci"
    assert "geriye uyumluluk" not in caplog.text
