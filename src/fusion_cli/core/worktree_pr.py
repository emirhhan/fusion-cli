"""PR/MR'den çalışma ağacı: `--worktree "#1234"` ya da PR/MR adresi (Claude Code, #341).

Claude Code (worktrees, "Branch from a pull request"): `#<n>`, GitHub PR adresi ya da GitLab
MR adresi verilince adresten yalnız numara okunur; baş commit her zaman `origin`'den çekilir
ve `.claude/worktrees/pr-<n>` açılır. Çekme yolu `origin`'in sunucusuna göre seçilir:
github.com → `pull/<n>/head`, gitlab.com → `merge-requests/<n>/head`, başka sunucu → önce
`pull/<n>/head`, sonra `merge-requests/<n>/head`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER = re.compile(r"^#(\d+)$")
_GITHUB = re.compile(r"^https?://[^/]+/[^/]+/[^/]+/pull/(\d+)(?:[/?#].*)?$")
_GITLAB = re.compile(r"^https?://[^/]+/.+/-/merge_requests/(\d+)(?:[/?#].*)?$")
#: `https://host/…`, `ssh://user@host/…` ve `user@host:yol` biçimlerinden sunucu adı.
_REMOTE_HOST = re.compile(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)")


@dataclass(frozen=True, slots=True)
class PullRequestRef:
    number: int

    @property
    def worktree_name(self) -> str:
        return f"pr-{self.number}"

    def refspecs(self, remote_url: str) -> tuple[str, ...]:
        """`origin` adresine göre denenecek uzak başvurular, sırayla."""
        pull, merge = f"pull/{self.number}/head", f"merge-requests/{self.number}/head"
        found = _REMOTE_HOST.match(remote_url.strip())
        host = found.group(1).casefold() if found else ""
        if host == "github.com":
            return (pull,)
        if host == "gitlab.com":
            return (merge,)
        return (pull, merge)


def parse_pull_request(text: str) -> PullRequestRef | None:
    """`#12`, GitHub `…/pull/12` ya da GitLab `…/-/merge_requests/12`; değilse `None`."""
    candidate = text.strip()
    for pattern in (_NUMBER, _GITHUB, _GITLAB):
        found = pattern.match(candidate)
        if found:
            return PullRequestRef(int(found.group(1)))
    return None
