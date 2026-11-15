"""Ajan kapsam önceliği ve frontmatter yasağının üretim yolundaki karşılığı."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.team import resolve_persona, spawn_agent_tool
from fusion_cli.tools.capabilities import CapabilityRegistry
from fusion_cli.tools.permission_match import evaluate
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


def _agent(folder: Path, *, body: str, settings: str = "", name: str = "denetci") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    path.write_text(
        f"---\nname: {name}\ndescription: Denetim\n{settings}---\n{body}", encoding="utf-8"
    )
    return path


@pytest.mark.parametrize("is_identical", [False, True])
def test_proje_ajani_kullanici_ajanini_icerikten_bagimsiz_golgeler(
    tmp_path: Path, is_identical: bool
) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    _agent(home / ".claude/agents", body="Proje talimatı" if is_identical else "Kullanıcı")
    project = _agent(root / ".claude/agents", body="Proje talimatı")
    registry = CapabilityRegistry(home, root)

    selected = registry.get_agent("denetci")

    assert selected is not None and selected.path == project
    assert selected.source == "proje"
    assert registry.get_agent(selected.qualified_name) == selected
    assert [item for item in registry.agents() if item.name == "denetci"] == [selected]
    assert resolve_persona(registry, "denetci").prompt == "Proje talimatı"


def test_ek_kok_ajani_kullanici_kapsamindan_once_gelir(tmp_path: Path) -> None:
    home, root, extra = tmp_path / "ev", tmp_path / "proje", tmp_path / "ek"
    _agent(home / ".claude/agents", body="Kullanıcı")
    chosen = _agent(extra / ".claude/agents", body="Ek proje")
    registry = CapabilityRegistry(home, root, extra_roots=(extra,))

    selected = registry.get_agent("denetci")

    assert selected is not None and selected.path == chosen
    assert selected.source == "ek-kok"


def test_beceri_farkli_kaynaklari_ajan_golgelemesinden_etkilenmez(tmp_path: Path) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    for folder, body in (
        (home / ".claude/skills/denetim", "Kullanıcı"),
        (root / ".claude/skills/denetim", "Proje"),
    ):
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            f"---\nname: denetim\ndescription: Denetim\n---\n{body}", encoding="utf-8"
        )
    registry = CapabilityRegistry(home, root)

    candidates = registry.candidates("denetim")

    assert len(candidates) == 2
    assert registry.get_skill("denetim") is None
    assert {registry.get_skill(name).source for name in candidates} == {"claude", "proje"}


@pytest.mark.parametrize("tools", ["", "tools: Read, Bash, Edit\n"])
async def test_frontmatter_belirtecli_yasak_gercek_alt_ajan_arac_kumesinden_aileyi_cikarir(
    tmp_path: Path, tools: str
) -> None:
    _agent(
        tmp_path / ".claude/agents",
        body="Özel denetçi",
        settings=tools + "disallowedTools: Bash(git push *), Edit(src/**)\n",
    )
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path)
    deps = AgentDeps(
        config=make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        capabilities=registry,
    )
    observed: list[set[str] | None] = []

    async def run_child(task: str, child: AgentDeps, **kwargs: object) -> SimpleNamespace:
        allowed = kwargs["allowed_tools"]
        assert isinstance(allowed, set) or allowed is None
        observed.append(allowed)
        return SimpleNamespace(final_text="Denetlendi", ok=True, tool_calls_made=0)

    result = await spawn_agent_tool(deps, depth=0, run_agent=run_child).run(
        {"task": "incele", "uzman": "denetci"}, deps.tool_context
    )

    assert result.ok and "Denetlendi" in result.output
    assert len(observed) == 1 and observed[0] is not None
    assert "read_file" in observed[0]
    assert not {"run_shell", "edit_file", "multi_edit"} & observed[0]
    persona = resolve_persona(registry, "denetci")
    assert persona.disallowed_tools == frozenset({"run_shell", "edit_file", "multi_edit"})


def test_ayni_belirtec_cli_izin_kuralinda_komut_kapsamini_korur(tmp_path: Path) -> None:
    rule = parse_rule("Bash(git push *)", PermissionDecision.DENY, source="cli")
    assert rule is not None
    rules = PermissionRuleSet(rules=(rule,))

    blocked = evaluate(rules, "run_shell", {"command": "git push origin main"}, tmp_path)

    assert blocked is not None and blocked.decision is PermissionDecision.DENY
    assert evaluate(rules, "run_shell", {"command": "git status"}, tmp_path) is None
    assert evaluate(rules, "run_shell", {"command": "git log -1"}, tmp_path) is None
