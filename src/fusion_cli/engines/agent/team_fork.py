"""Fork alt ajan: ana konuşmanın bağlamını devralan izole alt görev (P-054).

Claude Code'un `/subtask` ve beceri frontmatter'ındaki `context: fork` davranışının
karşılığı. Olağan alt ajan TEMİZ bağlamla başlar (yalnız görev metni + kişilik); fork alt
ajan ana konuşmanın o ana kadarki mesajlarını başlangıç geçmişi olarak alır, kendi
sistem istemiyle ve kendi adım bütçesiyle koşar, sonucu tek özet olarak döner. Ana
konuşmaya yalnız bu özet eklenir; alt ajanın kendi araç çağrıları ana geçmişe karışmaz.

Devredilen görünüm model çağırmadan kurulur (`compaction.compress` özetleyici çağırır,
burada istenmez): sistem mesajı düşer (alt ajanın kendi sistemi var), eski araç çıktıları
`clear_old_tool_outputs` ile temizlenir, hâlâ uzunsa kök tur korunup ortadaki mesajlar
atılır ve atıldığı not düşülür.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from ...core.types import Message
from . import history as history_rules

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome

#: Fork alt ajana devredilen geçmişin karakter tavanı; üstü araç çıktısı temizliği ve
#: orta kesim ile indirilir. Alt ajan bağlamı katlamasın diye ana eşiğin altındadır.
FORK_MAX_CHARS = 60_000
#: Kesimde her koşulda korunan son mesaj sayısı.
FORK_KEEP_RECENT = 8
#: Orta kesim notu: model geçmişin tamamını gördüğünü sanmasın.
FORK_GAP_NOTE = "[fork: aradaki {count} mesaj bağlam sınırı nedeniyle çıkarıldı]"
#: Alt ajanın başlangıç mesajına eklenen açıklama.
FORK_BRIEF = (
    "Bu görev ana konuşmanın bağlamını DEVRALAN bir alt görevdir: yukarıdaki mesajlar ana "
    "konuşmadır, onları yeniden yapma; yalnız verilen alt görevi yap ve kısa bir sonuç döndür."
)

LiveHistory = Callable[[], Sequence[Message]]


def fork_history(messages: Sequence[Message] | None) -> list[Message]:
    """Ana geçmişin alt ajana devredilecek görünümü (sistemsiz, kırpılmış)."""
    body = [message for message in (messages or ()) if message.role != "system"]
    if not body:
        return []
    trimmed = history_rules.clear_old_tool_outputs(body, threshold_chars=FORK_MAX_CHARS)
    if history_rules.total_chars(trimmed) <= FORK_MAX_CHARS:
        return trimmed
    anchor = trimmed[: _root_turn_length(trimmed)]
    recent = trimmed[len(anchor) :][-FORK_KEEP_RECENT:]
    kept = len(anchor) + len(recent)
    gap = max(0, len(trimmed) - kept)
    note = Message("user", FORK_GAP_NOTE.format(count=gap), harness_note=True)
    return [*anchor, note, *recent] if gap else [*anchor, *recent]


def _root_turn_length(messages: Sequence[Message]) -> int:
    """Kök turun uzunluğu: ikinci `user` mesajına kadar (sistemsiz listede de çalışır).

    `history.root_anchor_length` yalnız `system` ile başlayan listede anchor açar; fork
    görünümünde sistem düşmüştür ama kullanıcının kök talimatı yine korunmalıdır.
    """
    seen_users = 0
    for index, message in enumerate(messages):
        if message.role == "user":
            seen_users += 1
            if seen_users == 2:
                return index
    return min(len(messages), 1)


def parent_history(deps: AgentDeps) -> list[Message]:
    """Üst ajanın ANLIK geçmişi (`deps.live_history`); yoksa boş liste."""
    source: LiveHistory | None = getattr(deps, "live_history", None)
    if source is None:
        return []
    try:
        return list(source())
    except Exception:
        return []


async def run_forked_turn(
    task: str,
    deps: AgentDeps,
    *,
    history: list[Message] | None = None,
    plan_mode: bool = False,
    **_ignored: object,
) -> AgentOutcome:
    """`/subtask <görev>`: turu fork alt ajan olarak koştur, ana geçmişe yalnız özeti ekle.

    `run_agent` ile aynı imzayı taşır ki REPL, TUI ve masaüstü turu çağıranı değiştirmeden
    bu yola geçebilsin. `extra_system`/`step_limit` gibi tur ayarları alt ajanın kendi
    kişilik notu ve bütçesiyle değiştirildiği için yok sayılır.
    """
    from .loop import AgentOutcome, run_agent
    from .team import SubTask, run_subagent

    snapshot = list(history or [])
    deps.live_history = lambda: snapshot
    subtask = SubTask(task=task.strip(), read_only=plan_mode, inherit_context=True)
    run = await run_subagent(deps, subtask, depth=0, run_agent=run_agent)
    messages = [*snapshot, Message("user", task), Message("assistant", run.text)]
    return AgentOutcome(
        final_text=run.text,
        messages=messages,
        ok=run.ok,
        tool_calls_made=run.tool_calls,
    )
