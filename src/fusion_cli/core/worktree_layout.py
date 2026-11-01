"""Claude Code `worktree.symlinkDirectories` ve `worktree.sparsePaths` (#361).

Claude Code (settings-reference › worktree): `symlinkDirectories` ana depodaki dizinleri
(ör. `node_modules`) her çalışma ağacına sembolik bağ olarak koyar, diskte kopyalanmaz;
`sparsePaths` çalışma ağacına git sparse-checkout (cone kipi) ile yalnız listelenen dizinleri
yazar. Yalnız stdlib; `git` çağrısı çağıranın verdiği işlevle yapılır.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import WorktreeError

__all__ = ["WorktreeLayout", "add_worktree", "link_directories"]

GitRunner = Callable[..., str]


@dataclass(frozen=True, slots=True)
class WorktreeLayout:
    """Yeni çalışma ağacının diskteki biçimi; boş değerler eski davranıştır."""

    symlink_dirs: tuple[str, ...] = ()
    sparse_paths: tuple[str, ...] = ()


def _relative(raw: str, where: str) -> str:
    """Depo köküne göreli, `..` içermeyen yol; değilse `WorktreeError`."""
    path = PurePosixPath(raw.strip().strip("/"))
    if not raw.strip() or raw.strip().startswith("/") or ".." in path.parts:
        raise WorktreeError(f"worktree.{where}: depo köküne göreli bir yol olmalı: {raw!r}")
    return path.as_posix()


def add_worktree(
    git: GitRunner,
    origin: Path,
    path: Path,
    branch: str,
    base_commit: str,
    *,
    new_branch: bool,
    layout: WorktreeLayout,
) -> None:
    """`git worktree add`; `sparse_paths` varsa önce checkout'suz açılıp cone kipine alınır."""
    target = [str(path), branch] if not new_branch else ["-b", branch, str(path), base_commit]
    if not layout.sparse_paths:
        git(origin, "worktree", "add", *target)
        return
    paths = [_relative(item, "sparsePaths") for item in layout.sparse_paths]
    git(origin, "worktree", "add", "--no-checkout", *target)
    git(path, "sparse-checkout", "set", "--cone", *paths)
    git(path, "read-tree", "-mu", "HEAD")


def link_directories(origin: Path, path: Path, dirs: tuple[str, ...]) -> tuple[Path, ...]:
    """Ana depodaki var olan dizinlere bağ kur; ağaçta zaten olan yola dokunulmaz.

    Ağaca göreli bağ yollarını döndürür (çıkışta "iş" sayılmasınlar diye künyeye girer).
    """
    linked: list[Path] = []
    for raw in dirs:
        relative = _relative(raw, "symlinkDirectories")
        source = origin / relative
        target = path / relative
        if not source.is_dir() or target.exists() or target.is_symlink():
            continue
        if not _inside(source, origin) or not _inside(target.parent, path):
            # Depo dışını gösteren bağ (`cache -> ~/.ssh`) ya da ağaçtan taşan üst dizin.
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source, target_is_directory=True)
        linked.append(Path(relative))
    return tuple(linked)


def _inside(candidate: Path, base: Path) -> bool:
    """Sembolik bağlar çözüldüğünde `candidate` `base` içinde mi (var olmayan kısım dahil)?"""
    return candidate.resolve().is_relative_to(base.resolve())
