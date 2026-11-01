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


#: Bağlamı özetlenmiş oturumlar: sonraki yüklemenin nedeni `compact` (#169).
_COMPACTED: set[int] = set()
#: Özetlemeden sonra yeniden bildirilen nedenler.
_RELOADED_REASONS = ("session_start", "include", "compact")


def mark_compacted(hooks: object | None) -> None:
    """Bağlam özetlendi: talimatlar yeniden yüklenince olay `compact` nedeniyle tekrar gider."""
    if hooks is None:
        return
    seen = _FIRED.get(id(hooks))
    if seen is not None:
        _FIRED[id(hooks)] = {key for key in seen if not key.startswith("startup:")}
    _COMPACTED.add(id(hooks))


def after_compact(
    hooks: object | None, events: Iterable[Mapping[str, object]]
) -> list[Mapping[str, object]]:
    """Özetlemeden sonraki ilk yüklemede `session_start`/`include` → `compact` (bir kez)."""
    items = list(events)
    if hooks is None or id(hooks) not in _COMPACTED:
        return items
    _COMPACTED.discard(id(hooks))
    return [
        {**fields, "load_reason": "compact"}
        if fields.get("load_reason") in _RELOADED_REASONS
        else fields
        for fields in items
    ]


def payload(path: str, layer: str, reason: str, **extra: str) -> dict[str, object]:
    """Claude Code ile aynı alan adları; boş isteğe bağlı alanlar gönderilmez."""
    fields: dict[str, object] = {
        "file_path": path,
        "memory_type": MEMORY_TYPES.get(layer, "Project"),
        "load_reason": reason,
    }
    fields.update({name: value for name, value in extra.items() if value})
    return fields


def _key(fields: Mapping[str, object]) -> str:
    """Tekilleştirme anahtarı: oturum başı / include / compact aynı yüklemedir."""
    reason = fields.get("load_reason")
    kind = "startup" if reason in _RELOADED_REASONS else str(reason)
    return f"{kind}:{fields.get('file_path')}"


def notify(hooks: object | None, events: Iterable[Mapping[str, object]]) -> None:
    """Yeni yüklenen her dosya için olayı arka planda gönder (çalışan döngü yoksa atla)."""
    emit = getattr(hooks, "emit", None) if hooks is not None else None
    if emit is None:
        return
    fresh = [fields for fields in events if _first_time(hooks, _key(fields))]
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
        parent = getattr(item, "parent", None) if reason == "include" else None
        result.append(
            payload(
                str(getattr(item, "path", "")),
                layer,
                reason,
                parent_file_path=str(parent) if parent is not None else "",
            )
        )
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
