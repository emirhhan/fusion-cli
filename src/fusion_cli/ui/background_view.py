"""Arka plan görevleri ve açık oturumlar için terminal görünümleri (P-048, P-060).

`fusion agents` tabloyu, REPL `/tasks` ve `/list-agents` düz metin satırlarını buradan alır;
iki yüzey aynı durum adlarını ve sırayı gösterir (Claude Code agent view grupları:
girdi bekleyen → çalışan → biten).
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from rich.table import Table

from ..core.background_tasks import BackgroundTask, TaskStatus
from ..core.peers import PeerMessage, PeerRecord
from . import background_messages as texts
from . import theme

#: Gruplama sırası: kullanıcıdan bir şey bekleyen en üstte.
_GROUP_ORDER: dict[TaskStatus, int] = {
    TaskStatus.NEEDS_INPUT: 0,
    TaskStatus.WORKING: 1,
    TaskStatus.QUEUED: 2,
    TaskStatus.LOST: 3,
    TaskStatus.FAILED: 4,
    TaskStatus.COMPLETED: 5,
    TaskStatus.STOPPED: 6,
}
#: Durum → tema sabitinin ADI; renk çizimde okunur (tema `/theme` ile değişebilir).
_STATUS_STYLE: dict[TaskStatus, str] = {
    TaskStatus.NEEDS_INPUT: "WARN",
    TaskStatus.WORKING: "ACCENT",
    TaskStatus.QUEUED: "DIM",
    TaskStatus.LOST: "ERROR",
    TaskStatus.FAILED: "ERROR",
    TaskStatus.COMPLETED: "OK",
    TaskStatus.STOPPED: "DIM",
}


def ordered(tasks: Sequence[BackgroundTask]) -> list[BackgroundTask]:
    return sorted(tasks, key=lambda task: (_GROUP_ORDER[task.status], -task.created_at))


def status_label(task: BackgroundTask) -> str:
    return texts.BG_STATUS_LABELS.get(task.status.value, task.status.value)


def age(seconds: float) -> str:
    """Kısa geçen süre: 45 sn, 12 dk, 3 sa, 2 gün."""
    value = max(0, int(seconds))
    for size, unit in ((86_400, "gün"), (3_600, "sa"), (60, "dk")):
        if value >= size:
            return f"{value // size} {unit}"
    return f"{value} sn"


def detail_text(task: BackgroundTask) -> str:
    return task.question or task.summary or task.note or task.prompt


def task_table(tasks: Sequence[BackgroundTask], *, now: float | None = None) -> Table:
    """`fusion agents` tablosu."""
    moment = time.time() if now is None else now
    table = Table(title=texts.BG_TABLE_TITLE, expand=True, show_lines=False)
    for header in texts.BG_TABLE_HEADERS:
        table.add_column(header, overflow="fold")
    for task in ordered(tasks):
        style = getattr(theme, _STATUS_STYLE[task.status])
        table.add_row(
            task.id,
            task.name,
            f"[{style}]{status_label(task)}[/{style}]",
            age(moment - task.updated_at),
            detail_text(task)[:120],
        )
    return table


def task_lines(tasks: Sequence[BackgroundTask], *, now: float | None = None) -> str:
    """REPL `/tasks` çıktısı: her görev bir satır; boşsa kullanım ipucu."""
    if not tasks:
        return texts.BG_TASKS_EMPTY
    moment = time.time() if now is None else now
    lines = [texts.BG_TASKS_HEADER]
    for task in ordered(tasks):
        lines.append(
            texts.BG_TASK_LINE.format(
                id=task.id,
                name=task.name,
                status=status_label(task),
                age=age(moment - task.updated_at),
                detail=detail_text(task)[:100],
            )
        )
    lines.append(texts.BG_TASKS_HINT)
    return "\n".join(lines)


def task_detail(task: BackgroundTask, result: str, log_tail: str) -> str:
    """Tek görevin ayrıntısı (`/tasks show`, `fusion agents goster`)."""
    parts = [
        texts.BG_DETAIL_HEADER.format(id=task.id, name=task.name, status=status_label(task)),
        texts.BG_DETAIL_META.format(
            origin=task.origin, mode=task.mode, turns=task.turns, root=task.root
        ),
        texts.BG_DETAIL_PROMPT.format(prompt=task.prompt[:600]),
    ]
    if task.question:
        parts.append(texts.BG_DETAIL_NEEDS_INPUT.format(question=task.question))
    if task.note:
        parts.append(texts.BG_DETAIL_NOTE.format(note=task.note))
    if result:
        parts.append(texts.BG_DETAIL_RESULT.format(result=result))
    if log_tail:
        parts.append(texts.BG_DETAIL_LOG.format(log=log_tail))
    return "\n".join(parts)


def peer_lines(peers: Sequence[PeerRecord], held: Sequence[PeerMessage], self_id: str) -> str:
    """REPL `/list-agents`: açık oturumlar + bekletilen gelen mesajlar."""
    lines = [texts.PEER_LIST_HEADER]
    others = [peer for peer in peers if peer.id != self_id]
    lines.extend(
        texts.PEER_LINE.format(id=peer.id, name=peer.name, kind=peer.kind, root=peer.root)
        for peer in others
    )
    if not others:
        lines.append(texts.PEER_LIST_NONE)
    if held:
        lines.append(texts.PEER_HELD_HEADER)
        lines.extend(
            texts.PEER_HELD_LINE.format(
                no=index, sender=message.sender_name, text=message.text[:80]
            )
            for index, message in enumerate(held, start=1)
        )
        lines.append(texts.PEER_HELD_HINT)
    lines.append(texts.PEER_SEND_HINT)
    return "\n".join(lines)
