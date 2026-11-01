"""`-w #123`, GitHub PR ya da GitLab MR adresi: PR/MR'ı origin'den çekip ağacı ondan aç (#314).

Claude Code'da `--worktree` değeri `#<numara>`, `https://github.com/<o>/<r>/pull/<n>` ya da
`https://gitlab.com/<g>/<r>/-/merge_requests/<n>` olunca o PR/MR `origin`'den çekilir ve
çalışma ağacı ondan dallanır. Burada GitHub için `pull/<n>/head`, GitLab için
`merge-requests/<n>/head` başvurusu `refs/remotes/origin/pr/<n>`'e çekilir; ağacın adı
`pr-<n>` olur. Çekme başarısızsa `WorktreeError` (açık git özeti).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..core.worktree import (
    Worktree,
    WorktreeHookCalls,
    _git,
    enter_worktree,
    repository_root,
    worktree_for_path,
)

_GITHUB = re.compile(r"^https?://[^/]+/[^/]+/[^/]+/pull/(\d+)/?(?:[#?].*)?$")
_GITLAB = re.compile(r"^https?://[^/]+/.+/-/merge_requests/(\d+)/?(?:[#?].*)?$")


@dataclass(frozen=True, slots=True)
class PullRef:
    """Çekilecek PR/MR: numara ve uzak başvuru."""

    number: int
    remote_ref: str

    @property
    def local_ref(self) -> str:
        return f"refs/remotes/origin/pr/{self.number}"

    @property
    def worktree_name(self) -> str:
        return f"pr-{self.number}"


def parse_pull_ref(value: str) -> PullRef | None:
    """`#123`, GitHub PR ya da GitLab MR adresi; değilse `None` (düz ağaç adı)."""
    text = value.strip()
    if text.startswith("#") and text[1:].isdigit():
        number = int(text[1:])
        return PullRef(number, f"pull/{number}/head")
    if match := _GITHUB.match(text):
        number = int(match.group(1))
        return PullRef(number, f"pull/{number}/head")
    if match := _GITLAB.match(text):
        number = int(match.group(1))
        return PullRef(number, f"merge-requests/{number}/head")
    return None


def enter_pull_worktree(
    cwd: Path, ref: PullRef, *, hooks: WorktreeHookCalls | None = None
) -> Worktree:
    """PR/MR'ı origin'den çek ve `pr-<n>` ağacını o işlemeden aç (varsa olanı kullan)."""
    inside = worktree_for_path(cwd)
    origin = inside.origin if inside is not None else repository_root(cwd)
    git_dir = origin if origin is not None else cwd
    _git(git_dir, "fetch", "origin", f"+{ref.remote_ref}:{ref.local_ref}")
    return enter_worktree(cwd, ref.worktree_name, base_ref=ref.local_ref, hooks=hooks)
