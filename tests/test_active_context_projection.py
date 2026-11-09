"""Aktif durum özete değil mevcut checkpoint ve bütçeye bağlıdır."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent import compaction, loop

from .fakes import RecordingSink
from .test_agent_loop import _deps


async def test_runtime_uc_sikistirmada_checkpoint_hash_ve_butceyi_korur(tmp_path, monkeypatch):
    deps = _deps(tmp_path, RecordingSink())
    assert hasattr(deps.config.runtime, "context_restore_state")
    from fusion_cli.core.checkpoint import (
        ArtifactFingerprint,
        StepCheckpointEvidence,
        WorkflowCheckpoint,
    )
    from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
    from fusion_cli.engines.agent.context_projection import ACTIVE_HEADER

    path = tmp_path / "app.py"
    path.write_text("ölçülmüş içerik")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    step = PlanStep("adim", "düzelt", (), (), (), ("açık kriter",), "", RetrySafety.SAFE)
    checkpoint = WorkflowCheckpoint(
        ExecutionPlan("plan", "iş", (step,)),
        str(tmp_path),
        "chat",
        (),
        1,
        (StepCheckpointEvidence("adim", artifacts=(ArtifactFingerprint("app.py", digest),)),),
    )

    class Store:
        def load(self, plan_id):
            return checkpoint

    deps.checkpoint_store = Store()
    deps.conversation_id = "chat"
    deps.context_plan_id = "plan"
    deps.budget = loop._new_budget(deps.config)
    deps.config = replace(
        deps.config, runtime=replace(deps.config.runtime, context_restore_state=True)
    )
    deps.learned_compression_chars = 4000

    async def summarize(*args):
        return "Bütün kriterler kapandı; bütçe sınırsız."

    monkeypatch.setattr(compaction, "_summarize", summarize)
    messages = [Message("system", "sistem"), Message("user", "iş")]
    for _round_index in range(3):
        for index in range(20):
            messages.extend((Message("assistant", "a" * 2000), Message("user", f"devam {index}")))
        await loop._compact_before_call(messages, deps, loop._State())
        notes = [
            message.content for message in messages if message.content.startswith(ACTIVE_HEADER)
        ]
        assert len(notes) == 1
        assert "açık kriter" in notes[0] and digest in notes[0]
        assert "kalan" in notes[0]
    path.write_text("değişti")
    await loop._compact_before_call(messages, deps, loop._State())
    assert digest not in "\n".join(
        message.content for message in messages if message.content.startswith(ACTIVE_HEADER)
    )


@pytest.mark.parametrize("enabled", [False, True])
async def test_son_coklu_grubun_butun_sonuclari_korunur(tmp_path, enabled):
    deps = _deps(tmp_path, RecordingSink())
    assert hasattr(deps.config.runtime, "context_evidence_pins")
    deps.config = replace(
        deps.config,
        runtime=replace(deps.config.runtime, context_evidence_pins=enabled, tool_output_window=1),
    )
    messages = [Message("user", "iş")]
    for index in range(5):
        calls = tuple(ToolCall(f"{index}-{offset}", "read_file", "{}") for offset in range(3))
        messages.append(Message("assistant", "", tool_calls=calls))
        messages.extend(
            Message("tool", "sonuç" * 1000, tool_call_id=call.id, name="read_file", ok=True)
            for call in calls
        )
    view = loop._masked_view(messages, deps, deps.config.agent).messages
    assert view[-3:] == messages[-3:]
    clean = compaction.history.clear_old_tool_outputs(messages, 100)
    assert clean[-3:] == messages[-3:]


async def test_acik_kriter_pini_kapaninca_ve_kaynak_degistiğinde_birakilir(tmp_path):
    import sys

    from fusion_cli.core.checkpoint import StepCheckpointEvidence, WorkflowCheckpoint
    from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
    from fusion_cli.core.execution_plan import (
        ExecutionPlan,
        PlanStep,
        RetrySafety,
        StepStatus,
        VerificationCheckKind,
    )
    from fusion_cli.engines.agent.context_projection import derive_context
    from fusion_cli.engines.agent.verify_discovery import evidence_environment, source_digest

    deps = _deps(tmp_path, RecordingSink())
    (tmp_path / "app.py").write_text("def run(): pass\n")
    step = PlanStep("step", "iş", (), (), (), ("kriter",), "", RetrySafety.SAFE)
    criterion = CriterionEvidence(
        "kriter",
        VerificationCheckKind.COMMAND,
        EvidenceStatus.FAILED,
        "ölçüldü",
        source_after_digest=source_digest(tmp_path),
        call_id="gercek-call",
        environment=evidence_environment(tmp_path, ("python -V",), runtime=sys.version),
    )
    checkpoint = WorkflowCheckpoint(
        ExecutionPlan("plan", "iş", (step,)),
        str(tmp_path),
        "chat",
        (),
        1,
        (StepCheckpointEvidence("step", criteria=(criterion,)),),
    )

    class Store:
        def load(self, plan_id):
            return checkpoint

    deps.checkpoint_store = Store()
    deps.conversation_id = "chat"
    deps.context_plan_id = "plan"
    assert (await derive_context(deps)).pinned_call_ids == frozenset({"gercek-call"})
    (tmp_path / "app.py").write_text("def changed(): pass\n")
    assert not (await derive_context(deps)).pinned_call_ids
    checkpoint = replace(
        checkpoint,
        plan=replace(checkpoint.plan, steps=(replace(step, status=StepStatus.COMPLETED),)),
    )
    assert not (await derive_context(deps)).note


async def test_plain_chat_aktif_plan_uydurmaz(tmp_path):
    from fusion_cli.engines.agent.context_projection import derive_context

    deps = _deps(tmp_path, RecordingSink())
    assert not (await derive_context(deps)).note


@pytest.mark.parametrize(
    "flags",
    [
        (pins, trace, restore)
        for pins in (False, True)
        for trace in (False, True)
        for restore in (False, True)
    ],
)
async def test_coklu_son_grup_harness_notuyla_ozete_girmez(tmp_path, monkeypatch, flags):
    deps = _deps(tmp_path, RecordingSink())
    deps.config = replace(
        deps.config,
        runtime=replace(
            deps.config.runtime,
            context_evidence_pins=flags[0],
            context_original_trace=flags[1],
            context_restore_state=flags[2],
        ),
    )
    deps.learned_compression_chars = 100
    traces = []

    async def summarize(trace, *args):
        traces.append(trace)
        return "Özet."

    monkeypatch.setattr(compaction, "_summarize", summarize)
    messages = [Message("system", "sistem"), Message("user", "iş")]
    for _index in range(15):
        messages.extend((Message("assistant", "eski " * 300), Message("user", "devam")))
    calls = tuple(ToolCall(f"last-{index}", "read_file", "{}") for index in range(30))
    messages.append(Message("assistant", "", tool_calls=calls))
    results = [
        Message("tool", f"SON-GRUP-{call.id}" + "a" * 500, tool_call_id=call.id) for call in calls
    ]
    messages.extend(results)
    messages.append(Message("user", "ölçülmüş harness", harness_note=True))
    await loop._compact_before_call(messages, deps, loop._State())
    assert all(result in messages for result in results)
    assert all("SON-GRUP-" not in trace for trace in traces)


@pytest.mark.parametrize("requested", [1, 3, 5])
async def test_kirk_adim_kontrollu_replay(tmp_path, monkeypatch, requested, record_property):
    import json

    from fusion_cli.core.execution_plan import PlanStep, RetrySafety
    from fusion_cli.engines.agent.context_projection import ACTIVE_HEADER

    deps = _deps(tmp_path, RecordingSink())
    deps.config = replace(
        deps.config, runtime=replace(deps.config.runtime, context_restore_state=True)
    )
    deps.context_step = PlanStep(
        "step", "src/app.py", (), (), (), ("açık kriter",), "", RetrySafety.SAFE
    )
    deps.budget = loop._new_budget(deps.config)
    deps.learned_compression_chars = 2000
    calls = []

    async def summarize(trace, *args):
        calls.append(trace)
        return "Model bütün işin bittiğini yanlış söylüyor."

    monkeypatch.setattr(compaction, "_summarize", summarize)
    messages = [
        Message("system", "sistem"),
        Message("user", "src/app.py dosyasında çalış; asla push etme."),
    ]
    boundaries = {round(40 * index / requested) for index in range(1, requested + 1)}
    outcomes = []
    for index in range(1, 41):
        call = ToolCall(f"call{index}", "read_file", "{}")
        messages.extend(
            (
                Message("assistant", "ölçülen adım " * 150, tool_calls=(call,)),
                Message("tool", f"src/app.py adım {index}", tool_call_id=call.id),
            )
        )
        if index in boundaries:
            outcomes.append(await loop._compact_before_call(messages, deps, loop._State()))
    text = "\n".join(message.content for message in messages)
    criteria = [
        message.content for message in messages if message.content.startswith(ACTIVE_HEADER)
    ]
    assert "src/app.py" in text and "asla push etme" in text
    assert len(criteria) == 1 and "açık kriter" in criteria[0]
    assert len(calls) == requested
    record_property(
        "controlled_replay",
        json.dumps(
            {
                "steps": 40,
                "requested_compactions": requested,
                "actual_summaries": len(calls),
                "path_preserved": True,
                "rule_preserved": True,
                "open_criterion_preserved": True,
                "boundary_can_continue": outcomes,
                "live_model_gain": False,
            },
            ensure_ascii=False,
        ),
    )
