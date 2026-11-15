"""Uzun bağlam uyaranları gerçek journal/checkpoint ve kontrol API'lerini kullanır."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING

from evals.research_types import ResearchScenario
from fusion_cli.core.checkpoint import WorkflowCheckpoint
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStep,
    RetrySafety,
)
from fusion_cli.core.original_trace import OriginalTraceScope
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent.context_projection import derive_context
from fusion_cli.engines.agent.step_verification import _final_criteria
from fusion_cli.memory.checkpoint_store import JsonCheckpointStore
from fusion_cli.memory.turn_journal import FileTurnJournal

if TYPE_CHECKING:
    from fusion_cli.engines.agent.loop import AgentDeps


def scenario_step(spec: ResearchScenario) -> PlanStep:
    """Açık koşulları ürünün tipli plan sözleşmesine bağla."""
    checks = spec.checks
    return PlanStep(
        "research",
        "Açık dosyaları tamamla",
        (),
        (),
        ("files",),
        tuple(check.criterion_id for check in checks),
        "Dosya içeriğini ölç",
        RetrySafety.SAFE,
        verification_checks=checks,
    )


async def prepare_context(
    deps: AgentDeps, directory: Path, spec: ResearchScenario
) -> list[Message]:
    """Kayıplı özet karşısında disk kaydı aynı gerçek turda erişilebilir kalır."""
    deps.config = replace(
        deps.config,
        runtime=replace(
            deps.config.runtime,
            context_original_trace=True,
            context_restore_state=True,
            context_evidence_pins=True,
        ),
    )
    deps.attempt_id = "research-turn"
    deps.learned_compression_chars = 30000
    deps.context_step = scenario_step(spec)
    journal = FileTurnJournal(
        directory / "journal.json", task="Açık işi tamamla", original_owner_id="research"
    )
    deps.journal = journal
    messages = [Message("user", spec.rule)]
    for index in range(24):
        call = ToolCall(f"history-{index}", "read_file", '{"path":"notlar.txt"}')
        content = spec.diagnostic if index == 0 else "Geçmiş bilgi. " * 100
        group = [
            Message("assistant", "", tool_calls=(call,)),
            Message("tool", content, tool_call_id=call.id, name="read_file", ok=True),
        ]
        await journal.append_original(
            OriginalTraceScope("research", "history-turn", (f"segment-{index}",)), group
        )
        messages.extend(group)
    messages.append(Message("assistant", "Eski özet: bütün iş tamamlandı."))
    await asyncio.to_thread(journal.save, messages)
    store = JsonCheckpointStore(
        directory / "checkpoints", root=deps.tool_context.root, conversation_id=deps.conversation_id
    )
    checkpoint = WorkflowCheckpoint(
        ExecutionPlan("research-plan", "Açık işi tamamla", (deps.context_step,)),
        str(deps.tool_context.root.resolve()),
        deps.conversation_id,
        (),
        deps.clock.now(),
    )
    await asyncio.to_thread(store.save, checkpoint)
    deps.checkpoint_store = store
    return messages


async def collect_context(deps: AgentDeps, spec: ResearchScenario) -> dict[str, object]:
    """Son dosya hashleri ve journal okuması başarı beyanından bağımsız ölçülür."""
    records: dict[str, object] = {}
    checks = scenario_step(spec).verification_checks
    if checks:
        final = await _final_criteria(
            ExecutionPlan("research-final", "Son kabul", (scenario_step(spec),)),
            deps.tool_context.root,
            (),
        )
        records["criteria"] = [asdict(item) for item in final.criteria]
        records["final_criteria_ok"] = final.ok
    if deps.checkpoint_store is not None:
        checkpoint = await asyncio.to_thread(
            deps.checkpoint_store.find_resumable,
            str(deps.tool_context.root.resolve()),
            deps.conversation_id,
        )
        records["checkpoint_loaded"] = checkpoint is not None
    if deps.journal is not None:
        projection = await derive_context(deps)
        records["active_context"] = asdict(projection)
        if isinstance(deps.journal, FileTurnJournal):
            original = await deps.journal.read_original(
                OriginalTraceScope("research", "history-turn", ("segment-0",))
            )
            records["original_read"] = asdict(original)
            journal = await asyncio.to_thread(deps.journal.load)
            records["journal_message_count"] = len(journal.messages) if journal else 0
    return records
