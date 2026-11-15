"""Claude Code görev araçları: TaskCreate / TaskGet / TaskList / TaskUpdate (#329).

Claude Code (tools-reference › Task tools): bu dört araç, görev araçlarının açık olduğu
modellerde varsayılandır; TodoWrite yalnız `CLAUDE_CODE_ENABLE_TASKS=0` iken gelir. Hangi
modelde hangisinin sunulacağı `engines/agent/task_availability.py`'dedir.

Görevler `ToolContext.todos` listesinde yaşar (TodoWrite ile aynı liste): etkileşimli oturumda
liste oturum boyu kalır, `--resume` ile döner ve `CLAUDE_CODE_TASK_LIST_ID` ile paylaşılır
(#331). Kimlikler sıra numarasıdır ("1", "2"…). `metadata` ve `owner` kabul edilir ama
saklanmaz (Fusion'da ekip görev panosu yok).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from ..core.tools import TodoItem, TodoStatus, Tool, ToolArgs, ToolContext, ToolResult
from .args import ArgumentError

__all__ = ["TASK_TOOLS", "task_create", "task_get", "task_list", "task_update"]

_STRING = {"type": "string"}
_STRINGS = {"type": "array", "items": _STRING}
#: TaskUpdate'in kabul ettiği durumlar; `deleted` görevi listeden çıkarır.
_UPDATE_STATUSES = (*(status.value for status in TodoStatus), "deleted")


def _text(args: ToolArgs, key: str, *, required: bool = False) -> str:
    value = args.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if required:
        raise ArgumentError(f"'{key}' alanı boş olmayan bir metin olmalı.")
    return ""


def _find(context: ToolContext, task_id: str) -> TodoItem:
    for item in context.todos.items:
        if item.task_id == task_id:
            return item
    known = ", ".join(item.task_id for item in context.todos.items if item.task_id) or "yok"
    raise ArgumentError(f"Görev bulunamadı: {task_id}. Bilinen görevler: {known}.")


def _next_id(items: tuple[TodoItem, ...]) -> str:
    numbers = [int(item.task_id) for item in items if item.task_id.isdigit()]
    return str(max(numbers, default=0) + 1)


def task_create(args: ToolArgs, context: ToolContext) -> ToolResult:
    subject = _text(args, "subject", required=True)
    items = context.todos.items
    task = TodoItem(
        subject,
        TodoStatus.PENDING,
        _text(args, "activeForm"),
        task_id=_next_id(items),
        description=_text(args, "description"),
    )
    context.todos.replace((*items, task))
    return ToolResult(f"Görev #{task.task_id} oluşturuldu: {subject}")


def _blocks(context: ToolContext, task_id: str) -> tuple[str, ...]:
    return tuple(item.task_id for item in context.todos.items if task_id in item.blocked_by)


def task_get(args: ToolArgs, context: ToolContext) -> ToolResult:
    task = _find(context, _text(args, "taskId", required=True))
    lines = [f"#{task.task_id} {task.content}", f"Durum: {task.status.value}"]
    if task.description:
        lines.append(f"Açıklama: {task.description}")
    if task.blocked_by:
        lines.append("Bekledikleri: " + ", ".join(f"#{x}" for x in task.blocked_by))
    blocks = _blocks(context, task.task_id)
    if blocks:
        lines.append("Engelledikleri: " + ", ".join(f"#{x}" for x in blocks))
    return ToolResult("\n".join(lines))


def task_list(args: ToolArgs, context: ToolContext) -> ToolResult:
    tasks = [item for item in context.todos.items if item.task_id]
    if not tasks:
        return ToolResult("Görev yok.")
    lines = []
    for item in tasks:
        open_blockers = [
            blocker
            for blocker in item.blocked_by
            if any(
                other.task_id == blocker and other.status is not TodoStatus.COMPLETED
                for other in tasks
            )
        ]
        suffix = (
            f" (bekliyor: {', '.join('#' + x for x in open_blockers)})" if open_blockers else ""
        )
        lines.append(f"#{item.task_id} [{item.status.value}] {item.content}{suffix}")
    return ToolResult("\n".join(lines))


def _list_arg(args: ToolArgs, key: str) -> tuple[str, ...]:
    raw = args.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(x, str | int) for x in raw):
        raise ArgumentError(f"'{key}' görev kimliklerinden oluşan bir liste olmalı.")
    return tuple(str(x) for x in raw)


def _updated(task: TodoItem, args: ToolArgs, status: str) -> TodoItem:
    changes: dict[str, object] = {}
    if status:
        changes["status"] = TodoStatus(status)
    for key, field in (("subject", "content"), ("description", "description")):
        if _text(args, key):
            changes[field] = _text(args, key)
    if _text(args, "activeForm"):
        changes["active_form"] = _text(args, "activeForm")
    waits = _list_arg(args, "addBlockedBy")
    if waits:
        changes["blocked_by"] = tuple(dict.fromkeys((*task.blocked_by, *waits)))
    return replace(task, **changes)  # type: ignore[arg-type]


def task_update(args: ToolArgs, context: ToolContext) -> ToolResult:
    task = _find(context, _text(args, "taskId", required=True))
    status = _text(args, "status")
    if status and status not in _UPDATE_STATUSES:
        raise ArgumentError(f"'status' geçersiz; geçerli: {', '.join(_UPDATE_STATUSES)}.")
    blocks = _list_arg(args, "addBlocks")
    for other in blocks:
        _find(context, other)
    items: list[TodoItem] = []
    for item in context.todos.items:
        if item.task_id == task.task_id:
            if status != "deleted":
                items.append(_updated(item, args, status))
        elif item.task_id in blocks and task.task_id not in item.blocked_by:
            items.append(replace(item, blocked_by=(*item.blocked_by, task.task_id)))
        else:
            items.append(item)
    context.todos.replace(tuple(items))
    verb = "silindi" if status == "deleted" else "güncellendi"
    return ToolResult(f"Görev #{task.task_id} {verb}.")


def _tool(
    name: str,
    description: str,
    properties: dict[str, object],
    required: list[str],
    run: Callable[[ToolArgs, ToolContext], ToolResult],
) -> Tool:
    return Tool(
        name=name,
        description=description,
        parameters={"type": "object", "properties": properties, "required": required},
        run=run,
    )


TASK_TOOLS: tuple[Tool, ...] = (
    _tool(
        "task_create",
        "Görev listesine görev ekle.",
        {"subject": _STRING, "description": _STRING, "activeForm": _STRING, "metadata": {}},
        ["subject", "description"],
        task_create,
    ),
    _tool("task_get", "Görevin ayrıntısı.", {"taskId": _STRING}, ["taskId"], task_get),
    _tool("task_list", "Görevleri listele.", {}, [], task_list),
    _tool(
        "task_update",
        "Görevi güncelle (status: pending/in_progress/completed/deleted).",
        {
            "taskId": _STRING,
            "status": _STRING,
            "subject": _STRING,
            "description": _STRING,
            "activeForm": _STRING,
            "owner": _STRING,
            "addBlocks": _STRINGS,
            "addBlockedBy": _STRINGS,
            "metadata": {},
        },
        ["taskId"],
        task_update,
    ),
)
