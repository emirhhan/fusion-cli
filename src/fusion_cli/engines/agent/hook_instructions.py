"""`InstructionsLoaded` kancası (#90): talimat dosyası bağlama girince (Claude Code).

Claude: oturum başında yüklenen `CLAUDE.md` / `.claude/rules/*.md` dosyaları için
`session_start`, iç içe klasör talimatı için `nested_traversal`, `paths:` kuralı için
`path_glob_match`, `@import` için `include`, sıkıştırmadan sonra yeniden yüklemede
`compact`. Eşleştirici `load_reason`'dır. Kanca engelleyemez ve beklenmez (gözlem içindir);
çıktısı yok sayılır. Aynı dosya oturumda bir kez bildirilir (Fusion talimatı her kök turda
yeniden kurar; kanca yalnız ilk yüklemede çalışır).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.hooks.events import HookEvent
from .hook_bridge import records_tools, session_of
from .instruction_layers import PROJECT_LOCAL, InstructionLoad
from .instruction_rules import RuleFile, discover_rules

if TYPE_CHECKING:
    from ..hooks.session import HookSession
    from .loop import AgentDeps

#: Oturum başı yükleme nedeni; sıkıştırmadan sonra `compact` olur.
SESSION_START_REASON = "session_start"
COMPACT_REASON = "compact"


def memory_type(path: Path, home: Path | None) -> str:
    """Claude `memory_type`: `User` (ev dizini), `Local` (`CLAUDE.local.md`), `Project`."""
    if path.name == PROJECT_LOCAL:
        return "Local"
    if home is not None:
        try:
            if path.resolve().is_relative_to(home.resolve()):
                return "User"
        except OSError:
            return "Project"
    return "Project"


def _active(deps: AgentDeps) -> HookSession | None:
    session = session_of(deps)
    if session is None or not records_tools(deps):
        return None
    if not session.has(HookEvent.INSTRUCTIONS_LOADED):
        return None
    return session


def _fire(
    session: HookSession, path: Path, reason: str, home: Path | None, extra: dict[str, object]
) -> None:
    key = str(path.resolve())
    if key in session.instructions_seen:
        return
    session.instructions_seen.add(key)
    fields: dict[str, object] = {
        "file_path": key,
        "memory_type": memory_type(path, home),
        "load_reason": reason,
        **extra,
    }
    session.spawn(
        lambda: session.emit(HookEvent.INSTRUCTIONS_LOADED, subjects=(reason,), fields=fields)
    )


def session_instructions(deps: AgentDeps, load: InstructionLoad) -> None:
    """Kök tur başında yüklenen talimat ve koşulsuz kural dosyalarını bildir."""
    session = _active(deps)
    if session is None:
        return
    home = getattr(deps, "home", None)
    rules: tuple[RuleFile, ...] = ()
    if getattr(deps.config.runtime, "instruction_merge", True):
        rules = discover_rules(deps.tool_context.root, home)
    reason = session.instructions_reason
    for item in load.files:
        if item.layer == "import" and reason != COMPACT_REASON:
            parent = getattr(item, "parent", None)
            extra: dict[str, object] = {"parent_file_path": str(parent)} if parent else {}
            _fire(session, item.path, "include", home, extra)
            continue
        _fire(session, item.path, reason, home, {})
    for rule in rules:
        if not rule.is_scoped:
            _fire(session, rule.path, reason, home, {})
    session.instructions_reason = SESSION_START_REASON


def nested_instructions(
    deps: AgentDeps,
    root: Path,
    loaded: Iterable[str],
    rules: Iterable[RuleFile],
    trigger: Path,
) -> None:
    """Dosya erişimiyle gelen iç içe talimat (`nested_traversal`) ve kural (`path_glob_match`)."""
    session = _active(deps)
    if session is None:
        return
    home = getattr(deps, "home", None)
    by_label = {rule.label: rule for rule in rules}
    for label in loaded:
        rule = by_label.get(label)
        extra: dict[str, object] = {"trigger_file_path": str(trigger)}
        if rule is not None:
            extra["globs"] = list(rule.paths)
            _fire(session, rule.path, "path_glob_match", home, extra)
        else:
            _fire(session, root / label, "nested_traversal", home, extra)
