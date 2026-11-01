"""`InstructionsLoaded` kancası (Claude Code #169; code.claude.com/docs/en/hooks).

Claude Code bir CLAUDE.md ya da `.claude/rules/*.md` dosyası bağlama girdiğinde
`InstructionsLoaded` olayını gönderir: `file_path`, `memory_type` (User | Project | Local |
Managed), `load_reason` (session_start | nested_traversal | path_glob_match | include |
compact), isteğe bağlı `globs`, `trigger_file_path`, `parent_file_path`. Eşleştirici
`load_reason`'a bakar; olay yalnız gözlem içindir, kararı yoktur ve turu bekletmez.

Fusion talimatları her tur yeniden okur; olay oturum başına dosya başına bir kez gider.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping
from typing import Any

from ...core.hooks.events import HookEvent

_LOG = logging.getLogger(__name__)

#: Fusion katman adı → Claude `memory_type`.
MEMORY_TYPES = {
    "kurumsal": "Managed",
    "kullanici": "User",
    "proje": "Project",
    "yerel": "Local",
    "import": "Project",
    "ek-dizin": "Project",
}

#: Oturum (kanca nesnesi) başına bildirilmiş dosyalar; sınırsız büyümesin.
_FIRED: dict[int, set[str]] = {}
_MAX_SESSIONS = 64
_TASKS: set[asyncio.Task[Any]] = set()


def _first_time(hooks: object, key: str) -> bool:
    seen = _FIRED.setdefault(id(hooks), set())
    if len(_FIRED) > _MAX_SESSIONS:
        _FIRED.pop(next(iter(_FIRED)))
    if key in seen:
        return False
    seen.add(key)
    return True


def payload(path: str, layer: str, reason: str, **extra: str) -> dict[str, object]:
    """Claude Code ile aynı alan adları; boş isteğe bağlı alanlar gönderilmez."""
    fields: dict[str, object] = {
        "file_path": path,
        "memory_type": MEMORY_TYPES.get(layer, "Project"),
        "load_reason": reason,
    }
    fields.update({name: value for name, value in extra.items() if value})
    return fields


def notify(hooks: object | None, events: Iterable[Mapping[str, object]]) -> None:
    """Yeni yüklenen her dosya için olayı arka planda gönder (çalışan döngü yoksa atla)."""
    emit = getattr(hooks, "emit", None) if hooks is not None else None
    if emit is None:
        return
    fresh = [
        fields
        for fields in events
        if _first_time(hooks, f"{fields.get('load_reason')}:{fields.get('file_path')}")
    ]
    if not fresh:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    for fields in fresh:
        task = loop.create_task(
            emit(
                HookEvent.INSTRUCTIONS_LOADED,
                subjects=(str(fields["load_reason"]),),
                fields=dict(fields),
            )
        )
        _TASKS.add(task)
        task.add_done_callback(_done)


def _done(task: asyncio.Task[Any]) -> None:
    _TASKS.discard(task)
    if not task.cancelled() and task.exception() is not None:
        _LOG.warning("InstructionsLoaded kancası başarısız: %s", task.exception())


def startup_events(files: Iterable[object]) -> list[dict[str, object]]:
    """Tur başı yüklenen katman dosyaları → olay yükleri (`import` katmanı `include`)."""
    result = []
    for item in files:
        layer = str(getattr(item, "layer", ""))
        reason = "include" if layer == "import" else "session_start"
        result.append(payload(str(getattr(item, "path", "")), layer, reason))
    return result


def rule_startup_events(rules: Iterable[object]) -> list[dict[str, object]]:
    """Oturum başında yüklenen `paths`'siz `.claude/rules` dosyaları (#169)."""
    return [
        payload(str(getattr(rule, "path", "")), _rule_layer(rule), "session_start")
        for rule in rules
        if not getattr(rule, "paths", ())
    ]


def nested_event(
    root: object, rel: str, trigger: str, rules: Iterable[object]
) -> dict[str, object]:
    """Dosya erişiminde yüklenen talimat: `paths` eşleşen kural `path_glob_match` + `globs`."""
    from pathlib import Path

    for rule in rules:
        if getattr(rule, "label", None) == rel and getattr(rule, "paths", ()):
            fields = payload(
                str(getattr(rule, "path", "")),
                _rule_layer(rule),
                "path_glob_match",
                trigger_file_path=trigger,
            )
            return {**fields, "globs": list(getattr(rule, "paths", ()))}
    return payload(
        str(Path(str(root)) / rel), "proje", "nested_traversal", trigger_file_path=trigger
    )


def _rule_layer(rule: object) -> str:
    return "kullanici" if getattr(rule, "trusted", False) else "proje"
