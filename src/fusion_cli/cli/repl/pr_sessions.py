"""`fusion --from-pr <numara|URL>` (#205): PR'a bağlı oturumlarla süzülmüş seçici.

Claude Code: `claude --from-pr 123` (ya da GitHub/GitLab/Bitbucket PR adresi) oturum
seçicisini o PR'a bağlı oturumlarla süzerek açar. Oturumun PR künyesi `linked_pr` deposundan
okunur (sohbet PR açtığında ya da PR adresi geçtiğinde bağlanır).
"""

from __future__ import annotations

import re
from pathlib import Path

from ...core.errors import SessionNotFoundError
from ...ui import messages
from . import linked_pr
from .resume_launch import Chooser, _default_chooser
from .transcript_store import list_conversations

_URL_PATTERNS = (
    re.compile(r"github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)"),
    re.compile(r"gitlab\.com/(.+?)/-/merge_requests/(\d+)"),
    re.compile(r"bitbucket\.org/([^/\s]+/[^/\s]+)/pull-requests/(\d+)"),
)


def parse_reference(value: str) -> tuple[int, str | None]:
    """`123`, `#123` ya da PR adresi → (numara, depo|None). Geçersizse SessionNotFoundError."""
    text = value.strip()
    if text.lstrip("#").isdigit() and int(text.lstrip("#")) > 0:
        return int(text.lstrip("#")), None
    for pattern in _URL_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(2)), match.group(1).lower()
    raise SessionNotFoundError(messages.FROM_PR_INVALID.format(value=text))


def _matches(memory_dir: Path, conversation_id: str, number: int, repo: str | None) -> bool:
    link = linked_pr.load(memory_dir, conversation_id)
    if link is None or link.number != number:
        return False
    return repo is None or link.repo.lower().endswith(repo) or repo.endswith(link.repo.lower())


def pick_for_pr(memory_dir: Path, root: Path, value: str, chooser: Chooser | None = None) -> str:
    """PR'a bağlı sohbetlerden birini seçtir; kimliğini döndür."""
    from .session_resume import resume_choices

    number, repo = parse_reference(value)
    refs = [
        ref
        for ref in list_conversations(memory_dir, root)
        if _matches(memory_dir, ref.conversation_id, number, repo)
    ]
    if not refs:
        raise SessionNotFoundError(messages.FROM_PR_NONE.format(number=number))
    title = messages.FROM_PR_PICK_TITLE.format(number=number)
    chosen = (chooser or _default_chooser)(resume_choices(refs), title)
    if not chosen:
        raise SessionNotFoundError(messages.SESSION_PICK_CANCELLED)
    return chosen
