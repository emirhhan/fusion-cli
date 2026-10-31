"""PR oluşturma/yorum beyanlarının kanıt kapısı ve oturum PR bağı (P-057).

Fusion'da PR, model + `run_shell` + onay yoluyla `gh pr create` ile açılır (başlık ve gövde
model işidir; deterministik bir iş akışı bunları üretemez). Bu modül iki şeyi kanıta bağlar:

- **Beyan kapısı:** cevap "PR'ı açtım / pull request created" diyorsa, turda başarılı bir
  `gh pr create` çağrısı ve çıktısında PR adresi OLMALI. Yoksa cevaba "kanıt yok" notu düşer
  (kullanıcı açılmamış bir PR'ı açılmış sanmasın). Yorum beyanı (`gh pr comment`) da aynı.
- **Oturum bağı:** başarılı `gh pr create` (yoksa okunan `gh pr view/checks`) çıktısındaki
  adres oturumun PR künyesi olur (`core.pull_request.PullRequestLink`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from ...core.evidence import ToolUse
from ...core.pull_request import PullRequestLink, pr_links_in

if TYPE_CHECKING:
    from ..agent.loop import AgentOutcome

_GH_PR = re.compile(r"(?:^|[;&|]\s*|\s)gh\s+pr\s+(create|comment|view|checks|status)\b")
#: "PR'ı açtım", "pull request oluşturuldu", "opened a PR", "PR #12 created".
_CREATE_CLAIM = re.compile(
    r"\b(?:pr|pull request|çekme isteği|cekme istegi)\b[^.!?\n]{0,60}?"
    r"\b(?:açtım|actim|açıldı|acildi|açtık|oluşturdum|olusturdum|oluşturuldu|olusturuldu|"
    r"opened|created)\b|"
    r"\b(?:I|we)(?:'ve| have)?\s+(?:opened|created)\s+(?:a\s+|the\s+)?(?:pr|pull request)\b",
    re.IGNORECASE,
)
_COMMENT_CLAIM = re.compile(
    r"\b(?:pr|pull request)\b[^.!?\n]{0,60}?\b(?:yorum (?:yazdım|ekledim|bıraktım|bıraktim)|"
    r"commented)\b|\b(?:I|we)(?:'ve| have)?\s+commented on (?:the\s+)?(?:pr|pull request)\b",
    re.IGNORECASE,
)

UNVERIFIED_CREATE = (
    "Not: Bu turda başarılı bir `gh pr create` çıktısı (PR adresi) görülmedi; PR açılmamış "
    "olabilir. `gh pr status` ile doğrula ya da `/pr` ile yeniden dene."
)
UNVERIFIED_COMMENT = (
    "Not: Bu turda başarılı bir `gh pr comment` çağrısı görülmedi; yorum gönderilmemiş olabilir."
)


def _gh_action(use: ToolUse) -> str | None:
    if use.name == "run_shell":
        match = _GH_PR.search(str(use.arguments.get("command", "")))
        return match.group(1) if match else None
    if use.name == "gh":
        # Salt-okur `gh` aracı (`tools/github_cli.py`): yalnız okuma eylemleri.
        args = str(use.arguments.get("args") or "")
        match = re.match(r"\s*pr\s+(view|checks|status)\b", args)
        return match.group(1) if match else None
    return None


def created_pull_requests(tool_uses: Sequence[ToolUse]) -> tuple[PullRequestLink, ...]:
    """Turda başarılı `gh pr create` çıktılarındaki PR'lar."""
    links: list[PullRequestLink] = []
    for use in tool_uses:
        if use.ok and _gh_action(use) == "create":
            links.extend(pr_links_in(use.output))
    return tuple(dict.fromkeys(links))


def session_pull_request(tool_uses: Sequence[ToolUse]) -> PullRequestLink | None:
    """Oturumun bağlanacağı PR: son açılan, yoksa son okunan; hiçbiri yoksa None."""
    created = created_pull_requests(tool_uses)
    if created:
        return created[-1]
    read: list[PullRequestLink] = []
    for use in tool_uses:
        if use.ok and _gh_action(use) in ("view", "checks", "status"):
            read.extend(pr_links_in(use.output))
    return read[-1] if read else None


def unverified_pr_notes(text: str, tool_uses: Sequence[ToolUse]) -> tuple[str, ...]:
    """Kanıtsız PR beyanları için kullanıcı notları (beyan yoksa boş)."""
    notes: list[str] = []
    if _CREATE_CLAIM.search(text) and not created_pull_requests(tool_uses):
        notes.append(UNVERIFIED_CREATE)
    commented = any(use.ok and _gh_action(use) == "comment" for use in tool_uses)
    if _COMMENT_CLAIM.search(text) and not commented:
        notes.append(UNVERIFIED_COMMENT)
    return tuple(notes)


def disclose_unverified_pr(outcome: AgentOutcome) -> None:
    """Kanıtsız PR beyanı varsa cevabın sonuna not ekle (yerinde; tur sonucu)."""
    notes = [
        note
        for note in unverified_pr_notes(outcome.final_text, outcome.tool_uses)
        if note not in outcome.final_text
    ]
    if notes:
        outcome.final_text = outcome.final_text.rstrip() + "\n\n" + "\n".join(notes)
