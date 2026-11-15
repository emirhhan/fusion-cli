"""`/diff` — çalışma ağacındaki değişiklikler ve bu oturumdaki düzenlemeler tur tur (#230).

Claude Code `/diff` iki görünüm sunar: git çalışma ağacının farkı ve Claude'un bu oturumda
yaptığı düzenlemeler tur başına. Fusion aynı iki bölümü metin olarak basar: `git diff
HEAD --stat` özeti ve tur checkpoint defterindeki (`/rewind`) her turun dosyaları.
Komut salt okurdur; git yoksa ya da depo değilse yalnız oturum bölümü gösterilir.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ...ui import messages
from .state import ReplState

#: `git diff` için üst süre; büyük depoda REPL takılmasın.
GIT_TIMEOUT_S = 10
#: Tam farktan gösterilecek en fazla satır.
DIFF_MAX_LINES = 400


def _git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def session_lines(state: ReplState) -> list[str]:
    """Bu oturumda dosya değiştiren turlar, eskiden yeniye."""
    lines: list[str] = []
    for entry in state.checkpoints.entries():
        if not entry.changed_paths:
            continue
        task = entry.task.strip().splitlines()[0] if entry.task.strip() else ""
        lines.append(messages.DIFF_TURN.format(index=entry.index, task=task[:60]))
        lines.extend(f"  {_relative(path, state.root)}" for path in entry.changed_paths)
    return lines


def diff_command(state: ReplState, argument: str) -> str:
    """`/diff [tam]` — git özeti + oturum turları; `tam` farkın kendisini de basar."""
    parts: list[str] = []
    stat = _git(state.root, "diff", "HEAD", "--stat")
    if stat is None:
        parts.append(messages.DIFF_NO_GIT)
    elif stat.strip():
        parts.extend((messages.DIFF_WORKTREE_HEADING, stat.rstrip()))
        if argument.strip().lower() in {"tam", "full", "all"}:
            full = (_git(state.root, "diff", "HEAD") or "").splitlines()
            parts.append("\n".join(full[:DIFF_MAX_LINES]))
            if len(full) > DIFF_MAX_LINES:
                parts.append(messages.DIFF_TRUNCATED.format(count=len(full) - DIFF_MAX_LINES))
    else:
        parts.append(messages.DIFF_WORKTREE_CLEAN)
    turns = session_lines(state)
    parts.extend((messages.DIFF_SESSION_HEADING, *turns) if turns else (messages.DIFF_NO_TURNS,))
    return "\n".join(parts)
