"""`/rewind` menüsünde "Summarize from here" / "Summarize up to here" (#199, Claude Code).

Claude Code (Rewind and summarize, Guide a summary):
- Buradan itibaren özetle: seçilen noktadan SONRASI sıkıştırılır; ardından o mesajın istemi
  giriş kutusuna geri konur (yeniden gönder ya da düzenle).
- Buraya kadar özetle: seçilen noktadan ÖNCESİ sıkıştırılır, sonrası olduğu gibi kalır;
  giriş kutusu boş kalır.
- İsteğe bağlı talimat ("add context") özeti yönlendirir. Diskteki dosyalar değişmez; özgün
  mesajlar transcript'te kalır. `DISABLE_COMPACT` açıkken seçenekler gösterilmez.
Fusion: özet `/compact` ile aynı sıkıştırıcıyla (`engines.agent.compaction.compress`) yapılır.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
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
    split = min(len(target.history_before), len(state.history))
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
        state.history = [*(await _compress(state, prefix, instructions)), *tail]
    session_snapshot.save(state)
    return messages.REWIND_SUMMARIZED.format(before=split + len(tail), after=len(state.history))


def summarize_blocking(state: ReplState, index: int, kind: str, instructions: str = "") -> str:
    """Eşzamanlı işleyici yolu (satır içi REPL, masaüstü): özeti ayrı iş parçacığında bekle."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, summarize(state, index, kind, instructions)).result()
