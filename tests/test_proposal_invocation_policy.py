"""Kurulu öneri her çağrıda kaynak ve parametre kapısından geçer."""

from __future__ import annotations

import pytest

from fusion_cli.core.memory import RoutineSpec
from fusion_cli.core.proposal_invocation import ProposalInvocation, body_revision, metadata_line
from fusion_cli.tools.capabilities import _to_capability
from fusion_cli.tools.skill_commands import TemplateEnv, build_invocation
from tests.test_skill_proposal_cli import proposal_workspace as _proposal_workspace

proposal_workspace = _proposal_workspace


def test_oneri_varsayilan_politikada_calistirilmaz(tmp_path):
    raw = "---\nname: rutin\n---\n$ARGUMENTS\n"
    metadata = ProposalInvocation(
        "id",
        "development",
        RoutineSpec("rutin", "iş", '{"type":"object"}', ("a",), ("b",), "hash"),
        body_revision(raw),
    )
    path = tmp_path / "SKILL.md"
    path.write_text(raw.replace("---\n", "---\n" + metadata_line(metadata) + "\n", 1))
    skill = _to_capability(path, "kurulu", fallback="rutin")
    result = build_invocation(skill, "{}", TemplateEnv(tmp_path, tmp_path), shell_allowed=True)
    assert getattr(result, "ok", True) is False
    assert result.task == ""


@pytest.mark.parametrize("mutation", ["arguments", "precondition", "revision", "source", "shell"])
def test_public_cagri_gecersiz_kaynakta_bekleyen_gorev_acmaz(
    proposal_workspace, monkeypatch, mutation
):
    import json
    from dataclasses import replace
    from pathlib import Path

    from fusion_cli.cli.repl.skill_commands import skill_handler
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.config.paths import memory_dir
    from fusion_cli.core.proposal_invocation import ProposalPolicy
    from fusion_cli.memory.checkpoint_store import JsonCheckpointStore
    from fusion_cli.tools.capabilities import CapabilityRegistry
    from tests.fakes import make_config
    from tests.test_verified_skill_public_flow import CASES, apply_proposal, seed_plan

    proposal, arguments = seed_plan(proposal_workspace, CASES[2])
    assert apply_proposal(proposal, arguments).exit_code == 0
    library = CapabilityRegistry(
        Path.home(), proposal_workspace, proposal_policy=ProposalPolicy(True)
    )
    skill = library.get_skill(proposal.routine.routine_id)
    assert skill is not None
    if mutation == "arguments":
        arguments = {"baslik": False}
    elif mutation == "precondition":
        (proposal_workspace / "girdi.txt").write_text("uygun değil")
    elif mutation == "revision":
        skill.path.write_text(skill.path.read_text() + "Başka bir yönerge.\n")
    elif mutation == "shell":
        arguments = {"baslik": "!`echo yasak`"}
    else:
        store = JsonCheckpointStore(memory_dir() / "workflow-checkpoints")
        saved = store.load(proposal.routine.routine_id)
        changed = replace(saved.plan.steps[0], goal="değiştirilmiş kaynak")
        store.save(replace(saved, plan=replace(saved.plan, steps=(changed,))))
    config = make_config(memory_dir=memory_dir(), runtime={"verified_skill_proposals": True})
    state = ReplState(
        config=config, memory=None, root=proposal_workspace, home=Path.home(), capabilities=library
    )
    monkeypatch.setattr(
        "fusion_cli.tools.skill_commands.expand_shell_context",
        lambda *args, **kwargs: pytest.fail("Öneri için dinamik shell çalışamaz"),
    )
    text = skill_handler(skill.qualified_name)(state, json.dumps(arguments))
    assert text
    assert state.pending_task == "" and state.pending_context == ""


def test_kurulu_gelistirme_onerisi_ayni_kokte_blind_gorunumune_girmez(proposal_workspace):
    from pathlib import Path

    from fusion_cli.cli.repl.skill_commands import skill_slash_commands
    from fusion_cli.core.proposal_invocation import ProposalPolicy
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.engine_tools import _find_skill_tool, _read_skill_tool
    from fusion_cli.tools.capabilities import CapabilityRegistry
    from tests.test_verified_skill_public_flow import apply_proposal, seed_plan

    proposal, arguments = seed_plan(proposal_workspace)
    assert apply_proposal(proposal, arguments).exit_code == 0
    name = proposal.routine.routine_id
    original = CapabilityRegistry(
        Path.home(), proposal_workspace, proposal_policy=ProposalPolicy(True)
    )
    assert original.get_skill(name) is not None
    blind = original.with_proposal_policy(ProposalPolicy(True, "blind"))
    for library in (blind, blind.with_extra_roots((proposal_workspace,))):
        library.add_nested_roots((proposal_workspace,))
        assert library.get_skill(name) is None and library.candidates(name) == ()
        assert not skill_slash_commands(library)
        context = ToolContext(root=proposal_workspace)
        assert name not in _find_skill_tool(library).run({"query": name}, context).output
        assert not _read_skill_tool(library).run({"name": name}, context).ok
