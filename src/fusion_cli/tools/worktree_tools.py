"""`enter_worktree` / `exit_worktree` araçları (Claude Code'daki EnterWorktree/ExitWorktree).

Araç çalışma ağacını kurar ve isteği `ToolContext.worktree_switch`'e bırakır; kökü
değiştirmek REPL'in işidir (tur bitince, bkz. `cli/repl/worktrees.apply_switch`). Aynı
tur içinde model dosyalara `.claude/worktrees/<ad>/…` göreli yoluyla ulaşır — bu yol kökün
içindedir, kısıtlı kip bozulmaz.
"""

from __future__ import annotations

import asyncio

from ..core.errors import WorktreeError
from ..core.tools import ToolArgs, ToolContext, ToolResult
from ..config.worktree_settings import enter_configured_worktree
from ..core.worktree import WORKTREE_DIR, worktree_for_path
from ..ui import messages

ENTER_WORKTREE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "çalışma ağacının adı (harf/rakam, nokta, alt çizgi, tire); "
            "dal worktree-<ad> olur",
        }
    },
    "required": ["name"],
}

EXIT_WORKTREE_SCHEMA: dict[str, object] = {"type": "object", "properties": {}, "required": []}


async def enter_worktree_tool(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Adı verilen git çalışma ağacını aç (yoksa oluştur) ve tur sonunda köke geçilmesini iste."""
    name = args.get("name")
    if not isinstance(name, str) or not name.strip():
        return ToolResult.failure("'name' boş olmayan bir metin olmalı.")
    if worktree_for_path(context.root) is not None:
        return ToolResult.failure(
            "Zaten bir çalışma ağacındasın; iç içe ağaç açılmaz. Önce exit_worktree çağır."
        )
    try:
        worktree = await asyncio.to_thread(enter_configured_worktree, context.root, name)
    except WorktreeError as error:
        return ToolResult.failure(str(error))
    context.worktree_switch.request(worktree)
    relative = WORKTREE_DIR / worktree.name
    return ToolResult(
        messages.WORKTREE_TOOL_ENTERED.format(
            path=worktree.path, branch=worktree.branch, relative=relative
        )
    )


async def exit_worktree_tool(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Tur sonunda ana depoya dönülmesini iste; temiz ağaç kaldırılır, iş kalmışsa korunur."""
    del args
    inside = worktree_for_path(context.root)
    if inside is None:
        return ToolResult(messages.WORKTREE_TOOL_NOT_IN)
    context.worktree_switch.request_exit()
    return ToolResult(messages.WORKTREE_TOOL_EXIT.format(origin=inside.origin))
