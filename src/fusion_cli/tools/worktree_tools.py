"""`enter_worktree` / `exit_worktree` araçları (Claude Code'daki EnterWorktree/ExitWorktree).

Araç çalışma ağacını kurar ve isteği `ToolContext.worktree_switch`'e bırakır; kökü
değiştirmek REPL'in işidir (tur bitince, bkz. `cli/repl/worktrees.apply_switch`). Aynı
tur içinde model dosyalara `.claude/worktrees/<ad>/…` göreli yoluyla ulaşır — bu yol kökün
içindedir, kısıtlı kip bozulmaz.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..config.worktree_settings import enter_configured_worktree
from ..core.errors import WorktreeError
from ..core.tools import ToolArgs, ToolContext, ToolResult
from ..core.worktree import Worktree, WorktreeHookCalls, worktree_for_path
from ..core.worktree_attach import attach_worktree, origin_of
from ..core.worktree_names import random_worktree_name
from ..ui import messages

ENTER_WORKTREE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "yeni ağacın adı (harf/rakam . _ -); dal worktree-<ad>. Verilmezse "
            "rastgele ad",
        },
        "path": {
            "type": "string",
            "description": "yeni ağaç yerine bu deponun VAR OLAN çalışma ağacına geç "
            "(.claude/worktrees dışındaysa onay istenir)",
        },
    },
    "required": [],
}

EXIT_WORKTREE_SCHEMA: dict[str, object] = {"type": "object", "properties": {}, "required": []}


def _open(
    root: Path, name: object, path: object, hooks: WorktreeHookCalls | None = None
) -> Worktree:
    if isinstance(path, str) and path.strip():
        return attach_worktree(root, path.strip())
    if name is not None and not isinstance(name, str):
        raise WorktreeError("'name' metin olmalı.")
    chosen = name.strip() if isinstance(name, str) and name.strip() else random_worktree_name()
    # `WorktreeCreate` tanımlıysa ağacı git yerine kanca kurar (#90).
    return enter_configured_worktree(root, chosen, hooks=hooks)


def _reach(root: Path, worktree: Worktree) -> Path:
    """Bu turda ağaca ulaşılacak yol: kökün içindeyse göreli, değilse mutlak."""
    try:
        return worktree.path.relative_to(root.resolve())
    except ValueError:
        return worktree.path


async def enter_worktree_tool(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Çalışma ağacı aç (yoksa oluştur) ya da `path` ile var olana geç; tur sonunda köke geçilir.

    Claude Code (EnterWorktree): bir ağacın içindeyken başka bir ağaca doğrudan geçilir;
    yeni ağaç her zaman ana depoda açılır (iç içe ağaç olmaz).
    """
    try:
        hooks = getattr(context.worktree_switch, "hooks", None)
        worktree = await asyncio.to_thread(
            _open, context.root, args.get("name"), args.get("path"), hooks
        )
    except WorktreeError as error:
        return ToolResult.failure(str(error))
    context.worktree_switch.request(worktree)
    if worktree.hooked:
        return ToolResult(messages.WORKTREE_TOOL_ENTERED_HOOK.format(path=worktree.path))
    return ToolResult(
        messages.WORKTREE_TOOL_ENTERED.format(
            path=worktree.path, branch=worktree.branch, relative=_reach(context.root, worktree)
        )
    )


async def exit_worktree_tool(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Tur sonunda ana depoya dönülmesini iste; temiz ağaç kaldırılır, iş kalmışsa korunur."""
    del args
    inside = worktree_for_path(context.root)
    origin = inside.origin if inside is not None else _linked_origin(context.root)
    if origin is None:
        return ToolResult(messages.WORKTREE_TOOL_NOT_IN)
    context.worktree_switch.request_exit()
    return ToolResult(messages.WORKTREE_TOOL_EXIT.format(origin=origin))


def _linked_origin(root: Path) -> Path | None:
    """Kök `path` ile girilmiş bağlı bir ağaçsa ana depo kökü; değilse `None`."""
    try:
        origin = origin_of(root)
    except WorktreeError:
        return None
    return None if origin == root.resolve() else origin
