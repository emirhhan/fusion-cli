"""Görev listesi aracı.

Liste tur bazlıdır ve `ToolContext` üzerinden taşınır: alt-ajanlar ana ajanın
listesini ezmez. Ayrıca "iş yarım mı kaldı?" sezgiseli bu listeyi okur.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.tools import TodoItem, TodoStatus, ToolArgs, ToolContext, ToolResult
from .args import ArgumentError, require_list


def todo_write(args: ToolArgs, context: ToolContext) -> ToolResult:
    raw = require_list(args, "todos")
    items = parse_todos(raw)
    context.todos.replace(items)
    output = context.todos.render() or "(görev listesi boş)"
    bilinmeyen = _unknown_statuses(raw)
    if bilinmeyen:
        output += (
            f"\nNOT: tanınmayan durum {', '.join(repr(d) for d in bilinmeyen)} 'beklemede' "
            "sayıldı. Geçerli durumlar: pending, in_progress, completed."
        )
    return ToolResult(output)


def parse_todos(raw: object) -> tuple[TodoItem, ...]:
    """Ham liste → doğrulanmış görev maddeleri."""
    if not isinstance(raw, list):
        raise ArgumentError("'todos' bir liste olmalı.")
    items: list[TodoItem] = []
    for position, entry in enumerate(raw, 1):
        if not isinstance(entry, dict):
            raise ArgumentError(f"{position}. madde bir sözlük olmalı.")
        content = next(
            (entry[key] for key in _CONTENT_KEYS if isinstance(entry.get(key), str)), None
        )
        if not isinstance(content, str) or not content.strip():
            raise ArgumentError(f"{position}. madde: 'content' boş olamaz.")
        items.append(TodoItem(content=content.strip(), status=_status(entry.get("status"))))
    return tuple(items)


#: `content` yerine zayıf modellerin yazdığı alan adları.
_CONTENT_KEYS = ("content", "task", "title", "text", "step", "description")

#: Zayıf modellerin ürettiği durum eş anlamlıları. Ölçüldü (30 Ekim): `done`/`in-progress`
#: sessizce `pending` oluyor, "iş yarım" sezgiseli bitmiş işi bitmemiş sayıyordu.
_STATUS_SYNONYMS = {
    "done": TodoStatus.COMPLETED,
    "complete": TodoStatus.COMPLETED,
    "finished": TodoStatus.COMPLETED,
    "finish": TodoStatus.COMPLETED,
    "x": TodoStatus.COMPLETED,
    "tamamlandi": TodoStatus.COMPLETED,
    "tamamlandı": TodoStatus.COMPLETED,
    "doing": TodoStatus.IN_PROGRESS,
    "active": TodoStatus.IN_PROGRESS,
    "started": TodoStatus.IN_PROGRESS,
    "working": TodoStatus.IN_PROGRESS,
    "todo": TodoStatus.PENDING,
    "waiting": TodoStatus.PENDING,
    "not_started": TodoStatus.PENDING,
}


def _lookup_status(raw: str) -> TodoStatus | None:
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return TodoStatus(key)
    except ValueError:
        return _STATUS_SYNONYMS.get(key)


def _status(raw: object) -> TodoStatus:
    if not isinstance(raw, str):
        return TodoStatus.PENDING
    # Bilinmeyen durum sessizce "beklemede" sayılır: modelin ufak bir yazım
    # hatası yüzünden planın tamamı reddedilmemeli (`todo_write` sonuca not düşer).
    return _lookup_status(raw) or TodoStatus.PENDING


def _unknown_statuses(raw: Sequence[object]) -> list[str]:
    return [
        entry["status"]
        for entry in raw
        if isinstance(entry, dict)
        and isinstance(entry.get("status"), str)
        and entry["status"].strip()
        and _lookup_status(entry["status"]) is None
    ]
