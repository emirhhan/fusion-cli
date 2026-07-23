"""Görev listesi aracı.

Liste tur bazlıdır ve `ToolContext` üzerinden taşınır: alt-ajanlar ana ajanın
listesini ezmez. Ayrıca "iş yarım mı kaldı?" sezgiseli bu listeyi okur.
"""

from __future__ import annotations

from ..core.tools import TodoItem, TodoStatus, ToolArgs, ToolContext, ToolResult
from .args import ArgumentError, require_list


def todo_write(args: ToolArgs, context: ToolContext) -> ToolResult:
    items = parse_todos(require_list(args, "todos"))
    context.todos.replace(items)
    return ToolResult(context.todos.render() or "(görev listesi boş)")


def parse_todos(raw: object) -> tuple[TodoItem, ...]:
    """Ham liste → doğrulanmış görev maddeleri."""
    if not isinstance(raw, list):
        raise ArgumentError("'todos' bir liste olmalı.")
    items: list[TodoItem] = []
    for position, entry in enumerate(raw, 1):
        if not isinstance(entry, dict):
            raise ArgumentError(f"{position}. madde bir sözlük olmalı.")
        content = entry.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ArgumentError(f"{position}. madde: 'content' boş olamaz.")
        items.append(TodoItem(content=content.strip(), status=_status(entry.get("status"))))
    return tuple(items)


def _status(raw: object) -> TodoStatus:
    if not isinstance(raw, str):
        return TodoStatus.PENDING
    try:
        return TodoStatus(raw.strip().lower())
    except ValueError:
        # Bilinmeyen durum sessizce "beklemede" sayılır: modelin ufak bir yazım
        # hatası yüzünden planın tamamı reddedilmemeli.
        return TodoStatus.PENDING
