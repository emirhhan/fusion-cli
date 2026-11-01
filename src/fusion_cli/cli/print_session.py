"""`fusion -p` oturum kaydı (#277, #304).

Bayraklar: `-c/-r/--fork-session/--session-id/--no-session-persistence/-n`.

Claude'da başsız koşu da bir oturumdur: kimliği `system/init` ve `result` nesnesinde
`session_id` olarak döner, sonra `claude -r "$session_id" -p "..."` ile sürdürülür. Fusion
REPL'in sohbet deposu (`TranscriptStore`) aynen kullanılır; böylece `-p` ile açılan oturum
REPL'deki `/resume` listesinde de görünür.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.errors import SessionNotFoundError
from ..core.types import Message
from ..ui import print_messages as texts
from .repl import linked_pr, session_resume
from .repl.transcript_store import TranscriptStore, list_conversations

if TYPE_CHECKING:
    from .print_plan import PrintPlan


@dataclass(frozen=True, slots=True)
class PrintSession:
    """Koşunun bağlandığı oturum."""

    session_id: str
    history: tuple[Message, ...]
    persist: bool


def resolve_print_session(
    memory_dir: Path,
    root: Path,
    *,
    continue_last: bool,
    resume: str,
    fork: bool,
    name: str,
    session_id: str | None,
    persist: bool,
) -> PrintSession:
    """Bayrakları oturuma çevir; bulunamayan sohbet `SessionNotFoundError`."""
    resuming = continue_last or bool(resume.strip())
    if session_id is not None and resuming and not fork:
        raise ValueError(texts.PRINT_SESSION_ID_CONFLICT)
    if not resuming:
        if fork:  # kaynaksız --fork-session: deponun açık hatası (SessionNotFoundError)
            session_resume.resolve_launch(memory_dir, root, fork=True)
        new_id = session_id or str(uuid.uuid4())
        if name.strip() and persist:
            TranscriptStore(memory_dir, root, conversation_id=new_id).record_name(name.strip())
        return PrintSession(new_id, (), persist)
    target = session_resume.resolve_launch(
        memory_dir,
        root,
        continue_last=continue_last,
        resume=resume,
        fork=fork,
        name=name if persist else "",
    )
    assert target is not None  # sürdürme bayrağı varken hedef her zaman döner
    return PrintSession(target.conversation_id, target.history, persist)


def record_turn(
    memory_dir: Path, root: Path, session: PrintSession, task: str, answer: str
) -> None:
    """Turu oturum deposuna yaz (`--no-session-persistence` ile hiç yazılmaz)."""
    if not session.persist:
        return
    store = TranscriptStore(memory_dir, root, conversation_id=session.session_id)
    store.record_user(task)
    if answer.strip():
        store.record_assistant(answer)


_PR_NUMBER = re.compile(r"(?:/pull/|/merge_requests/|/pull-requests/)(\d+)")


def pr_number(raw: str) -> int | None:
    """`--from-pr` değeri: PR numarası ya da GitHub/GitLab/Bitbucket URL'si."""
    text = raw.strip().lstrip("#")
    if text.isdigit():
        return int(text)
    match = _PR_NUMBER.search(text)
    return int(match.group(1)) if match else None


def find_pr_session(memory_dir: Path, root: Path, raw: str) -> str:
    """`--from-pr`: bu PR'a bağlı en son oturumun kimliği; yoksa `SessionNotFoundError`."""
    number = pr_number(raw)
    if number is None:
        raise ValueError(texts.PRINT_FROM_PR_INVALID.format(value=raw))
    url = raw.strip().rstrip("/")
    for ref in list_conversations(memory_dir, root):
        link = linked_pr.load(memory_dir, ref.conversation_id)
        if link is None:
            continue
        if link.number == number and (not url.startswith("http") or link.url.rstrip("/") == url):
            return ref.conversation_id
    raise SessionNotFoundError(texts.PRINT_FROM_PR_NONE.format(value=raw.strip()))


def snapshot_plan(plan: PrintPlan, session: PrintSession, *, resuming: bool) -> PrintPlan:
    """Sürdürülen sohbette kayıtlı sistem istemi metni (`--system-prompt-snapshot`, #295)."""
    from dataclasses import replace

    from .launch_prompts import LaunchPrompts, recorded, snapshot_enabled

    request = plan.request
    prompts = recorded(
        plan.config.memory_dir,
        session.session_id,
        LaunchPrompts(plan.system_prompt, plan.extra_system),
        resuming=resuming and not request.fork_session,
        enabled=snapshot_enabled(request.system_prompt_snapshot, bare=request.bare),
        persist=session.persist,
    )
    return replace(plan, system_prompt=prompts.system_prompt, extra_system=prompts.extra_system)
