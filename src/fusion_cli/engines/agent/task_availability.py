"""Görev araçlarının hangi modelde sunulacağı (Claude Code tools-reference, #329).

Claude Code: TaskCreate/TaskGet/TaskList/TaskUpdate ve TodoWrite varsayılan olarak yalnız
Opus 4.7, Sonnet 4.6, Haiku 4.5 ve daha eski modellerde vardır; bu modellerde Task*
dörtlüsü varsayılandır, TodoWrite `CLAUDE_CODE_ENABLE_TASKS=0` (ya da `false`) ile gelir.
Diğer modellerde (Opus 4.8, Sonnet 5 ve sonrası; Claude dışı modeller) araçlar yoktur;
`CLAUDE_CODE_ENABLE_TODO_TOOLS=1` her modelde açar, `--allowedTools`/`--tools` ile adı
verilen araç da sunulur (`_permitted` açıkça istenen adı süzmez).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

__all__ = [
    "TASK_TOOL_NAMES",
    "TODO_TOOL_NAME",
    "hidden_task_tools",
    "task_tool_mode",
]

TASK_TOOL_NAMES = frozenset({"task_create", "task_get", "task_list", "task_update"})
TODO_TOOL_NAME = "todo_write"
#: Varsayılanda görev araçlarının açık olduğu son sürümler (aile → (ana, ara)).
_LAST_DEFAULT_ON = {"opus": (4, 7), "sonnet": (4, 6), "haiku": (4, 5)}
_FAMILY_VERSION = re.compile(r"claude-(opus|sonnet|haiku)-(\d+)(?:[-.](\d+))?")
_VERSION_FAMILY = re.compile(r"claude-(\d+)(?:[-.](\d+))?-(opus|sonnet|haiku)")
_OFF = {"0", "false", "no", "off"}


def _legacy_claude(model: str) -> bool:
    """Görev araçlarının varsayılan açık olduğu (eski) Claude modeli mi?"""
    name = model.lower()
    if "claude" not in name:
        return False
    if re.search(r"claude-(?:2|instant|1)\b|claude-(?:2|1)[-.]", name):
        return True
    match = _FAMILY_VERSION.search(name)
    if match is not None:
        family, major, minor = match.group(1), int(match.group(2)), match.group(3)
    else:
        legacy = _VERSION_FAMILY.search(name)
        if legacy is None:
            return False
        major, minor, family = int(legacy.group(1)), legacy.group(2), legacy.group(3)
    # `claude-sonnet-4-20250514` biçiminde ikinci sayı tarihtir, ara sürüm değil.
    minor_value = int(minor) if minor is not None and len(minor) <= 2 else 0
    return (major, minor_value) <= _LAST_DEFAULT_ON[family]


def task_tool_mode(model: str, env: Mapping[str, str] | None = None) -> str:
    """`tasks` (Task* dörtlüsü), `todo` (todo_write) ya da `none`."""
    source = os.environ if env is None else env
    forced = source.get("CLAUDE_CODE_ENABLE_TODO_TOOLS", "").strip().lower() in {"1", "true"}
    if not forced and not _legacy_claude(model):
        return "none"
    if source.get("CLAUDE_CODE_ENABLE_TASKS", "").strip().lower() in _OFF:
        return "todo"
    return "tasks"


def hidden_task_tools(mode: str) -> frozenset[str]:
    """Bu kipte sunulmayan görev aracı adları."""
    if mode == "tasks":
        return frozenset({TODO_TOOL_NAME})
    if mode == "todo":
        return TASK_TOOL_NAMES
    return TASK_TOOL_NAMES | {TODO_TOOL_NAME}
