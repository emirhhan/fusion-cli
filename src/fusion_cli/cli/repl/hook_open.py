"""REPL/TUI açılışında `SessionStart` (#111): Claude Code oturum başlarken çalıştırır.

Kanca bağlamı ilk isteme eklenir (`HookSession.open`); `systemMessage` ve engellemeyen
hatalar açılış ekranında gösterilir. SessionStart kancası yoksa oturum açılmış sayılmaz,
ilk istemdeki yol (`hook_bridge.user_prompt_submit`) eskisi gibi çalışır.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.markup import escape

from ...core.hooks.events import HookEvent, HookVerdict
from ...engines.hooks.setup_hook import run_setup
from ...ui import messages, theme

if TYPE_CHECKING:
    from .state import ReplState


async def open_hooks(state: ReplState, console: Console, *, setup_trigger: str = "") -> None:
    """Tanımlı SessionStart kancalarını oturum açılırken çalıştır.

    `setup_trigger` (`--init`/`--maintenance`) verildiyse önce `Setup` kancaları (#90).
    """
    session = state.hooks()
    if state.persona is not None:
        session.agent_type = state.persona.name
    session.refresh()
    if setup_trigger:
        show_verdict(await run_setup(session, setup_trigger), console)
    if not session.has(HookEvent.SESSION_START):
        return
    show_verdict(await session.open(), console)


def show_verdict(verdict: HookVerdict, console: Console) -> None:
    """Açılış kancasının `systemMessage` satırları ve engellemeyen hataları."""
    for text in verdict.system_messages:
        line = messages.HOOKS_SYSTEM.format(text=text)
        console.print(f"[{theme.DIM}]{escape(line)}[/{theme.DIM}]")
    for detail in verdict.errors:
        line = messages.HOOKS_ERROR.format(detail=detail)
        console.print(f"[{theme.WARN}]{escape(line)}[/{theme.WARN}]")
