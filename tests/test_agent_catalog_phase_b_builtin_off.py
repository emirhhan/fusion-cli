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
