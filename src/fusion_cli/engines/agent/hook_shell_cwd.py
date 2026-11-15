"""Kalıcı kabuk dizini ↔ kanca oturumu (#126): Bash `cd`'si `CwdChanged` tetikler.

Claude Code: "CwdChanged — when the working directory changes, for example when Claude
executes a `cd` command". Tur bağlamı (`ToolContext`) her turda yeniden kurulur; ana
konuşmanın dizini oturumda (`HookSession.shell_cwd`) saklanır ve her araç çağrısından
ÖNCE (onay denetimi de aynı dizini görsün diye) bağlama aktarılır. Kabuk komutu dizini
değiştirdiyse oturuma yazılır ve `CwdChanged(old_cwd, new_cwd)` gönderilir; alt ajanın
`cd`'si ana konuşmanın dizinini değiştirmez (ana ajanın sıradaki çağrısı geri yükler).
"""

from __future__ import annotations

from ...core.hooks.events import HookEvent, HookVerdict
from ...core.shell_cwd import ShellCwd
from ...core.tools import ToolFamily, tool_family
from ..hooks.session import NO_VERDICT, HookSession


def _holder(tool_context: object) -> ShellCwd | None:
    holder = getattr(tool_context, "shell_cwd", None)
    return holder if isinstance(holder, ShellCwd) else None


def adopt(tool_context: object, session: HookSession) -> None:
    """Ana ajanın çağrısından önce: oturumun kabuk dizini tur bağlamına."""
    holder = _holder(tool_context)
    if holder is None:
        return
    holder.path = session.shell_cwd
    holder.changed = None


async def after_tool(tool_context: object, session: HookSession, tool_name: str) -> HookVerdict:
    """Ana ajanın kabuk komutu dizini değiştirdiyse oturuma yaz ve `CwdChanged` gönder."""
    holder = _holder(tool_context)
    if holder is None or tool_family(tool_name) is not ToolFamily.SHELL:
        return NO_VERDICT
    change, holder.changed = holder.changed, None
    session.shell_cwd = holder.path
    if change is None:
        return NO_VERDICT
    old, new = change
    return await session.emit(
        HookEvent.CWD_CHANGED, fields={"old_cwd": str(old), "new_cwd": str(new)}
    )
