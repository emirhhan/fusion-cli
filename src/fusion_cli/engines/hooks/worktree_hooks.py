"""`WorktreeCreate` / `WorktreeRemove` kancaları: çalışma ağacı kurulumunun yerine geçer.

Claude Code: `--worktree` ya da alt ajan `isolation: "worktree"` ağaç kurarken
`WorktreeCreate` tanımlıysa git hiç çalışmaz; komut kancası girdideki `name` ile ağacı kurar
ve mutlak yolunu stdout'a yazar (http kancası `hookSpecificOutput.worktreePath`). Sıfır
dışı çıkış ya da yol yoksa kurulum başarısız olur. `WorktreeRemove` (`worktree_path`)
oturumdan ya da alt ajandan çıkarken temizlik içindir; karar denetimi yoktur, hatası
oturumu etkilemez.

Çağıranlar eşzamanlıdır (git yolu gibi); kanca ayrı iş parçacığındaki kendi olay döngüsünde
koşar, böylece hem çalışan bir döngünün içinden (`asyncio.run` iç içe olamaz) hem
`asyncio.to_thread`'den çağrılabilir. Çağıran, git komutunda olduğu gibi kanca bitene dek bekler.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from pathlib import Path
from typing import TypeVar

from ...config.models import Config
from ...core.errors import WorktreeError
from ...core.hooks.events import HookEvent, HookVerdict
from ...core.worktree import WorktreeHookCalls
from ...ui import messages
from .factory import open_hook_session
from .session import HookSession

_T = TypeVar("_T")


def worktree_hook_calls(session: HookSession | None) -> WorktreeHookCalls | None:
    """Oturumun kancalarıyla çalışan çağrılar; oturum yoksa `None` (git yolu)."""
    if session is None:
        return None
    return WorktreeHookCalls(
        create=lambda cwd, name: create_with_hooks(session, cwd, name),
        remove=lambda path: remove_with_hooks(session, path),
    )


def create_with_hooks(session: HookSession, cwd: Path, name: str) -> Path | None:
    """`WorktreeCreate` tanımlı değilse `None`; tanımlıysa kancanın kurduğu dizin."""
    if not session.has(HookEvent.WORKTREE_CREATE):
        return None
    verdict = _run_sync(session.emit(HookEvent.WORKTREE_CREATE, fields={"name": name}))
    if verdict.errors or verdict.blocked:
        reason = "\n".join(verdict.errors) or verdict.reason
        raise WorktreeError(messages.WORKTREE_HOOK_FAILED.format(reason=reason))
    if not verdict.worktree_path:
        raise WorktreeError(messages.WORKTREE_HOOK_NO_PATH)
    path = Path(verdict.worktree_path).expanduser()
    path = (path if path.is_absolute() else cwd / path).resolve()
    if not path.is_dir():
        raise WorktreeError(messages.WORKTREE_HOOK_NOT_DIR.format(path=path))
    return path


def remove_with_hooks(session: HookSession, path: Path) -> bool:
    """`WorktreeRemove` kancalarını çalıştır; tanımlı kanca yoksa `False`."""
    if not session.has(HookEvent.WORKTREE_REMOVE):
        return False
    verdict: HookVerdict = _run_sync(
        session.emit(HookEvent.WORKTREE_REMOVE, fields={"worktree_path": str(path)})
    )
    return verdict.ran > 0


def _run_sync(work: Coroutine[object, object, _T]) -> _T:
    """Eşyordamı ayrı iş parçacığında kendi döngüsüyle çalıştır ve sonucunu bekle."""
    box: dict[str, object] = {}

    def _target() -> None:
        try:
            box["value"] = asyncio.run(work)
        except BaseException as error:
            box["error"] = error

    thread = threading.Thread(target=_target, name="fusion-worktree-hook", daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["value"]  # type: ignore[return-value]


def launch_hook_calls(cwd: Path, config: Config, *, interactive: bool) -> WorktreeHookCalls:
    """`--worktree` açılışı: oturum henüz yokken kancalar `cwd`'nin ayarlarından okunur."""
    session = open_hook_session(cwd, config, interactive=interactive)
    # Açılış ağacı oturumun dökümüne yazılmaz (oturum kimliği henüz yok).
    session.transcript_dir = None
    calls = worktree_hook_calls(session)
    assert calls is not None
    return calls
