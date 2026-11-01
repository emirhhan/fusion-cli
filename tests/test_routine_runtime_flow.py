"""Rutin tanımı aynı plan ve checkpoint sözleşmesinde taşınır."""

from __future__ import annotations

import json

from fusion_cli.engines.agent.plan_parser import parse_execution_plan


def test_plan_rutin_bildirimi_kaybolmaz():
    raw = {
        "plan_id": "rutin",
        "task": "iş",
        "steps": [
            {
                "step_id": "adim",
                "goal": "dosyayı yaz",
                "depends_on": [],
                "expected_effects": [],
                "allowed_tool_families": ["files"],
                "success_criteria": ["önce", "sonra"],
                "verification_hint": "",
                "retry_safety": "safe",
                "verification_checks": [
                    {"criterion_id": "önce", "kind": "file_exists", "target": "girdi"},
                    {"criterion_id": "sonra", "kind": "file_exists", "target": "sonuc"},
                ],
            }
        ],
        "routine": {
            "input_schema": '{"type":"object"}',
            "preconditions": ["önce"],
            "checks": ["sonra"],
        },
    }
    plan = parse_execution_plan(json.dumps(raw))
    assert getattr(plan, "routine", None) is not None


async def test_uc_gercek_plan_yurutmesi_oneri_uretir(tmp_path):
    from dataclasses import replace

    from fusion_cli.core.evidence import ToolUse
    from fusion_cli.core.execution_plan import (
        ExecutionPlan,
        PlanStep,
        RetrySafety,
        RoutineDefinition,
        VerificationCheck,
        VerificationCheckKind,
    )
    from fusion_cli.engines.agent.learning_steps import finish_learning
    from fusion_cli.engines.agent.lesson_attribution import LessonTurnState
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.plan_runner import run_execution_plan
    from fusion_cli.memory.checkpoint_store import JsonCheckpointStore
    from fusion_cli.memory.skill_proposals import SkillProposalStore
    from tests.test_agent_lessons import _deps

    (tmp_path / "girdi.txt").write_text("hazır")
    checks = (
        VerificationCheck("önce", VerificationCheckKind.FILE_EXISTS, "girdi.txt"),
        VerificationCheck("sonra", VerificationCheckKind.FILE_CONTAINS, "sonuc.txt", "tamam"),
    )
    plan = ExecutionPlan(
        "rutin",
        "dosyayı üret",
        (
            PlanStep(
                "adim",
                "sonuc.txt yaz",
                (),
                (),
                ("files",),
                ("önce", "sonra"),
                "",
                RetrySafety.SAFE,
                verification_checks=checks,
            ),
        ),
        routine=RoutineDefinition('{"type":"object"}', ("önce",), ("sonra",)),
    )
    store = SkillProposalStore(tmp_path / "bellek" / "skill-proposals.json")
    for index in range(4):
        deps = _deps(tmp_path)
        deps.config = replace(
            deps.config, runtime=replace(deps.config.runtime, verified_skill_proposals=True)
        )
        deps.attempt_id = f"gercek-{index}"
        deps.conversation_id = f"konusma-{index}"
        deps.lesson_state = LessonTurnState()
        deps.skill_proposals = store
        deps.checkpoint_store = JsonCheckpointStore(tmp_path / f"checkpoint-{index}")
        if index == 3:
            from fusion_cli.core.lesson_runtime import LessonDelivery
            from fusion_cli.engines.agent.learning_steps import recall_lessons
            from fusion_cli.engines.agent.lesson_attribution import offer
            from tests.test_lesson_runtime_attribution import Memory

            deps.config = replace(
                deps.config,
                runtime=replace(deps.config.runtime, lessons=True, lesson_attributed_feedback=True),
            )
            deps.lessons = Memory()
            proposal = (await store.list())[0]
            deps.lessons.lesson = replace(
                deps.lessons.lesson, evidence_refs=(proposal.routine.source_digest,)
            )
            offer(recall_lessons("dosya", deps), deps, LessonDelivery.TOOL)

        async def agent(task, child, index=index, **kwargs):
            if (tmp_path / "sonuc.txt").exists():
                await child.base_registry.execute(
                    "read_file", {"path": "sonuc.txt"}, child.tool_context
                )
            result = await child.base_registry.execute(
                "write_file", {"path": "sonuc.txt", "content": f"tamam{index}"}, child.tool_context
            )
            assert result.ok, result.output
            return AgentOutcome(
                "tamam",
                [],
                tool_calls_made=1,
                mutating_tool_calls_made=1,
                tool_uses=(
                    ToolUse(
                        "write_file",
                        True,
                        True,
                        {"path": "sonuc.txt", "content": f"tamam{index}"},
                        result.output,
                        call_id=f"yaz-{index}",
                    ),
                ),
            )

        outcome = await run_execution_plan(
            "dosyayı üret", deps, agent, plan=plan, self_review=False
        )
        assert outcome.ok, outcome.final_text
        assert deps.lesson_state.routines, "Gerçek final kanıtı gözlem üretmeli"
        await finish_learning(outcome, deps, plan_mode=False)
        assert len(await store.list()) == (1 if index >= 2 else 0)
        await finish_learning(outcome, deps, plan_mode=False)
        if index == 3:
            assert deps.lessons.lesson.success_count == 1
            assert deps.lessons.feedback[0]["used"] is True
    completed = deps.checkpoint_store.load("rutin")
    assert completed is not None
    deps.attempt_id = "sadece-replay"
    deps.checkpoint_store = None
    deps.lesson_state = LessonTurnState()
    replay = await run_execution_plan(
        "dosyayı üret", deps, agent, plan=completed.plan, self_review=False
    )
    await finish_learning(replay, deps, plan_mode=False)
    assert len((await store.list())[0].observations) == 4
