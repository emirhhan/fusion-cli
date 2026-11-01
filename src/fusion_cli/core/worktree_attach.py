"""Var olan bir çalışma ağacına yolu ile girme (Claude Code EnterWorktree `path`, #342).

Claude Code (tools-reference › EnterWorktree): `path` verilirse yeni ağaç açılmaz, geçerli
deponun var olan bir çalışma ağacına geçilir; bir ağacın içindeyken başkasına doğrudan
geçilebilir. Yol `git worktree list` içinde olmalı ve ana çalışma ağacı olamaz.

`.claude/worktrees/` altında Fusion künyesi olan ağaç kendi künyesiyle döner. Künyesiz ya da
başka yerdeki ağaç `external=True` döner: çıkışta HİÇ kaldırılmaz (oturum onu yaratmadı).
Yalnız stdlib; hata `WorktreeError`.
"""

from __future__ import annotations

from pathlib import Path

from .errors import WorktreeError
from .worktree import WORKTREE_DIR, Worktree, _git, find_worktree

__all__ = ["attach_worktree", "is_managed_location", "origin_of"]


def origin_of(cwd: Path) -> Path:
    """`cwd`'nin deposunun ana çalışma ağacı kökü (bağlı ağaçtan da)."""
    common = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    if not common:
        raise WorktreeError(f"Burası bir git deposu değil: {cwd}.")
    return Path(common).resolve().parent


def _listed(origin: Path) -> dict[Path, str]:
    """`git worktree list --porcelain` → {yol: dal (kısa ad; ayrık HEAD'de boş)}."""
    listed: dict[Path, str] = {}
    current: Path | None = None
    for line in _git(origin, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            current = Path(line.removeprefix("worktree ")).resolve()
            listed[current] = ""
        elif line.startswith("branch ") and current is not None:
            listed[current] = line.removeprefix("branch ").removeprefix("refs/heads/")
    return listed


def is_managed_location(origin: Path, path: Path) -> bool:
    """Yol deponun `.claude/worktrees/` dizininin içinde mi (Claude: onaysız giriş)?"""
    managed = (origin / WORKTREE_DIR).resolve()
    resolved = path.expanduser().resolve()
    return resolved.parent == managed


def attach_worktree(cwd: Path, raw_path: str) -> Worktree:
    """Geçerli deponun `raw_path`'teki çalışma ağacını döndür; değilse `WorktreeError`."""
    origin = origin_of(cwd)
    candidate = Path(raw_path).expanduser()
    path = (candidate if candidate.is_absolute() else cwd / candidate).resolve()
    listed = _listed(origin)
    if path == origin.resolve():
        raise WorktreeError(
            "Bu yol deponun ana çalışma ağacı; ana depoya dönmek için exit_worktree çağır."
        )
    if path not in listed:
        raise WorktreeError(f"{path} bu deponun bir çalışma ağacı değil (git worktree list).")
    if is_managed_location(origin, path):
        known = find_worktree(origin, path.name)
        if known is not None:
            return known
    head = _git(path, "rev-parse", "HEAD").strip()
    return Worktree(
        name=path.name,
        path=path,
        branch=listed[path] or head[:12],
        origin=origin,
        base_commit=head,
        external=True,
    )
