"""REPL/TUI açılışında `SessionStart` (#111): Claude Code oturum başlarken çalıştırır.

Kanca bağlamı ilk isteme eklenir (`HookSession.open`); `systemMessage` ve engellemeyen
hatalar açılış ekranında gösterilir. SessionStart kancası yoksa oturum açılmış sayılmaz,
ilk istemdeki yol (`hook_bridge.user_prompt_submit`) eskisi gibi çalışır.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape

from ...core.hooks.events import HookEvent
from ...ui import messages, theme

if TYPE_CHECKING:
    from .state import ReplState


async def open_hooks(state: ReplState, console: Console) -> None:
    """Tanımlı SessionStart kancalarını oturum açılırken çalıştır."""
    session = state.hooks()
    session.refresh()
    if not session.has(HookEvent.SESSION_START):
        return
    verdict = await session.open()
    for text in verdict.system_messages:
        line = messages.HOOKS_SYSTEM.format(text=text)
        console.print(f"[{theme.DIM}]{escape(line)}[/{theme.DIM}]")
    for detail in verdict.errors:
        line = messages.HOOKS_ERROR.format(detail=detail)
        console.print(f"[{theme.WARN}]{escape(line)}[/{theme.WARN}]")
