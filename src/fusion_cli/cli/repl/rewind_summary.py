"""`/rewind` menüsünde "Summarize from here" / "Summarize up to here" (#199, Claude Code).

Claude Code (Rewind and summarize, Guide a summary):
- Buradan itibaren özetle: seçilen noktadan SONRASI sıkıştırılır; ardından o mesajın istemi
  giriş kutusuna geri konur (yeniden gönder ya da düzenle).
- Buraya kadar özetle: seçilen noktadan ÖNCESİ sıkıştırılır, sonrası olduğu gibi kalır;
  giriş kutusu boş kalır.
- İsteğe bağlı talimat ("add context") özeti yönlendirir. Diskteki dosyalar değişmez; özgün
  mesajlar transcript'te kalır. `DISABLE_COMPACT` açıkken seçenekler gösterilmez.
Fusion: özet `/compact` ile aynı sıkıştırıcıyla (`engines.agent.compaction.compress`) yapılır.

Sınır, checkpoint'in `history_before`'u geçerli geçmişin başıyla BİREBİR örtüşüyorsa
kullanılır. Ölçüldü (1 Kasım): yalnız uzunluk kullanılıyordu; önceki bir özet ya da
`/compact` geçmişi kısalttıktan sonra eski checkpoint'ler yanlış aralığı özetliyor, istem
yanlış turdan geri konuyordu. Artık "Buraya kadar özetle" sonraki turların sınırını özetin
üzerine taşır; özetin içinde kalan tur için özetleme açık bir iletiyle reddedilir.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import dataclasses
import os
from collections.abc import Sequence

from ...core.types import Message
from ...ui import messages
from ...ui.picker import Choice
from .state import ReplState

FROM_HERE = "ozet-buradan"
UP_TO_HERE = "ozet-oncesi"
KINDS = (FROM_HERE, UP_TO_HERE)
_TRUE = frozenset({"1", "true", "yes", "on"})


def enabled() -> bool:
    """`DISABLE_COMPACT` açıksa özet seçenekleri yok (Claude Code)."""
    return os.environ.get("DISABLE_COMPACT", "").strip().lower() not in _TRUE


def choices() -> list[Choice]:
    if not enabled():
        return []
    return [
        Choice(FROM_HERE, messages.REWIND_SUMMARIZE_FROM, messages.REWIND_SUMMARIZE_FROM_HINT),
        Choice(UP_TO_HERE, messages.REWIND_SUMMARIZE_UP_TO, messages.REWIND_SUMMARIZE_UP_TO_HINT),
    ]


def parse(argument: str) -> tuple[int | None, str, str] | None:
    """`/rewind [no] ozet-buradan|ozet-oncesi [talimat…]` → (tur, tür, talimat); değilse None."""
    words = argument.split()
    kind_at = next((i for i, word in enumerate(words) if word in KINDS), None)
    if kind_at is None:
        return None
    head = words[:kind_at]
    if len(head) > 1 or (head and not head[0].isdigit()):
        return None
    index = int(head[0]) if head else None
    return index, words[kind_at], " ".join(words[kind_at + 1 :])


async def _compress(state: ReplState, part: Sequence[Message], focus: str) -> list[Message]:
    from ...engines.agent.compaction import compress

    return await compress(list(part), config=state.config, manual=True, focus=focus)


async def summarize(state: ReplState, index: int, kind: str, instructions: str = "") -> str:
    """Seçilen turdan sonrasını ya da öncesini özetle; dosyalara dokunulmaz."""
    from ...engines.agent.history import root_anchor_length
    from . import session_snapshot

    target = state.checkpoints.find(index)
    if target is None:
        return messages.REWIND_UNKNOWN_TURN.format(index=index)
    split = len(target.history_before)
    if not _boundary_holds(state.history, split, target.history_before):
        # Tur önceki bir özetin ya da `/compact`ın içinde kaldı: sınır artık geçmişte yok.
        return messages.REWIND_SUMMARY_STALE.format(index=index)
    prefix, tail = state.history[:split], state.history[split:]
    if kind == FROM_HERE:
        if not tail:
            return messages.REWIND_SUMMARY_NOTHING
        compressed = await _compress(state, tail, instructions)
        summary = compressed[root_anchor_length(tail) :]
        state.history = [*prefix, *summary]
        state.pending_input = target.task
    else:
        if not prefix:
            return messages.REWIND_SUMMARY_NOTHING
        compressed = await _compress(state, prefix, instructions)
        state.history = [*compressed, *tail]
        _rebase_later(state, index, split, compressed)
    session_snapshot.save(state)
    return messages.REWIND_SUMMARIZED.format(before=split + len(tail), after=len(state.history))


def _conversational(history: Sequence[Message]) -> tuple[Message, ...]:
    """Her turda yeniden kurulan sistem istemi ve harness notları dışındaki mesajlar."""
    return tuple(m for m in history if m.role != "system" and not m.harness_note)


def _boundary_holds(history: Sequence[Message], split: int, before: Sequence[Message]) -> bool:
    """Geçerli geçmişin başı checkpoint'in öncesiyle örtüşüyor mu (sistem/not hariç)?"""
    if split > len(history):
        return False
    return _conversational(history[:split]) == _conversational(before)


def _rebase_later(state: ReplState, index: int, split: int, compressed: Sequence[Message]) -> None:
    """Hedef ve sonraki turların sınırını özetlenmiş başın üzerine taşı."""
    state.checkpoints.replace_entries(
        dataclasses.replace(entry, history_before=(*compressed, *entry.history_before[split:]))
        if entry.index >= index and len(entry.history_before) >= split
        else entry
        for entry in state.checkpoints.entries()
    )


def summarize_blocking(state: ReplState, index: int, kind: str, instructions: str = "") -> str:
    """Eşzamanlı işleyici yolu (satır içi REPL, masaüstü): özeti ayrı iş parçacığında bekle."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, summarize(state, index, kind, instructions)).result()
