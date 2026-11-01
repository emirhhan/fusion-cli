"""Etkileşimli oturum çıkışında çalışma ağacı: sor, sakla ya da sil (#340).

Claude Code (worktrees › Clean up worktrees): çıkışta değişiklik yoksa ağaç ve dalı kendiliğinden
silinir; değişiklik, izlenmeyen dosya ya da yeni commit varsa (alt modül değişikliği de
`git status`'ta görünür) "sakla / sil" diye sorulur; durum doğrulanamazsa da sorulur. Adlı
oturumun ağacı temiz olsa da sorulur. Saklanınca yeniden açma komutu basılır; silinince ağaç ve
dalı commit'lenmemiş değişiklik ve commit'lerle birlikte silinir.

Etkileşimsiz çıkışta (boru, CI) eski kural sürer: temiz ağaç kaldırılır, iş varsa korunur.
Oturumun yaratmadığı (`path` ile girilen) ağaca hiç dokunulmaz.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ...core.errors import WorktreeError
from ...core.worktree import Worktree, has_new_commits, is_dirty, remove_worktree
from ...ui.picker import Choice, pick
from .state import ReplState
from .worktrees import leave_session_worktree

__all__ = ["CHOICE_KEEP", "CHOICE_REMOVE", "exit_decision", "finish_session_worktree"]

CHOICE_KEEP = "sakla"
CHOICE_REMOVE = "sil"
DECIDE_REMOVE = "kaldir"
DECIDE_ASK = "sor"
DECIDE_KEEP = "koru"

EXIT_TITLE = "Çalışma ağacından çıkılıyor: {name} ({reason})"
REASON_WORK = "commit'lenmemiş değişiklik ya da yeni commit var"
REASON_UNKNOWN = "durum doğrulanamadı"
REASON_NAMED = "adlı oturum"
KEPT = "Çalışma ağacı saklandı: {path} (dal {branch}). Devam etmek için: {resume}"
REMOVED = "Çalışma ağacı ve dalı silindi: {name}. Kök: {origin}"
RESUME = "fusion --worktree {name} --resume {conversation}"
CONTINUE = "fusion --worktree {name} --continue"

Chooser = Callable[[Sequence[Choice], str], str | None]


def _pick(choices: Sequence[Choice], title: str) -> str | None:
    return pick(list(choices), title=title)


def exit_decision(worktree: Worktree, *, named: bool) -> tuple[str, str]:
    """(karar, gerekçe): kendiliğinden kaldır, sor ya da koru."""
    if worktree.external:
        return DECIDE_KEEP, ""
    try:
        has_work = is_dirty(worktree) or has_new_commits(worktree)
    except WorktreeError:
        return DECIDE_ASK, REASON_UNKNOWN
    if has_work:
        return DECIDE_ASK, REASON_WORK
    if named:
        return DECIDE_ASK, REASON_NAMED
    return DECIDE_REMOVE, ""


def finish_session_worktree(
    state: ReplState, *, interactive: bool, choose: Chooser | None = None
) -> str:
    """Oturum biterken ağacı Claude kuralıyla kapat; kullanıcıya gösterilecek satır döner."""
    worktree = state.worktree
    if worktree is None:
        return ""
    decision, reason = exit_decision(worktree, named=bool(state.conversation_name))
    if decision != DECIDE_ASK or not interactive:
        return leave_session_worktree(state)
    choices = (
        Choice(CHOICE_KEEP, "Sakla", "ağaç ve dal kalır; sonra devam edebilirsin"),
        Choice(CHOICE_REMOVE, "Sil", "ağaç ve dalı, değişiklik ve commit'lerle birlikte silinir"),
    )
    selected = (choose or _pick)(choices, EXIT_TITLE.format(name=worktree.name, reason=reason))
    state.root = worktree.origin
    state.worktree = None
    if selected != CHOICE_REMOVE:
        conversation = getattr(state, "conversation_id", "") or ""
        resume = (
            RESUME.format(name=worktree.name, conversation=conversation)
            if conversation
            else CONTINUE.format(name=worktree.name)
        )
        return KEPT.format(path=worktree.path, branch=worktree.branch, resume=resume)
    try:
        remove_worktree(worktree, force=True, discard_commits=True)
    except WorktreeError as error:
        return str(error)
    return REMOVED.format(name=worktree.name, origin=worktree.origin)
