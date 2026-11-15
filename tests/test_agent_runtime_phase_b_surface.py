"""Modele tek alt ajan aracı (Agent) sunulur; eski adlar gizli ama çağrılabilir (#8)."""

from __future__ import annotations

from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.tools.agent_catalog_index import agent_catalog_index
from fusion_cli.tools.capabilities import CapabilityRegistry

from .test_system_prompt_layers import _deps

_LEGACY = ("Task", "spawn_agent", "spawn_agents", "invoke_subagent")


def test_modele_yalniz_agent_sunulur_eski_adlar_gizli_kalir(tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    registry = build_agent_registry(deps, depth=0, run_agent=loop.run_agent)

    advertised = set(registry.advertised_names())
    schemas = {schema["function"]["name"] for schema in registry.schemas()}  # type: ignore[index]

    assert {"Agent", "SendMessage"} <= advertised
    assert not advertised & set(_LEGACY)
    assert not schemas & set(_LEGACY)
    for name in _LEGACY:
        assert registry.get(name) is not None, name


def test_agent_aciklamasi_ve_katalog_eski_araclari_ogretmez(tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    agent = build_agent_registry(deps, depth=0, run_agent=loop.run_agent).get("Agent")
    index = agent_catalog_index(CapabilityRegistry(tmp_path / "ev", tmp_path), count_tokens=len)

    assert agent is not None
    assert "spawn_agent" not in agent.description
    assert "Agent" in index and "spawn_agent" not in index and "invoke_agent" not in index


def test_agent_semasi_yalniz_claude_parametrelerini_ve_effort_tasir(tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    agent = build_agent_registry(deps, depth=0, run_agent=loop.run_agent).get("Agent")

    assert agent is not None
    properties = set(agent.parameters["properties"])  # type: ignore[index]
    assert properties == {
        "description",
        "prompt",
        "subagent_type",
        "model",
        "name",
        "isolation",
        "effort",
        "run_in_background",
    }
    assert agent.parameters["required"] == ["prompt"]  # type: ignore[index]


def test_agent_effort_cagrisi_tanimdaki_eforu_ezer():
    from fusion_cli.engines.agent.team import _parse_subtask

    task = _parse_subtask({"prompt": "Ara", "effort": "high", "salt_okunur": True})

    assert not isinstance(task, str)
    assert task.effort == "high"
    # Eski Türkçe alanlar şemada yok ama gelen çağrıda okunmaya devam eder.
    assert task.read_only is True


def test_alt_ajandan_claude_listesindeki_araclar_alinir(tmp_path):
    """Claude Code: AskUserQuestion, ScheduleWakeup, Workflow her alt ajandan; Agent derinlik
    sınırında alınır (#28)."""
    from dataclasses import replace

    from fusion_cli.engines.agent.team import max_agent_depth

    class _Asker:
        async def ask(self, question: str) -> str:
            return ""

    deps = replace(_deps(tmp_path, "nvidia_nim/ornek-model"), asker=_Asker())
    main = {tool.name for tool in build_agent_registry(deps, depth=0, run_agent=loop.run_agent)}
    child = {tool.name for tool in build_agent_registry(deps, depth=1, run_agent=loop.run_agent)}
    deepest = {
        tool.name
        for tool in build_agent_registry(
            deps, depth=max_agent_depth(deps), run_agent=loop.run_agent
        )
    }

    assert {"ask_user", "workflow_run"} <= main
    assert not child & {"ask_user", "schedule_wakeup", "workflow_run"}
    assert "Agent" in child
    assert not deepest & {"Agent", "Task", "spawn_agent", "spawn_agents", "invoke_subagent"}
