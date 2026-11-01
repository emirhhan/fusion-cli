"""`enter_worktree path` onayı (Claude Code EnterWorktree, #342).

Claude Code: deponun `.claude/worktrees/` dizini dışındaki bir çalışma ağacına girmeden önce
kullanıcıya sorulur. Fusion aynı kuralı `pre_ask` ile uygular: her kipte sorulur (yalnız
"İzinleri atla" sormaz), soracak kimse yoksa (`dontAsk`, gözetimsiz) engellenir.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.errors import WorktreeError
from ...core.tools import ToolContext
from ...core.worktree_attach import is_managed_location, origin_of

if TYPE_CHECKING:
    from .approval import ApprovalRequest

__all__ = ["OUTSIDE_WORKTREES", "apply_worktree_path_policy"]

OUTSIDE_WORKTREES = "çalışma ağacı .claude/worktrees dışında ({path}); girmeden önce onay gerekir"


def apply_worktree_path_policy(
    request: ApprovalRequest, context: ToolContext | None
) -> ApprovalRequest:
    """`.claude/worktrees` dışındaki yola giren `enter_worktree` çağrısını sorulur yap."""
    raw = request.args.get("path")
    if (
        context is None
        or request.tool.name != "enter_worktree"
        or not isinstance(raw, str)
        or not raw.strip()
    ):
        return request
    root = Path(context.root)
    candidate = Path(raw.strip()).expanduser()
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        origin = origin_of(root)
    except WorktreeError:
        return request
    if is_managed_location(origin, target):
        return request
    reason = OUTSIDE_WORKTREES.format(path=target)
    note = f"{request.note}. {reason}" if request.note else reason
    return replace(request, pre_ask=request.pre_ask or reason, note=note)
