"""`/fork [istem]` — konuşmayı yeni bir arka plan oturumuna kopyala, burada devam et (#229).

Claude Code: istem verilirse kopya hemen çalışmaya başlar; verilmezse ilk istemini bekler.
Kopya kod değiştirmeden önce kendi çalışma ağacını kurar (yerinde düzenleme dışında).

Fusion karşılığı: istemli `/fork` konuşmayı devralan arka plan görevi başlatır (`/bg` ile aynı
altyapı); proje bir git deposuysa görev kendi çalışma ağacında (`fork-<kısa kimlik>`) çalışır.
İstemsiz `/fork` konuşmayı yeni kimlikli kayıtlı bir sohbete kopyalar; kopya ilk istemini
`/resume <kimlik>` ya da `fusion -r <kimlik>` ile bekler. Özgün sohbet ikisinde de değişmez.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...core.background_tasks import BackgroundTaskError
from ...core.errors import FusionError, WorktreeError
from ...core.worktree import enter_worktree, repository_root
from ...ui import messages
from .background_commands import start_background
from .state import ReplState

_LOG = logging.getLogger(__name__)
#: Kopyanın çalışma ağacı adının öneki.
FORK_WORKTREE_PREFIX = "fork-"


def fork_command(state: ReplState, argument: str) -> str:
    """İstem varsa arka plan kopyası başlat, yoksa bekleyen kayıtlı kopya oluştur."""
    if not any(m.role in ("user", "assistant") for m in state.history):
        return messages.FORK_EMPTY
    prompt = argument.strip()
    if not prompt:
        return _waiting_copy(state)
    root, note = _isolated_root(state)
    original = state.root
    try:
        state.root = root
        task = start_background(state, prompt)
    except BackgroundTaskError as error:
        return str(error)
    finally:
        state.root = original
    return messages.FORK_STARTED.format(id=task.id, name=task.name) + note


def _waiting_copy(state: ReplState) -> str:
    from .session_resume import fork_conversation

    try:
        target_id = fork_conversation(
            state.config.memory_dir,
            state.root,
            state.history,
            name=state.conversation_name,
            source_id=state.conversation_id,
        )
    except (OSError, ValueError, FusionError) as error:
        return messages.FORK_COPY_FAILED.format(error=error)
    return messages.FORK_WAITING.format(id=target_id)


def _isolated_root(state: ReplState) -> tuple[Path, str]:
    """Git deposunda kopyaya kendi çalışma ağacını aç; değilse yerinde çalışır."""
    if repository_root(state.root) is None:
        return state.root, messages.FORK_IN_PLACE
    name = FORK_WORKTREE_PREFIX + state.conversation_id.removeprefix("session-")[:8]
    try:
        tree = enter_worktree(state.root, name)
    except (WorktreeError, OSError) as error:
        _LOG.warning("fork çalışma ağacı açılamadı: %s", type(error).__name__)
        return state.root, messages.FORK_IN_PLACE
    return tree.path, messages.FORK_WORKTREE.format(path=tree.path)
