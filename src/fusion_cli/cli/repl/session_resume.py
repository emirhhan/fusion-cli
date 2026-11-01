"""Fusion'ın KENDİ sohbetlerini sürdürme, adlandırma ve dallandırma.

Claude Code'daki `--continue/--resume/--fork-session/--name` ve `/resume`, `/rename`,
`/branch` karşılıkları. Dinamik `/resume<kaynak>` komutları (Claude/Codex geçmişi) ayrı
kalır: oradaki kayıt DIŞ araçlarındır ve yalnız künye olarak devralınır; burada ise
konuşma transcript'ten olduğu gibi model bağlamına yüklenir.

Ölçüldü (31 Ekim): REPL her turu `TranscriptStore`'a yazıyor, `list_conversations` ve
`load_transcript_messages` konuşmayı kimliğiyle geri okuyabiliyordu; ama CLI hiçbir
yoldan kendi önceki sohbetini açamıyordu (`state.py` her açılışta yeni kimlik üretir).
Bu modül o boşluğu kapatır; depo biçimi değişmez.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ...core.errors import SessionNotFoundError
from ...core.types import Message
from ...ui import messages
from ...ui.picker import Choice, pick
from . import linked_pr
from .state import ReplState
from .transcript_store import (
    ConversationRef,
    TranscriptStore,
    conversation_prefix,
    copy_conversation,
    find_conversation,
    list_conversations,
    load_transcript_messages,
)

#: `/resume` listesinde gösterilecek en fazla sohbet.
SESSION_LIST_LIMIT = 50


@dataclass(frozen=True, slots=True)
class ResumeTarget:
    """Açılışta ya da `/resume` ile bağlanılacak sohbet."""

    conversation_id: str
    history: tuple[Message, ...]
    title: str
    name: str = ""
    #: `--fork-session` ile kopyalandıysa kaynağın kimliği (bilgi amaçlı).
    forked_from: str = ""


def new_conversation_id() -> str:
    """`ReplState` ile aynı biçim: transcript ve checkpoint aynı sahibi kullanır."""
    return f"session-{uuid.uuid4().hex}"


def resolve_launch(
    memory_dir: Path,
    root: Path,
    *,
    continue_last: bool = False,
    resume: str = "",
    fork: bool = False,
    name: str = "",
) -> ResumeTarget | None:
    """CLI bayraklarını açılış hedefine çevir. Hiçbiri verilmediyse `None` (yeni sohbet).

    `--continue` bu projedeki en son sohbeti, `--resume <kimlik|ad>` seçileni açar;
    `--fork-session` seçilenin kopyasını yeni kimlikle açar (özgün sohbet değişmez);
    `--name` yeni ya da sürdürülen sohbete ad verir. Bulunamayan sohbet
    `SessionNotFoundError` ile bildirilir; sessizce yeni sohbet açılmaz.
    """
    name = name.strip()
    from .resume_launch import RESUME_PICKER, pick_conversation

    if resume == RESUME_PICKER:
        # Argümansız `--resume` (#188): seçilen sohbetin kimliğiyle devam.
        resume = pick_conversation(memory_dir, root)
    if not continue_last and not resume.strip():
        if fork:
            # Ölçüldü (31 Ekim): bayrak sessizce yok sayılıp yeni boş sohbet açılıyordu.
            raise SessionNotFoundError(messages.SESSION_FORK_NEEDS_SOURCE)
        if not name:
            return None
        conversation_id = new_conversation_id()
        TranscriptStore(memory_dir, root, conversation_id=conversation_id).record_name(name)
        return ResumeTarget(conversation_id, (), name, name=name)
    if continue_last:
        refs = list_conversations(memory_dir, root)
        if not refs:
            raise SessionNotFoundError(messages.SESSION_NONE_TO_CONTINUE)
        ref = refs[0]
    else:
        found = find_conversation(memory_dir, root, resume)
        if found is None:
            raise SessionNotFoundError(messages.SESSION_NOT_FOUND.format(query=resume.strip()))
        ref = found
    history = tuple(load_transcript_messages(memory_dir, root, conversation_id=ref.conversation_id))
    if fork:
        target_id = fork_conversation(memory_dir, root, history, name=name or ref.name)
        linked_pr.save(memory_dir, target_id, linked_pr.load(memory_dir, ref.conversation_id))
        return ResumeTarget(
            target_id, history, ref.title, name=name or ref.name, forked_from=ref.conversation_id
        )
    if name:
        TranscriptStore(memory_dir, root, conversation_id=ref.conversation_id).record_name(name)
    return ResumeTarget(ref.conversation_id, history, name or ref.title, name=name or ref.name)


def fork_conversation(
    memory_dir: Path, root: Path, history: Sequence[Message], *, name: str = ""
) -> str:
    """Konuşmayı yeni bir kimliğe kopyala ve kimliği döndür (`ValueError`: kopya doğrulanamadı)."""
    target_id = new_conversation_id()
    copy_conversation(memory_dir, root, history, target_id=target_id, name=name)
    return target_id


def apply_target(state: ReplState, target: ResumeTarget) -> None:
    """Oturum durumunu seçilen sohbete bağla; motor geçmişi transcript'ten gelir."""
    state.conversation_id = target.conversation_id
    state.conversation_name = target.name
    state.history = list(target.history)
    state.last_changes = None
    # Başka sohbetin tur kayıtları bu konuşmaya ait değildir; PR künyesi sohbetinkidir.
    state.checkpoints.clear()
    linked_pr.restore(state)
    if target.history and not target.forked_from:
        # Claude Code (#187, #189): araç çağrıları/sonuçları, compaction özeti, model, izin
        # kipi ve checkpoint'ler kayıtlı oturum durumundan gelir; yoksa metin geçmişi kalır.
        from . import session_snapshot

        session_snapshot.restore(state)


def launch_notice(target: ResumeTarget) -> str:
    """Açılışta basılacak tek satır: sürdürüldü / kopyalandı / adlı yeni sohbet."""
    if target.forked_from:
        return messages.SESSION_FORKED.format(title=target.title, count=len(target.history))
    if not target.history:
        return messages.SESSION_NAMED_NEW.format(name=target.name)
    return messages.SESSION_RESUMED.format(title=target.title, count=len(target.history))


# --------------------------------------------------------------------------- #
# Slash komutları
# --------------------------------------------------------------------------- #


def resume_choices(refs: Sequence[ConversationRef]) -> list[Choice]:
    """Sohbet listesini seçim satırlarına çevir; düz REPL `pick()`, TUI kendi modalı kullanır."""
    return [
        Choice(
            ref.conversation_id,
            ref.title,
            messages.SESSION_CHOICE_DETAIL.format(
                when=_when(ref.updated_at), count=ref.message_count
            ),
        )
        for ref in refs[:SESSION_LIST_LIMIT]
    ]


def resume_command(state: ReplState, argument: str) -> str:
    """`/resume [kimlik|ad]` — bu projedeki bir Fusion sohbetini sürdür.

    Argüman DOLUYSA (TUI modalından ya da betikten) seçici açılmaz. Argüman BOŞSA
    düz REPL `pick()` ile seçtirir; TUI bu dalı kullanmaz, kendi modalını açar.
    """
    refs = list_conversations(state.config.memory_dir, state.root)
    if not refs:
        return messages.SESSION_LIST_EMPTY
    query = argument.strip()
    if not query:
        chosen = pick(resume_choices(refs), title=messages.SESSION_PICK_TITLE)
        if chosen is None:
            return ""
        query = chosen
    ref = find_conversation(state.config.memory_dir, state.root, query)
    if ref is None:
        return messages.SESSION_NOT_FOUND.format(query=query)
    if ref.conversation_id == state.conversation_id:
        return messages.SESSION_ALREADY_ACTIVE
    history = load_transcript_messages(
        state.config.memory_dir, state.root, conversation_id=ref.conversation_id
    )
    apply_target(state, ResumeTarget(ref.conversation_id, tuple(history), ref.title, name=ref.name))
    from . import session_agent

    if session_agent.load(state.config.memory_dir, state.conversation_id):
        note = session_agent.restore(state)
    else:
        note = ""
    resumed = messages.SESSION_RESUMED.format(title=ref.title, count=len(history))
    return f"{resumed}\n{note}" if note else resumed


def rename_command(state: ReplState, argument: str) -> str:
    """`/rename <ad>` — açık sohbete ad ver; `--resume <ad>` ile bulunur."""
    name = argument.strip()
    if not name:
        return messages.SESSION_RENAME_USAGE
    TranscriptStore(
        state.config.memory_dir, state.root, conversation_id=state.conversation_id
    ).record_name(name)
    state.conversation_name = name
    return messages.SESSION_RENAMED.format(name=name)


def branch_command(state: ReplState, argument: str) -> str:
    """`/branch [ad]` — konuşmayı yeni sohbete kopyala ve oradan sür; özgün sohbet değişmez."""
    if not any(message.role == "user" and message.content.strip() for message in state.history):
        return messages.SESSION_BRANCH_EMPTY
    name = argument.strip()
    try:
        target_id = fork_conversation(state.config.memory_dir, state.root, state.history, name=name)
    except (ValueError, OSError) as error:
        return messages.SESSION_COPY_FAILED.format(reason=error)
    count = len(conversation_prefix(state.history))
    state.conversation_id = target_id
    # Kopya aynı PR üzerinde sürer (Claude Code `--fork-session` ile aynı).
    linked_pr.save(state.config.memory_dir, target_id, state.linked_pr)
    state.conversation_name = name
    # Kopyanın dosya geçmişi yoktur: eski sohbetin `/undo`/`/rewind` kaydı yeni kimliğe taşınmaz.
    state.last_changes = None
    state.checkpoints.clear()
    return messages.SESSION_BRANCHED.format(count=count, name=f" ({name})" if name else "")


def _when(epoch: float) -> str:
    if not epoch:
        return ""
    return datetime.fromtimestamp(epoch).strftime("%d/%m %H:%M")
