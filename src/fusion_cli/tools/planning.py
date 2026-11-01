"""Görev listesi aracı.

Liste `ToolContext` üzerinden taşınır: alt-ajanlar ana ajanın listesini ezmez. Etkileşimli
oturumda liste oturum boyu yaşar ve diske yazılır (`cli/repl/task_list`, #331). "İş yarım mı
kaldı?" sezgiseli yalnız bu turda yazılmış listeye bakar.
"""

from __future__ import annotations

from ..core.tools import TodoItem, TodoStatus, ToolArgs, ToolContext, ToolResult
from .args import ArgumentError, require_list


def todo_write(args: ToolArgs, context: ToolContext) -> ToolResult:
    raw = require_list(args, "todos")
    items = parse_todos(raw)
    context.todos.replace(items)
    return ToolResult(context.todos.render() or "(görev listesi boş)")


#: Claude Code'daki geçerli durumlar; eş anlamlı ya da alternatif alan adı yok (#355).
VALID_STATUSES = tuple(status.value for status in TodoStatus)


def parse_todos(raw: object) -> tuple[TodoItem, ...]:
    """Ham liste → doğrulanmış görev maddeleri (Claude şeması: `content`, `status`, `activeForm`).

    Eski Fusion davranışı (1 Kasım öncesi): `done`/`doing`/`tamamlandı` gibi durum eş
    anlamlıları ve `task`/`title`/`text`/`step`/`description` alan adları kabul ediliyordu.
    Claude'da bunlar şema hatasıdır; model hatayı görüp düzeltir.
    """
    if not isinstance(raw, list):
        raise ArgumentError("'todos' bir liste olmalı.")
    items: list[TodoItem] = []
    for position, entry in enumerate(raw, 1):
        if not isinstance(entry, dict):
            raise ArgumentError(f"{position}. madde bir sözlük olmalı.")
        content = entry.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ArgumentError(f"{position}. madde: 'content' boş olamaz.")
        active = entry.get("activeForm")
        items.append(
            TodoItem(
                content=content.strip(),
                status=_status(entry.get("status"), position),
                active_form=active.strip() if isinstance(active, str) else "",
            )
        )
    return tuple(items)


def _status(raw: object, position: int) -> TodoStatus:
    if isinstance(raw, str):
        try:
            return TodoStatus(raw)
        except ValueError:
            pass
    raise ArgumentError(
        f"{position}. madde: 'status' {raw!r} geçersiz; geçerli: {', '.join(VALID_STATUSES)}."
    )
