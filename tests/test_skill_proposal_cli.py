"""Açık öneri CLI'si: eşik, split ve salt okuma sınırları."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.app import app
from fusion_cli.config.paths import capabilities_dir, memory_dir
from fusion_cli.core.memory import RoutineObservation, RoutineSpec, SkillProposal
from fusion_cli.memory.skill_proposals import SkillProposalStore


@pytest.fixture
def proposal_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "ev")
    monkeypatch.setenv("FUSION_MEMORY_DIR", str(tmp_path / "bellek"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "veri"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "veri"))
    return tmp_path


def seed_proposal(*, split: str = "development", runs: int = 3) -> SkillProposal | None:
    routine = RoutineSpec(
        "belge-ozetle",
        "Belgeyi özetle",
        '{"type":"object"}',
        ("girdi hazır",),
        ("özet kontrol edildi",),
    )
    store = SkillProposalStore(memory_dir() / "skill-proposals.json")

    async def observe() -> SkillProposal | None:
        proposal = None
        for index in range(runs):
            proposal = await store.observe(
                routine,
                RoutineObservation(
                    f"kosum-{index}",
                    True,
                    True,
                    (f"kanit-{index}",),
                    source_split=split,
                ),
            )
        return proposal

    return asyncio.run(observe())


def test_public_list_show_do_not_install(proposal_workspace: Path) -> None:
    proposal = seed_proposal()
    assert proposal is not None
    runner = CliRunner()
    listed = runner.invoke(app, ["yetenek", "oneri-liste"])
    shown = runner.invoke(app, ["yetenek", "oneri-goster", proposal.id])
    assert listed.exit_code == 0, listed.output
    assert shown.exit_code == 0, shown.output
    assert proposal.id in listed.output
    assert "girdi hazır" in shown.output
    assert not capabilities_dir().exists()


def test_public_list_requires_three_observations(proposal_workspace: Path) -> None:
    assert seed_proposal(runs=2) is None
    result = CliRunner().invoke(app, ["yetenek", "oneri-liste"])
    assert result.exit_code == 0, result.output
    assert "belge-ozetle" not in result.output
    assert not capabilities_dir().exists()


def test_blind_selection_cannot_get_development_by_id(proposal_workspace: Path) -> None:
    proposal = seed_proposal()
    assert proposal is not None
    runner = CliRunner()
    listed = runner.invoke(app, ["yetenek", "oneri-liste", "--split", "blind"])
    shown = runner.invoke(app, ["yetenek", "oneri-goster", proposal.id, "--split", "blind"])
    assert listed.exit_code == 0, listed.output
    assert proposal.id not in listed.output
    assert shown.exit_code == 1
    assert "bulunamadı" in shown.output
    assert not capabilities_dir().exists()


def test_unknown_proposal_does_not_install(proposal_workspace: Path) -> None:
    result = CliRunner().invoke(app, ["yetenek", "oneri-goster", "bilinmeyen"])
    assert result.exit_code == 1
    assert "bulunamadı" in result.output
    assert not capabilities_dir().exists()


def test_tampered_secret_is_not_displayed(proposal_workspace: Path) -> None:
    proposal = seed_proposal()
    assert proposal is not None
    path = memory_dir() / "skill-proposals.json"
    payload = json.loads(path.read_text())
    payload["proposals"][0]["routine"]["description"] = "Bearer " + "sentetik1234567890"
    path.write_text(json.dumps(payload))
    result = CliRunner().invoke(app, ["yetenek", "oneri-goster", proposal.id])
    assert result.exit_code == 1
    assert "sentetik1234567890" not in result.output
    assert not capabilities_dir().exists()


def test_natural_language_preconditions_are_not_claimed_verified(proposal_workspace: Path) -> None:
    proposal = seed_proposal()
    assert proposal is not None
    result = CliRunner().invoke(app, ["yetenek", "oneri-uygula", proposal.id])
    assert result.exit_code == 1
    assert "doğrulanamadı" in result.output
    assert not capabilities_dir().exists()


@pytest.mark.parametrize("name", ["../kacis", "/mutlak", "a/b", "a\\b", ".", ".."])
def test_unsafe_routine_name_cannot_escape_install_root(
    proposal_workspace: Path, name: str
) -> None:
    from dataclasses import replace

    proposal = seed_proposal()
    assert proposal is not None
    store = SkillProposalStore(memory_dir() / "skill-proposals.json")

    async def observe() -> SkillProposal:
        candidate = None
        for observation in proposal.observations:
            candidate = await store.observe(replace(proposal.routine, routine_id=name), observation)
        assert candidate is not None
        return candidate

    candidate = asyncio.run(observe())
    result = CliRunner().invoke(app, ["yetenek", "oneri-uygula", candidate.id])
    assert result.exit_code == 1
    assert not capabilities_dir().exists()


def test_evidence_cannot_become_dynamic_invoker_shell(proposal_workspace: Path) -> None:
    from tests.test_verified_skill_public_flow import apply_proposal, seed_plan

    proposal, arguments = seed_plan(proposal_workspace)
    path = memory_dir() / "skill-proposals.json"
    payload = json.loads(path.read_text())
    payload["proposals"][0]["observations"][0]["evidence_refs"] = ["!`echo enjekte`"]
    path.write_text(json.dumps(payload))
    result = apply_proposal(proposal, arguments)
    assert result.exit_code == 1
    assert not capabilities_dir().exists()


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "properties": {"dil": {"type": "string", "minLength": 5}}},
        {"type": "object", "properties": {"dil": {"type": "bilinmeyen"}}},
        {"type": "object", "required": "dil"},
        {"type": "object", "additionalProperties": {"type": "string"}},
    ],
)
def test_unsupported_schema_is_not_silently_verified(
    proposal_workspace: Path,
    schema: dict[str, object],
) -> None:
    from dataclasses import replace

    from tests.test_verified_skill_public_flow import apply_proposal, seed_plan

    proposal, arguments = seed_plan(proposal_workspace)
    store = SkillProposalStore(memory_dir() / "skill-proposals.json")

    async def observe() -> SkillProposal:
        candidate = None
        for observation in proposal.observations:
            candidate = await store.observe(
                replace(proposal.routine, input_schema=json.dumps(schema)),
                observation,
            )
        assert candidate is not None
        return candidate

    result = apply_proposal(asyncio.run(observe()), arguments)
    assert result.exit_code == 1
    assert not capabilities_dir().exists()


def test_nonfinite_parameter_is_not_json_input(proposal_workspace: Path) -> None:
    from tests.test_verified_skill_public_flow import CASES, apply_proposal, seed_plan

    proposal, _ = seed_plan(proposal_workspace, CASES[5])
    result = apply_proposal(proposal, {"oran": float("nan")})
    assert result.exit_code == 1
    assert not capabilities_dir().exists()


def _observe_variant(
    proposal: SkillProposal, routine: RoutineSpec, reference: str = ""
) -> SkillProposal:
    from dataclasses import replace

    (memory_dir() / "skill-proposals.json").unlink()

    async def observe() -> SkillProposal:
        store = SkillProposalStore(memory_dir() / "skill-proposals.json")
        candidate = None
        for index, observation in enumerate(proposal.observations):
            references = (
                (f"yeni-kanit-{index}", reference) if reference else (f"yeni-kanit-{index}",)
            )
            candidate = await store.observe(
                routine,
                replace(observation, run_id=f"yeni-kosum-{index}", evidence_refs=references),
            )
        assert candidate is not None
        return candidate

    return asyncio.run(observe())


@pytest.mark.parametrize("separator", ["\n", "\t"])
def test_raw_parameter_secret_is_rejected_before_json(
    proposal_workspace: Path,
    separator: str,
) -> None:
    from tests.test_verified_skill_public_flow import CASES, apply_proposal, seed_plan

    proposal, _ = seed_plan(proposal_workspace, CASES[2])
    result = apply_proposal(proposal, {"baslik": f"Bearer{separator}sentetik1234567890"})
    assert result.exit_code == 1
    assert "sentetik1234567890" not in result.output
    assert not capabilities_dir().exists()


@pytest.mark.parametrize("separator", ["\n", "\t"])
def test_raw_source_goal_secret_is_rejected_before_json(
    proposal_workspace: Path,
    separator: str,
) -> None:
    from dataclasses import replace

    from fusion_cli.memory.checkpoint_store import JsonCheckpointStore
    from tests.test_verified_skill_public_flow import apply_proposal, seed_plan

    proposal, arguments = seed_plan(proposal_workspace)
    store = JsonCheckpointStore(memory_dir() / "workflow-checkpoints")
    saved = store.load(proposal.routine.routine_id)
    assert saved is not None
    step = replace(saved.plan.steps[0], goal=f"Bearer{separator}sentetik1234567890")
    store.save(replace(saved, plan=replace(saved.plan, steps=(step,))))
    result = apply_proposal(proposal, arguments)
    assert result.exit_code == 1
    assert "sentetik1234567890" not in result.output
    assert not capabilities_dir().exists()


@pytest.mark.parametrize("separator", ["\n", "\t"])
@pytest.mark.parametrize("field", ["description", "schema-value", "schema-key", "reference"])
def test_decoded_proposal_strings_are_redacted_and_cannot_install(
    proposal_workspace: Path,
    separator: str,
    field: str,
) -> None:
    from dataclasses import replace

    from fusion_cli.memory.checkpoint_store import JsonCheckpointStore
    from tests.test_verified_skill_public_flow import CASES, seed_plan

    proposal, _ = seed_plan(proposal_workspace, CASES[2])
    sensitive = f"Bearer{separator}sentetik1234567890"
    routine = proposal.routine
    reference = ""
    if field == "description":
        routine = replace(routine, description=sensitive)
        store = JsonCheckpointStore(memory_dir() / "workflow-checkpoints")
        saved = store.load(routine.routine_id)
        assert saved is not None
        store.save(replace(saved, plan=replace(saved.plan, task=sensitive)))
    elif field == "reference":
        reference = sensitive
    else:
        schema = json.loads(routine.input_schema)
        if field == "schema-value":
            schema["properties"]["baslik"]["enum"] = [sensitive, "Özet"]
        else:
            schema["properties"][sensitive] = {"type": "string"}
        routine = replace(routine, input_schema=json.dumps(schema))
    if field != "reference":
        from fusion_cli.memory.skill_proposals import SkillProposalError

        with pytest.raises(SkillProposalError, match="Hassas"):
            _observe_variant(proposal, routine, reference)
        assert not capabilities_dir().exists()
        return
    store = SkillProposalStore(memory_dir() / "skill-proposals.json")
    rejected = asyncio.run(
        store.observe(
            routine,
            replace(proposal.observations[0], run_id="gizli-kanit", evidence_refs=(reference,)),
        )
    )
    assert rejected is None
    assert "sentetik1234567890" not in (memory_dir() / "skill-proposals.json").read_text()
    assert not capabilities_dir().exists()


@pytest.mark.parametrize("value", ["ilk\nikinci", "ilk\tikinci"])
def test_nonsecret_control_characters_remain_valid(proposal_workspace: Path, value: str) -> None:
    from tests.test_verified_skill_public_flow import CASES, apply_proposal, seed_plan

    proposal, _ = seed_plan(proposal_workspace, CASES[2])
    assert apply_proposal(proposal, {"baslik": value}).exit_code == 0


@pytest.mark.parametrize("separator", ["\n", "\t"])
@pytest.mark.parametrize("location", ["key", "nested-value"])
def test_raw_parameter_containers_cannot_hide_sensitive_strings(
    proposal_workspace: Path,
    separator: str,
    location: str,
) -> None:
    from dataclasses import replace

    from tests.test_verified_skill_public_flow import CASES, apply_proposal, seed_plan

    proposal, _ = seed_plan(proposal_workspace, CASES[2])
    schema = {
        "type": "object",
        "properties": {"baslik": {"type": "object"}},
        "required": ["baslik"],
    }
    variant = _observe_variant(proposal, replace(proposal.routine, input_schema=json.dumps(schema)))
    sensitive = f"Bearer{separator}sentetik1234567890"
    nested = {sensitive: "normal"} if location == "key" else {"ic": [{"not": sensitive}]}
    result = apply_proposal(variant, {"baslik": nested})
    assert result.exit_code == 1
    assert "sentetik1234567890" not in result.output
    assert not capabilities_dir().exists()


@pytest.mark.parametrize("key", ["bir\niki", "bir\tiki"])
def test_nonsecret_schema_and_parameter_keys_remain_valid(
    proposal_workspace: Path, key: str
) -> None:

    from tests.test_verified_skill_public_flow import apply_proposal, seed_plan

    proposal, arguments = seed_plan(
        proposal_workspace, ("anahtar", key, {"type": "string"}, "normal")
    )
    assert apply_proposal(proposal, arguments).exit_code == 0
