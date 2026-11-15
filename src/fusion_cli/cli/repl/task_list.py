"""Oturum boyu yaşayan görev listesi (Claude Code task list, #331).

Claude Code (interactive-mode › Task list): liste oturum boyunca yaşar ve `--resume` ile geri
gelir; `CLAUDE_CODE_TASK_LIST_ID=<ad>` verilirse `~/.claude/tasks/<ad>/` dizini üzerinden
oturumlar arasında paylaşılır. Fusion'da liste her turda boş başlıyordu (`ToolContext.todos`).

`StoredTodoList` her `todo_write`'ta diske yazar ve okurken dosya değiştiyse yeniden yükler
(paylaşılan listede başka oturumun yazdığı görünür). Yer:
- `CLAUDE_CODE_TASK_LIST_ID` varsa `<claude kullanıcı dizini>/tasks/<ad>/fusion-todos.json`
  (Claude'un kendi görev dosyalarıyla çakışmasın diye Fusion'a özgü ad);
- yoksa `<memory_dir>/tasks/<sohbet kimliği>.json` — sohbet sürdürülünce aynı dosya okunur.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path

from ...config.claude_home import claude_user_dir
from ...core.tools import TodoItem, TodoList, TodoStatus

__all__ = ["TASK_LIST_ID_ENV", "StoredTodoList", "session_todos", "task_list_path"]

_LOG = logging.getLogger(__name__)
TASK_LIST_ID_ENV = "CLAUDE_CODE_TASK_LIST_ID"
_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


def task_list_path(memory_dir: Path, conversation_id: str) -> Path:
    """Bu sohbetin görev listesi dosyası (paylaşılan liste kimliği önce)."""
    shared = os.environ.get(TASK_LIST_ID_ENV, "").strip()
    if shared:
        return claude_user_dir() / "tasks" / _SAFE_ID.sub("_", shared) / "fusion-todos.json"
    return Path(memory_dir) / "tasks" / f"{_SAFE_ID.sub('_', conversation_id)}.json"


class StoredTodoList(TodoList):
    """Diske yazılan, dosya değişince yeniden okunan görev listesi.

    Otomatik devam (`has_pending`) yalnız bu turda yazılmış listeye bakar: önceki turdan kalan
    yarım liste ilgisiz yeni bir isteği "devam et" diye uzatmasın (eski tur bazlı davranış).
    """

    def __init__(self, locate: Callable[[], Path]) -> None:
        super().__init__()
        self._locate = locate
        self._loaded: tuple[Path, float] | None = None
        self._written_this_turn = False

    def begin_turn(self) -> None:
        """Yeni tur: önceki turdan kalan bekleyen maddeler otomatik devamı tetiklemez."""
        self._written_this_turn = False

    def replace(self, items: tuple[TodoItem, ...]) -> None:
        super().replace(items)
        self._written_this_turn = True
        path = self._locate()
        payload = [_dump(item) for item in items]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
            self._loaded = (path, path.stat().st_mtime)
        except OSError as error:
            _LOG.warning("Görev listesi kaydedilemedi (%s): %s", path, error)

    def _refresh(self) -> None:
        path = self._locate()
        try:
            stamp = path.stat().st_mtime
        except OSError:
            if self._loaded is not None and self._loaded[0] != path:
                super().replace(())
                self._loaded = None
            return
        if self._loaded == (path, stamp):
            return
        self._loaded = (path, stamp)
        super().replace(_read(path))

    @property
    def items(self) -> tuple[TodoItem, ...]:
        self._refresh()
        return super().items

    @property
    def pending_count(self) -> int:
        """Bu turda yazılmış listenin bekleyenleri (otomatik devam bütçesi; eski tur kuralı)."""
        if not self._written_this_turn:
            return 0
        return sum(1 for item in self.items if item.status is not TodoStatus.COMPLETED)

    @property
    def has_pending(self) -> bool:
        return self.pending_count > 0

    def render(self) -> str:
        return "\n".join(f"{item.status.icon} {item.label}" for item in self.items)


def _dump(item: TodoItem) -> dict[str, object]:
    payload: dict[str, object] = {
        "content": item.content,
        "status": item.status.value,
        "activeForm": item.active_form,
    }
    if item.task_id:  # Task* araçlarının alanları (#329)
        payload.update(id=item.task_id, description=item.description, blockedBy=item.blocked_by)
    return payload


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _read(path: Path) -> tuple[TodoItem, ...]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _LOG.warning("Görev listesi okunamadı; boş başlandı: %s", path)
        return ()
    items: list[TodoItem] = []
    for entry in raw if isinstance(raw, list) else ():
        if not isinstance(entry, dict) or not isinstance(entry.get("content"), str):
            continue
        try:
            active = entry.get("activeForm")
            blocked = entry.get("blockedBy")
            items.append(
                TodoItem(
                    entry["content"],
                    TodoStatus(entry.get("status")),
                    active if isinstance(active, str) else "",
                    task_id=_text(entry.get("id")),
                    description=_text(entry.get("description")),
                    blocked_by=tuple(str(x) for x in blocked) if isinstance(blocked, list) else (),
                )
            )
        except ValueError:
            continue
    return tuple(items)


def session_todos(state: object, *, new_turn: bool = True) -> TodoList:
    """Oturumun (ReplState) kalıcı görev listesi; ilk çağrıda kurulur, tur başını işaretler."""
    existing = getattr(state, "todos", None)
    if isinstance(existing, StoredTodoList):
        if new_turn:
            existing.begin_turn()
        return existing
    if isinstance(existing, TodoList):
        return existing
    todos = StoredTodoList(
        lambda: task_list_path(
            getattr(getattr(state, "config", None), "memory_dir", Path()),
            str(getattr(state, "conversation_id", "")),
        )
    )
    with contextlib.suppress(AttributeError):
        state.todos = todos  # type: ignore[attr-defined]
    return todos
