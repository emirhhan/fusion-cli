"""PR/MR'den çalışma ağacı: `--worktree "#1234"` ya da PR/MR adresi (Claude Code, #341).

Claude Code (common-workflows, worktrees): `#<n>`, GitHub PR adresi ya da GitLab MR adresi
verilince `origin`'den `pull/<n>/head` (GitLab: `merge-requests/<n>/head`) çekilir ve
`.claude/worktrees/pr-<n>` açılır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER = re.compile(r"^#(\d+)$")
_GITHUB = re.compile(r"^https?://[^/]+/[^/]+/[^/]+/pull/(\d+)(?:[/?#].*)?$")
_GITLAB = re.compile(r"^https?://[^/]+/.+/-/merge_requests/(\d+)(?:[/?#].*)?$")


@dataclass(frozen=True, slots=True)
class PullRequestRef:
    number: int
    #: `origin`'den çekilecek uzak başvuru.
    refspec: str

    @property
    def worktree_name(self) -> str:
        return f"pr-{self.number}"


def parse_pull_request(text: str) -> PullRequestRef | None:
    """`#12`, GitHub `…/pull/12` ya da GitLab `…/-/merge_requests/12`; değilse `None`."""
    candidate = text.strip()
    for pattern, template in (
        (_NUMBER, "pull/{n}/head"),
        (_GITHUB, "pull/{n}/head"),
        (_GITLAB, "merge-requests/{n}/head"),
    ):
        found = pattern.match(candidate)
        if found:
            number = int(found.group(1))
            return PullRequestRef(number, template.format(n=number))
    return None
