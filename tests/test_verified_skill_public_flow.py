"""Altı kayıtlı plan: public CLI'den gerçek beceri keşfi ve çağrısına."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from fusion_cli.cli.app import app
from fusion_cli.config.paths import capabilities_dir, memory_dir
from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStep,
    RetrySafety,
    RoutineDefinition,
    StepStatus,
    VerificationCheck,
    VerificationCheckKind,
)
from fusion_cli.core.memory import SkillProposal
from fusion_cli.core.proposal_invocation import ProposalPolicy
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.engine_tools import _find_skill_tool, _read_skill_tool
from fusion_cli.engines.agent.routine_invocation import RoutineInvocationValidator
from fusion_cli.memory.checkpoint_store import JsonCheckpointStore
from fusion_cli.memory.skill_proposals import SkillProposalStore
from fusion_cli.tools.capabilities import CapabilityRegistry
from fusion_cli.tools.skill_commands import TemplateEnv, build_invocation
from tests.test_skill_proposal_cli import proposal_workspace as _workspace_fixture

proposal_workspace = _workspace_fixture

CASES = (
    ("belge-ozetle", "dil", {"type": "string", "enum": ["tr", "en"]}, "tr"),
    ("satir-sec", "sinir", {"type": "integer", "minimum": 1}, 5),
    ("baslik-duzenle", "baslik", {"type": "string"}, "Özet"),
    ("etiket-sec", "etiketler", {"type": "array", "items": {"type": "string"}}, ["belge"]),
    ("rapor-hazirla", "ayrintili", {"type": "boolean"}, True),
    ("puan-hesapla", "oran", {"type": "number", "maximum": 1}, 0.5),
)


def seed_plan(root: Path, case: tuple = CASES[0]) -> tuple[SkillProposal, dict[str, object]]:
    name, parameter, parameter_schema, value = case
    description = f"{name} rutinini verilen parametrelerle uygula."
    checks = (
        VerificationCheck("girdi-var", VerificationCheckKind.FILE_EXISTS, "girdi.txt"),
        VerificationCheck("girdi-hazir", VerificationCheckKind.FILE_CONTAINS, "girdi.txt", "hazır"),
        VerificationCheck("sonuc", VerificationCheckKind.FILE_CONTAINS, "girdi.txt", "hazır"),
    )
    step = PlanStep(
        "adim",
        description,
        (),
        (),
        ("files",),
        ("girdi-var", "girdi-hazir", "sonuc"),
        "",
        RetrySafety.SAFE,
        status=StepStatus.COMPLETED,
        verification_checks=checks,
    )
    schema = {
        "type": "object",
        "properties": {parameter: parameter_schema},
        "required": [parameter],
        "additionalProperties": False,
    }
    plan = ExecutionPlan(
        name,
        description,
        (replace(step, status=StepStatus.PENDING),),
        routine=RoutineDefinition(json.dumps(schema), ("girdi-var", "girdi-hazir"), ("sonuc",)),
    )
    (root / "girdi.txt").write_text("hazır", encoding="utf-8")

    async def execute() -> SkillProposal:
        from fusion_cli.core.lesson_runtime import LessonRuntimeContext
        from fusion_cli.core.memory import LessonRecallPolicy
        from fusion_cli.engines.agent.learning_steps import finish_learning
        from fusion_cli.engines.agent.lesson_attribution import LessonTurnState
        from fusion_cli.engines.agent.loop import AgentOutcome
        from fusion_cli.engines.agent.plan_runner import run_execution_plan
        from tests.test_agent_lessons import _deps

        store = SkillProposalStore(memory_dir() / "skill-proposals.json")
        checkpoint_store = JsonCheckpointStore(memory_dir() / "workflow-checkpoints")
        for index in range(3):
            deps = _deps(root)
            deps.config = replace(
                deps.config,
                memory_dir=memory_dir(),
                runtime=replace(deps.config.runtime, verified_skill_proposals=True),
            )
            deps.attempt_id = f"{name}-{index}"
            deps.conversation_id = f"konusma-{index}"
            deps.lesson_context = LessonRuntimeContext(
                LessonRecallPolicy(source_split="development")
            )
            deps.lesson_state = LessonTurnState()
            deps.skill_proposals = store
            deps.checkpoint_store = JsonCheckpointStore(memory_dir() / f"koşum-{index}")

            async def agent(task, child, index=index, **kwargs):
                result = await child.base_registry.execute(
                    "read_file", {"path": "girdi.txt"}, child.tool_context
                )
                assert result.ok
                written = await child.base_registry.execute(
                    "write_file",
                    {"path": "girdi.txt", "content": f"hazır {index}"},
                    child.tool_context,
                )
                assert written.ok
                return AgentOutcome(
                    "tamam",
                    [],
                    tool_calls_made=2,
                    mutating_tool_calls_made=1,
                    tool_uses=(
                        ToolUse(
                            "write_file",
                            True,
                            True,
                            {"path": "girdi.txt"},
                            written.output,
                            call_id=f"yaz-{name}-{index}",
                        ),
                    ),
                )

            outcome = await run_execution_plan(
                description, deps, agent, plan=plan, self_review=False
            )
            assert outcome.ok, outcome.final_text
            await finish_learning(outcome, deps, plan_mode=False)
        proposal = (await store.list())[0]
        completed = deps.checkpoint_store.load(plan.plan_id)
        assert completed is not None
        checkpoint_store.save(replace(completed, storage_revision=0))
        return proposal

    return asyncio.run(execute()), {parameter: value}


def apply_proposal(proposal: SkillProposal, arguments: dict[str, object]) -> Result:
    return CliRunner().invoke(
        app, ["yetenek", "oneri-uygula", proposal.id, "--parametreler", json.dumps(arguments)]
    )


@pytest.mark.parametrize("case", CASES, ids=[item[0] for item in CASES])
def test_six_public_routines_reach_find_read_and_invoker(
    proposal_workspace: Path, case: tuple, monkeypatch
) -> None:
    proposal, arguments = seed_plan(proposal_workspace, case)
    runner = CliRunner()
    assert runner.invoke(app, ["yetenek", "oneri-liste"]).exit_code == 0
    assert runner.invoke(app, ["yetenek", "oneri-goster", proposal.id]).exit_code == 0
    assert not capabilities_dir().exists()
    result = apply_proposal(proposal, arguments)
    assert result.exit_code == 0, result.output
    registry = CapabilityRegistry(
        Path.home(), proposal_workspace, proposal_policy=ProposalPolicy(True)
    )
    name = proposal.routine.routine_id
    context = ToolContext(root=proposal_workspace)
    found = _find_skill_tool(registry).run({"query": name}, context)
    assert name in found.output
    read = _read_skill_tool(registry).run({"name": name}, context)
    assert name in read.output and "girdi.txt" in read.output
    skill = registry.get_skill(name)
    assert skill is not None
    argument = json.dumps(arguments, ensure_ascii=False)
    invocation = build_invocation(
        skill,
        argument,
        TemplateEnv(skill.path.parent, proposal_workspace),
        shell_allowed=True,
        proposal_policy=ProposalPolicy(True),
        proposal_validator=RoutineInvocationValidator(memory_dir(), ProposalPolicy(True)),
    )
    assert invocation.task == argument
    assert json.loads(invocation.context.split(": ", 1)[1])["arguments"] == argument
    assert not invocation.notes
    from fusion_cli.engines.agent import loop
    from tests.fakes import ScriptedProvider, model_result, tool_call
    from tests.test_agent_lessons import _deps

    provider = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("read_file", path="girdi.txt"),)),
            model_result(
                tool_calls=(tool_call("write_file", path="girdi.txt", content="hazır çağrıldı"),)
            ),
            model_result("İstenen dosya güncellendi ve kontroller geçiyor."),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    deps = _deps(proposal_workspace)
    deps.config = replace(
        deps.config,
        memory_dir=memory_dir(),
        runtime=replace(deps.config.runtime, verified_skill_proposals=True, self_review=False),
    )
    deps.capabilities = registry
    outcome = asyncio.run(
        loop.run_agent(
            invocation.task, deps, extra_system=invocation.context, self_review=False, verify=False
        )
    )
    assert outcome.ok, outcome.final_text
    assert provider.calls >= 2
    assert any(
        argument in message.content for messages in provider.seen_messages for message in messages
    )
    assert (proposal_workspace / "girdi.txt").read_text() == "hazır çağrıldı"
    before = skill.path.read_bytes()
    assert apply_proposal(proposal, arguments).exit_code == 1
    assert skill.path.read_bytes() == before


@pytest.mark.parametrize("arguments", [{}, {"dil": "de"}, {"dil": 7}, {"dil": "tr", "fazla": 1}])
def test_wrong_parameters_never_install(
    proposal_workspace: Path, arguments: dict[str, object]
) -> None:
    proposal, _ = seed_plan(proposal_workspace)
    result = apply_proposal(proposal, arguments)
    assert result.exit_code == 1
    assert "parametre" in result.output.lower()
    assert not capabilities_dir().exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "content",
        "workspace",
        "description",
        "unknown",
        "goal",
        "target",
        "expected",
        "schema",
        "roles",
    ],
)
def test_precondition_or_source_mismatch_never_installs(
    proposal_workspace: Path, mutation: str
) -> None:
    proposal, arguments = seed_plan(proposal_workspace)
    store = JsonCheckpointStore(memory_dir() / "workflow-checkpoints")
    checkpoint = store.load(proposal.routine.routine_id)
    assert checkpoint is not None
    if mutation == "missing":
        (proposal_workspace / "girdi.txt").unlink()
    elif mutation == "content":
        (proposal_workspace / "girdi.txt").write_text("eksik")
    elif mutation == "workspace":
        store.save(replace(checkpoint, root=str(proposal_workspace / "baska"), storage_revision=0))
    elif mutation == "description":
        store.save(replace(checkpoint, plan=replace(checkpoint.plan, task="Başka görev")))
    elif mutation in {"goal", "target", "expected"}:
        step = checkpoint.plan.steps[0]
        if mutation == "goal":
            step = replace(step, goal="Başka etki")
        else:
            check = step.verification_checks[-1]
            check = replace(
                check,
                **({"target": "baska.txt"} if mutation == "target" else {"expected": "başka"}),
            )
            step = replace(step, verification_checks=(*step.verification_checks[:-1], check))
        store.save(replace(checkpoint, plan=replace(checkpoint.plan, steps=(step,))))
    elif mutation in {"schema", "roles"}:
        definition = checkpoint.plan.routine
        assert definition is not None
        definition = (
            replace(definition, input_schema='{"type":"object"}')
            if mutation == "schema"
            else replace(definition, preconditions=("sonuc",), checks=("girdi-var", "girdi-hazir"))
        )
        store.save(replace(checkpoint, plan=replace(checkpoint.plan, routine=definition)))
    else:
        check = replace(checkpoint.plan.steps[0].verification_checks[0], criterion_id="baska")
        step = replace(checkpoint.plan.steps[0], verification_checks=(check,))
        store.save(replace(checkpoint, plan=replace(checkpoint.plan, steps=(step,))))
    result = apply_proposal(proposal, arguments)
    assert result.exit_code == 1
    assert not capabilities_dir().exists()


@pytest.mark.parametrize(
    "collision", ["directory", "file", "symlink", "root-symlink", "skill-name"]
)
def test_existing_paths_and_skill_names_are_never_overwritten(
    proposal_workspace: Path, collision: str
) -> None:
    proposal, arguments = seed_plan(proposal_workspace)
    root = capabilities_dir()
    root.mkdir(parents=True)
    target = root / proposal.routine.routine_id
    if collision == "directory":
        target.mkdir()
    elif collision == "file":
        target.write_text("koru")
    elif collision == "symlink":
        target.symlink_to(proposal_workspace / "hedef")
    elif collision == "root-symlink":
        root.rmdir()
        root.symlink_to(proposal_workspace, target_is_directory=True)
    else:
        source = proposal_workspace / ".agents" / "skills" / "mevcut"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(
            f"---\nname: {proposal.routine.routine_id}\ndescription: koru\n---\nkoru"
        )
    result = apply_proposal(proposal, arguments)
    assert result.exit_code == 1
    assert not (target / "SKILL.md").exists()


@pytest.mark.parametrize(
    "mutation", ["command", "duplicate", "template", "empty-content", "traversal", "symlink"]
)
def test_unsupported_or_unsafe_checks_are_rejected(proposal_workspace: Path, mutation: str) -> None:
    proposal, arguments = seed_plan(proposal_workspace)
    store = JsonCheckpointStore(memory_dir() / "workflow-checkpoints")
    checkpoint = store.load(proposal.routine.routine_id)
    assert checkpoint is not None
    first, second, third = checkpoint.plan.steps[0].verification_checks
    if mutation == "command":
        first = replace(first, kind=VerificationCheckKind.COMMAND, target="echo hazır")
    elif mutation == "duplicate":
        second = replace(second, criterion_id=first.criterion_id)
    elif mutation == "template":
        first = replace(first, target="$ARGUMENTS")
    elif mutation == "empty-content":
        second = replace(second, expected="")
    elif mutation == "traversal":
        first = replace(first, target="../disarida.txt")
    else:
        outside = proposal_workspace / "disarida"
        outside.mkdir()
        (outside / "girdi.txt").write_text("hazır")
        (proposal_workspace / "girdi.txt").unlink()
        (proposal_workspace / "girdi.txt").symlink_to(outside / "girdi.txt")
    step = replace(checkpoint.plan.steps[0], verification_checks=(first, second, third))
    store.save(replace(checkpoint, plan=replace(checkpoint.plan, steps=(step,))))
    result = apply_proposal(proposal, arguments)
    assert result.exit_code == 1
    assert not capabilities_dir().exists()


def test_blind_apply_rejects_development_id(proposal_workspace: Path) -> None:
    proposal, arguments = seed_plan(proposal_workspace)
    result = CliRunner().invoke(
        app,
        [
            "yetenek",
            "oneri-uygula",
            proposal.id,
            "--parametreler",
            json.dumps(arguments),
            "--split",
            "blind",
        ],
    )
    assert result.exit_code == 1
    assert "bulunamadı" in result.output
    assert not capabilities_dir().exists()


@pytest.mark.parametrize("value", ["Bearer sentetik1234567890", "!`echo tehlike`", "$ARGUMENTS"])
def test_sensitive_or_dynamic_parameters_are_not_persisted(
    proposal_workspace: Path, value: str
) -> None:
    proposal, _ = seed_plan(proposal_workspace, CASES[2])
    result = apply_proposal(proposal, {"baslik": value})
    assert result.exit_code == 1
    assert value not in result.output
    assert not capabilities_dir().exists()


@pytest.mark.parametrize("failure", ["write", "publish", "cleanup"])
def test_failed_install_leaves_no_partial_skill(
    proposal_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    from fusion_cli.engines import capability_proposals

    proposal, arguments = seed_plan(proposal_workspace)
    original_unlink = capability_proposals.os.unlink
    has_failed = False

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("sentetik hata")

    def fail_once(*args: object, **kwargs: object) -> None:
        nonlocal has_failed
        if not has_failed:
            has_failed = True
            raise OSError("sentetik hata")
        original_unlink(*args, **kwargs)

    if failure == "write":
        monkeypatch.setattr(capability_proposals.os, "fsync", fail)
    elif failure == "publish":
        monkeypatch.setattr(capability_proposals.os, "link", fail)
    else:
        monkeypatch.setattr(capability_proposals.os, "unlink", fail_once)
    result = apply_proposal(proposal, arguments)
    assert result.exit_code == 1
    assert not tuple(capabilities_dir().iterdir())
    assert (
        CapabilityRegistry(
            Path.home(), proposal_workspace, proposal_policy=ProposalPolicy(True)
        ).get_skill(proposal.routine.routine_id)
        is None
    )
