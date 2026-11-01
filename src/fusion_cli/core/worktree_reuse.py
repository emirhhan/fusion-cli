"""Aynı adla yeniden açılan çalışma ağacının "fresh" tabanda tazelenmesi (Claude Code, #373).

Claude Code (worktrees, "Reuse a worktree name"): varsayılan `"fresh"` tabanda yeniden açılan
ağaç şu koşulların hepsi tutarsa varsayılan dala getirilir: commit'lenmemiş/izlenmeyen dosya
yok, hâlâ kendisi için açılan dalda, kendi commit'i yok. Öteki her durumda (doğrulanamayan
durum, `"head"` taban, PR/MR adı) eski ucunda açılır.

Tazeleme `git merge --ff-only` ile yapılır: kendi commit'i olmayan dal varsayılan dalın
atasıdır, ileri sarma hiçbir işi silemez; atası değilse git reddeder ve ağaç olduğu gibi kalır.
"""

from __future__ import annotations

from pathlib import Path

from .worktree_fetch import GIT_LOCAL_TIMEOUT_S, quiet_git


def _git(path: Path, *args: str) -> str | None:
    return quiet_git(path, args, timeout_s=GIT_LOCAL_TIMEOUT_S)


def _work_left(status: str, included: tuple[str, ...]) -> bool:
    """`.worktreeinclude` kopyaları dışında değişmiş/izlenmeyen dosya var mı?"""
    for line in status.splitlines():
        if len(line) < 4:
            continue
        if line.startswith("??") and line[3:].strip().strip('"') in included:
            continue
        return True
    return False


def refresh_to(path: Path, branch: str, target: str, *, included: tuple[str, ...] = ()) -> bool:
    """Koşullar doğrulanırsa ağacı `target`'a ileri sar; sarıldıysa `True`."""
    status = _git(path, "status", "--porcelain", "--untracked-files=all")
    current = _git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    own = _git(path, "rev-list", "--count", f"{target}..HEAD")
    if status is None or current is None or own is None:
        return False  # durum doğrulanamadı: eski ucunda aç
    if _work_left(status, included) or current.strip() != branch or own.strip() != "0":
        return False
    return _git(path, "merge", "--ff-only", "--quiet", target) is not None
