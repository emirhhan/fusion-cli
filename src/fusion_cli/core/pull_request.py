"""Oturuma bağlı GitHub PR künyesi (P-057).

Claude Code `gh pr create` sonrası oturumu PR'a bağlar ve durum satırında gösterir. Fusion'da
künye tur kanıtından (başarılı `gh pr create` çıktısındaki adres) ya da `--from-pr N` ile
kurulur; REPL durum satırı ve masaüstü sohbet şeridi aynı künyeyi gösterir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: `https://github.com/<sahip>/<depo>/pull/<no>` (Enterprise alan adları da: `<alan>/…/pull/N`).
PR_URL = re.compile(r"https://([\w.-]+)/([\w.-]+/[\w.-]+)/pull/(\d+)\b")


@dataclass(frozen=True, slots=True)
class PullRequestLink:
    """Oturumun bağlı olduğu PR."""

    repo: str
    number: int
    url: str

    @property
    def label(self) -> str:
        return f"PR #{self.number}"


def pr_links_in(text: str) -> tuple[PullRequestLink, ...]:
    """Metindeki PR adresleri (sıra korunur, tekrar elenir)."""
    found: dict[str, PullRequestLink] = {}
    for match in PR_URL.finditer(text):
        url = match.group(0)
        found.setdefault(url, PullRequestLink(match.group(2), int(match.group(3)), url))
    return tuple(found.values())
