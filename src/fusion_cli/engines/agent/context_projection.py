"""Checkpoint ve gerçek tur günlüğünden çağrı anında türetilen bağlam."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...core.active_context import ActiveContext
from ...core.checkpoint import StepCheckpointEvidence
from ...core.evidence import EvidenceStatus
from ...core.execution_plan import StepStatus
from ...core.original_trace import OriginalTraceJournal, OriginalTraceScope
from ...core.redaction import redact
from ...core.types import Message
from .plan_checkpoint import _digest
from .verify_discovery import evidence_environment, source_digest

if TYPE_CHECKING:
    from .loop import AgentDeps

ACTIVE_HEADER = "[doğrulanmış çalışma durumu]"
ACTIVE_MAX_CHARS = 3000
MAX_PINS = 4
EVIDENCE_NOTE_CHARS = 1000
_LOG = logging.getLogger(__name__)


async def derive_context(deps: AgentDeps, *, local_remaining: int | None = None) -> ActiveContext:
    """Plan uydurmadan mevcut otoriteyi oku; eski hash'i yeniden doğrula."""
    checkpoint = None
    if deps.checkpoint_store is not None and deps.conversation_id:
        checkpoint = await asyncio.to_thread(
            deps.checkpoint_store.find_resumable,
            str(deps.tool_context.root.resolve()),
            deps.conversation_id,
        )
    steps = checkpoint.plan.steps if checkpoint is not None else ()
    if deps.context_step is not None and not any(
        item.step_id == deps.context_step.step_id for item in steps
    ):
        steps = (*steps, deps.context_step)
    opened = [step for step in steps if step.status is not StepStatus.COMPLETED]
    if not opened:
        return ActiveContext()
    lines = [ACTIVE_HEADER, "Bu ölçülmüş durum model özetinden üstündür."]
    pins: list[str] = []
    current_source = await asyncio.to_thread(source_digest, deps.tool_context.root)
    for step in opened:
        lines.extend(
            f"Açık koşul {step.step_id}: {redact(text)[:180]}" for text in step.success_criteria[:8]
        )
        lines.extend(
            f"Kontrol: {redact(check.criterion_id)}" for check in step.verification_checks[:8]
        )
    relevant = {step.step_id for step in opened} | {
        identity for step in opened for identity in step.depends_on
    }
    evidence_lines, pins = await _evidence_lines(
        checkpoint.step_evidence if checkpoint is not None else (), relevant, deps, current_source
    )
    lines[2:2] = [_budget_line(deps, local_remaining), *_bounded_evidence(evidence_lines)]
    unique = tuple(dict.fromkeys(pins))
    return ActiveContext(
        "\n".join(lines)[:ACTIVE_MAX_CHARS],
        frozenset(unique[:MAX_PINS]),
        max(0, len(unique) - MAX_PINS),
    )


def _bounded_evidence(lines: list[str]) -> list[str]:
    """Kanıt ayrıntısı açık koşul için ayrılan not payını tüketmesin."""
    selected: list[str] = []
    size = 0
    for line in lines:
        if size + len(line) + 1 > EVIDENCE_NOTE_CHARS:
            selected.append("Ek kanıt ayrıntıları not bütçesi nedeniyle gösterilmedi.")
            break
        selected.append(line)
        size += len(line) + 1
    return selected


async def _evidence_lines(
    records: tuple[StepCheckpointEvidence, ...],
    relevant: set[str],
    deps: AgentDeps,
    current_source: str,
) -> tuple[list[str], list[str]]:
    """Ölçülmüş sürüm ve çağrı kanıtlarını mevcut kaynakla eşleştir."""
    lines: list[str] = []
    pins: list[str] = []
    for evidence in records:
        if evidence.step_id not in relevant:
            continue
        for artifact in evidence.artifacts:
            current = await asyncio.to_thread(_digest, deps.tool_context.root, artifact.path)
            if current and current == artifact.digest:
                lines.append(f"Doğrulanmış SHA-256 {redact(artifact.path)}: {current}")
            else:
                lines.append(f"Kanıt güncel değil: {redact(artifact.path)}")
        for criterion in evidence.criteria:
            if (
                criterion.source_after_digest == current_source
                and criterion.environment
                and criterion.call_id
                and await asyncio.to_thread(
                    evidence_environment,
                    deps.tool_context.root,
                    tuple(criterion.environment.command.splitlines()),
                    runtime=sys.version,
                )
                == criterion.environment
            ):
                if criterion.status is not EvidenceStatus.PASSED:
                    pins.append(criterion.call_id)
                lines.append(
                    f"Ölçülmüş kaynak SHA-256: {current_source}; "
                    f"çağrı: {redact(criterion.call_id)}; "
                    f"ortam: {redact(criterion.environment.runtime)[:80]}"
                )
    return lines, pins


def _budget_line(deps: AgentDeps, local_remaining: int | None) -> str:
    """Tek gerçek bütçe otoritesinin o andaki kalan hakkı."""
    budget = deps.budget
    if budget is None:
        return "Tur bütçesi henüz kurulmadı."
    remaining = (
        max(0, budget.max_model_calls - budget.model_calls)
        if budget.max_model_calls is not None
        else "sınırsız"
    )
    local = f"; adımda kalan: {local_remaining}" if local_remaining is not None else ""
    return f"Gerçek kalan model çağrısı: {remaining}{local}; kalan süre: {budget.remaining_s()}"


def restore_context(messages: Sequence[Message], projection: ActiveContext) -> list[Message]:
    """Eski projeksiyonu bırak; tek taze harness notu taşınır."""
    clean = [
        message
        for message in messages
        if not (message.harness_note and message.content.startswith(ACTIVE_HEADER))
    ]
    if projection.note:
        clean.append(Message("user", projection.note, harness_note=True))
    return clean


@dataclass(frozen=True, slots=True)
class OriginalSegment:
    """İçerik kopyası olmadan gerçek journal kapsamına referans."""

    identity: str
    call_ids: frozenset[str]


@dataclass(slots=True)
class OriginalCursor:
    """Yalnız bu turdaki segment referansları; başarısız yazı da kapsamdan düşmez."""

    turn_id: str = ""
    excluded_call_ids: frozenset[str] = frozenset()
    segments: list[OriginalSegment] = field(default_factory=list)

    async def append(self, messages: Sequence[Message], deps: AgentDeps) -> None:
        """Tamamlanmış grupları maskelemeden önce aynı journal sahibine yaz."""
        journal = original_journal(deps.journal)
        if not deps.config.runtime.context_original_trace or journal is None:
            return
        turn_id = deps.attempt_id or ""
        if not turn_id or not journal.original_owner_id:
            return
        if self.turn_id != turn_id:
            self.turn_id = turn_id
            self.segments.clear()
        seen = {segment.identity for segment in self.segments}
        for group in completed_groups(messages):
            calls = frozenset(call.id for message in group for call in message.tool_calls)
            if calls & self.excluded_call_ids:
                continue
            identity = hashlib.sha256("\0".join(sorted(calls)).encode()).hexdigest()
            if identity in seen:
                continue
            self.segments.append(OriginalSegment(identity, calls))
            seen.add(identity)
            scope = OriginalTraceScope(journal.original_owner_id, turn_id, (identity,))
            try:
                saved = await journal.append_original(scope, group)
                if not saved:
                    _LOG.info("Özgün segment kaydedilemedi; okuma kapsamı eksik kalacak.")
            except (OSError, ValueError) as error:
                _LOG.warning("Özgün segment yazılamadı.", extra={"hata": type(error).__name__})
                # Referans kalır: okuyucu eksik segmenti açık fallback'e çevirir.
                continue

    def scope(
        self, old: Sequence[Message], recent: Sequence[Message], deps: AgentDeps
    ) -> OriginalTraceScope | None:
        """Araç dışı konuşmayı eksik journal ile değiştirme; son grubu kapsamdan çıkar."""
        journal = original_journal(deps.journal)
        if journal is None or not self.turn_id:
            return OriginalTraceScope("", deps.attempt_id or "", ())
        # Üretici yalnız araç gruplarını kaydeder. Kullanıcı, düz assistant veya
        # önceki özet içeren dilimin tamamlığı bu kayıttan kanıtlanamaz.
        # Kaynak var + scope yok, compactor'ın açık fallback yolunu seçer.
        if any(message.role != "tool" and not message.tool_calls for message in old):
            return None
        recent_ids = {call.id for message in recent for call in message.tool_calls}
        ids = tuple(
            segment.identity for segment in self.segments if not segment.call_ids & recent_ids
        )
        return OriginalTraceScope(journal.original_owner_id, self.turn_id, ids)


def completed_groups(messages: Sequence[Message]) -> list[tuple[Message, ...]]:
    """Modelin bütün sonuçları gelmiş assistant araç gruplarını ayır."""
    groups: list[tuple[Message, ...]] = []
    pending: set[str] = set()
    group: list[Message] = []
    for message in messages:
        if message.role == "assistant" and message.tool_calls:
            group = [message]
            pending = {call.id for call in message.tool_calls}
        elif message.role == "tool" and message.tool_call_id in pending:
            group.append(message)
            pending.remove(message.tool_call_id)
            if not pending:
                groups.append(tuple(group))
                group = []
        elif not message.harness_note:
            pending.clear()
            group = []
    return groups


def original_journal(value: object) -> OriginalTraceJournal | None:
    """Eski snapshot günlüklerini zorunlu özgün iz desteğine yükseltme."""
    return value if isinstance(value, OriginalTraceJournal) else None


async def prepare_context(
    messages: list[Message], deps: AgentDeps, *, local_remaining: int | None = None
) -> None:
    """Her sınırda aynı üretici ve projeksiyonu kullan."""
    await deps.original_cursor.append(messages, deps)
    if deps.config.runtime.context_restore_state or deps.config.runtime.context_evidence_pins:
        deps.active_context = await derive_context(deps, local_remaining=local_remaining)
    if deps.config.runtime.context_restore_state:
        messages[:] = restore_context(messages, deps.active_context)


async def compact_context(
    messages: list[Message], deps: AgentDeps, threshold: int, *, between_turns: bool = False
) -> list[Message]:
    """Gerçek kesim kapsamını aynı journal okuyucusuna bağla."""
    from . import compaction, history

    if not (
        deps.config.runtime.context_original_trace or deps.config.runtime.context_evidence_pins
    ):
        function = compaction.compress if between_turns else compaction.compact_in_turn
        result = await function(
            messages, config=deps.config, publisher=deps.publisher, threshold_chars=threshold
        )
        return (
            restore_context(result, deps.active_context)
            if deps.config.runtime.context_restore_state
            else result
        )
    cut = (
        history.safe_cut(messages)
        if between_turns
        else compaction._summary_cut(messages, history.task_anchor_length(messages))
    )
    source = original_journal(deps.journal) if deps.config.runtime.context_original_trace else None
    anchor = (
        history.root_anchor_length(messages)
        if between_turns
        else history.task_anchor_length(messages)
    )
    scope = (
        deps.original_cursor.scope(messages[anchor:cut], messages[cut:], deps)
        if deps.config.runtime.context_original_trace
        else None
    )
    function = compaction.compress if between_turns else compaction.compact_in_turn
    result = await function(
        messages,
        config=deps.config,
        publisher=deps.publisher,
        threshold_chars=threshold,
        original_source=source,
        original_scope=scope,
        pinned_call_ids=deps.active_context.pinned_call_ids
        if deps.config.runtime.context_evidence_pins
        else frozenset(),
    )
    return (
        restore_context(result, deps.active_context)
        if deps.config.runtime.context_restore_state
        else result
    )


def record_protection(messages: list[Message], deps: AgentDeps, threshold: int) -> None:
    """Koruma bütçeyi aşıyorsa açık olay üret; geçmişi zorla bozma."""
    from ...core.events import ContextProtectionMeasured
    from .history import total_chars, unseen_tool_indexes

    visible = total_chars(messages)
    projection = deps.active_context
    if visible < threshold and not projection.omitted_pins:
        return
    newest = unseen_tool_indexes(messages)
    deps.publisher.publish(
        ContextProtectionMeasured(
            threshold,
            visible,
            total_chars([messages[index] for index in newest]),
            len(projection.pinned_call_ids),
            projection.omitted_pins,
            visible >= threshold,
        )
    )
