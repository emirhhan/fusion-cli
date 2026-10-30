"""`/worktree` komutu ve `--worktree` açılışı: git çalışma ağacı izolasyonunun CLI yüzü.

Çekirdek `core/worktree.py`'dedir; burada yalnız durum (`ReplState.root/worktree`) ve
kullanıcı metni vardır. Masaüstü aynı komutu `run_command` üzerinden çalıştırır ve kök
değişimini `kok` alanıyla öğrenir (bkz. `appserver/session.py::_run_command`).
"""

from __future__ import annotations

from pathlib import Path

from ...core.errors import WorktreeError
from ...core.tools import ToolContext
from ...core.worktree import (
    LeaveOutcome,
    LeaveResult,
    Worktree,
    enter_worktree,
    leave_worktree,
    list_worktrees,
    worktree_for_path,
)
from ...ui import messages
from .state import ReplState


def worktree_command(state: ReplState, argument: str) -> str:
    """`/worktree <ad>` girer, `/worktree cik` çıkar, `/worktree liste` listeler."""
    word, _, rest = argument.strip().partition(" ")
    action = word.casefold()
    if not action:
        if state.worktree is None:
            return messages.WORKTREE_USAGE
        return messages.WORKTREE_CURRENT.format(
            name=state.worktree.name,
            path=state.worktree.path,
            branch=state.worktree.branch,
            origin=state.worktree.origin,
        )
    if action in ("liste", "list", "ls"):
        return _list(state)
    if action in ("cik", "çık", "exit"):
        return leave_session_worktree(state)
    if rest.strip():
        return messages.WORKTREE_USAGE
    return enter_session_worktree(state, word)


def enter_session_worktree(state: ReplState, name: str) -> str:
    """Oturum kökünü adı verilen çalışma ağacına taşı (yoksa oluştur)."""
    if state.worktree is not None:
        return messages.WORKTREE_ALREADY_IN.format(name=state.worktree.name)
    try:
        worktree = enter_worktree(state.root, name)
    except WorktreeError as error:
        return str(error)
    _switch_root(state, worktree)
    return messages.WORKTREE_ENTERED.format(path=worktree.path, branch=worktree.branch)


def leave_session_worktree(state: ReplState) -> str:
    """Ana depoya dön; temiz ağaç kaldırılır, iş kalmışsa korunur ve yolu söylenir."""
    worktree = state.worktree
    if worktree is None:
        return messages.WORKTREE_NOT_IN
    try:
        result = leave_worktree(worktree)
    except WorktreeError as error:
        return str(error)
    state.root = worktree.origin
    state.worktree = None
    return leave_notice(result)


def apply_switch(state: ReplState, tool_context: ToolContext) -> str:
    """Turun `enter_worktree`/`exit_worktree` isteğini uygula; bildirim metni döner (yoksa boş).

    Araç tur ortasında kökü değiştiremez (`ToolContext` donmuş); istek burada, tur
    bittikten sonra tek yerden uygulanır.
    """
    switch = getattr(tool_context, "worktree_switch", None)
    if switch is None:
        return ""
    requested, exit_requested = switch.take()
    if requested is not None:
        if state.worktree is not None and state.worktree.path == requested.path:
            return ""
        _switch_root(state, requested)
        return messages.WORKTREE_SWITCHED.format(path=requested.path)
    if exit_requested and state.worktree is not None:
        return leave_session_worktree(state)
    return ""


def leave_notice(result: LeaveResult) -> str:
    worktree = result.worktree
    if result.outcome is LeaveOutcome.REMOVED:
        return messages.WORKTREE_LEFT_REMOVED.format(name=worktree.name, origin=worktree.origin)
    return messages.WORKTREE_LEFT_KEPT.format(
        reason=messages.WORKTREE_KEPT_REASON.get(result.reason, result.reason),
        path=worktree.path,
        branch=worktree.branch,
    )


def resolve_launch_root(cwd: Path, name: str) -> tuple[Path, Worktree | None]:
    """`--worktree <ad>`: kökü çalışma ağacına çevir; ad boşsa `cwd` olduğu gibi kalır."""
    if not name.strip():
        return cwd, worktree_for_path(cwd)
    worktree = enter_worktree(cwd, name)
    return worktree.path, worktree


def _switch_root(state: ReplState, worktree: Worktree) -> None:
    state.worktree = worktree
    state.root = worktree.path


def _list(state: ReplState) -> str:
    origin = state.worktree.origin if state.worktree is not None else state.root
    inside = worktree_for_path(origin)
    if inside is not None:
        origin = inside.origin
    worktrees = list_worktrees(origin)
    if not worktrees:
        return messages.WORKTREE_LIST_EMPTY
    rows = [
        messages.WORKTREE_LIST_ROW.format(name=item.name, branch=item.branch, path=item.path)
        for item in worktrees
    ]
    return "\n".join(rows)
