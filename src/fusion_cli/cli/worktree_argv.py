"""`-w` / `--worktree` değersiz verilirse ad üret (Claude Code `claude -w`, #339).

Typer/Click seçenekleri isteğe bağlı değer almaz; ad, bayraktan hemen sonra başka bir seçenek
(`-` ile başlayan) geliyorsa ya da bayrak son argümansa eklenir. `--worktree=ad` ve `--`
sonrasındaki argümanlara dokunulmaz.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..core.worktree_names import random_worktree_name

_FLAGS = frozenset({"-w", "--worktree"})


def fill_missing_worktree_name(
    argv: Sequence[str], *, namer: Callable[[], str] = random_worktree_name
) -> list[str]:
    """Değersiz `-w`/`--worktree` arkasına üretilmiş ad ekle; argv'nin yeni kopyasını döndür."""
    result: list[str] = []
    for index, value in enumerate(argv):
        if value == "--":
            return [*result, *argv[index:]]
        result.append(value)
        if value in _FLAGS:
            following = argv[index + 1] if index + 1 < len(argv) else None
            if following is None or following.startswith("-"):
                result.append(namer())
    return result
