"""Ctrl+T görev listesi görünümü (Claude Code interactive-mode › Task list, #330).

Claude Code: Ctrl+T görev listesini durum alanında açar/kapatır, en çok 5 madde gösterir;
liste açık bırakılırsa `--resume`/`--continue` sonrası açık gelir. Açık/kapalı durumu
oturumun görev listesi dosyasının yanında saklanır (`<liste>.view.json`).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ...core.tools import TodoItem, TodoStatus
from .task_list import session_todos, task_list_path

__all__ = ["MAX_VISIBLE_TASKS", "is_visible", "task_lines", "toggle_visible"]

_LOG = logging.getLogger(__name__)
MAX_VISIBLE_TASKS = 5


def _view_path(state: object) -> Path:
    config = getattr(state, "config", None)
    memory = getattr(config, "memory_dir", Path())
    return task_list_path(memory, str(getattr(state, "conversation_id", ""))).with_suffix(
        ".view.json"
    )


def is_visible(state: object) -> bool:
    """Liste açık mı (sürdürülen oturumda son durum)?"""
    try:
        data = json.loads(_view_path(state).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("visible") is True


def toggle_visible(state: object) -> bool:
    """Görünürlüğü çevir ve sakla; yeni durumu döndür."""
    visible = not is_visible(state)
    path = _view_path(state)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"visible": visible}), encoding="utf-8")
    except OSError as error:
        _LOG.warning("Görev listesi görünümü kaydedilemedi (%s): %s", path, error)
    return visible


def _order(items: tuple[TodoItem, ...]) -> list[TodoItem]:
    """Süren ve bekleyen maddeler önce (en çok 5 satıra sığsın), sonra bitenler."""
    rank = {TodoStatus.IN_PROGRESS: 0, TodoStatus.PENDING: 1, TodoStatus.COMPLETED: 2}
    return sorted(items, key=lambda item: rank[item.status])


def task_lines(state: object) -> list[str]:
    """Durum alanı satırları: en çok 5 madde ve taşan sayı; liste boşsa tek bilgi satırı."""
    items = session_todos(state, new_turn=False).items
    if not items:
        return ["Görev listesi boş"]
    ordered = _order(items)
    lines = [f"{item.status.icon} {item.label}" for item in ordered[:MAX_VISIBLE_TASKS]]
    if len(ordered) > MAX_VISIBLE_TASKS:
        lines.append(f"… +{len(ordered) - MAX_VISIBLE_TASKS} görev daha")
    return lines
