"""Mevcut tur günlüğünü proje ve üst oturum sınırında alt ajana bağlar."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from ..core.agent_runtime_state import AgentRunState
from ..core.file_lease import FileLease
from ..core.types import Message
from .turn_journal import FileTurnJournal, JournalEntry
from .turn_journal_codec import message_to

MAX_AGENT_RECORDS = 128
MAX_JOURNAL_BYTES = 2_000_000
_AGENT_ID = re.compile(r"^[\w-]{1,96}$")


def agent_journal(
    memory: Path, root: Path, session: str, identifier: str, *, state: AgentRunState | None = None
) -> FileTurnJournal:
    """Kimlikten yol türet; modelden dosya yolu kabul etme."""
    if not session or not _AGENT_ID.fullmatch(identifier):
        raise ValueError("Ajan kimliği veya üst oturum geçersiz.")
    owner = hashlib.sha256(f"{root.resolve()}\0{session}".encode()).hexdigest()
    base = memory.resolve() / "subagents" / owner
    path = base / f"agent-{identifier}.json"
    if any(
        candidate.is_symlink()
        for candidate in (
            base.parent,
            base,
            path,
            path.with_suffix(path.suffix + ".original.jsonl"),
        )
    ):
        raise ValueError("Ajan günlüğünde sembolik bağlantı kullanılamaz.")
    if state is not None and not path.exists():
        _admit_record(base)
    return FileTurnJournal(path, original_owner_id=identifier, agent_state=state)


def load_agent(memory: Path, root: Path, session: str, identifier: str) -> JournalEntry | None:
    """Salt okuma; yabancı oturum, bozuk/büyük kayıt veya belirsiz kimlik açılmaz."""
    if not _AGENT_ID.fullmatch(identifier):
        return _load_named(memory, root, session, identifier)
    journal = agent_journal(memory, root, session, identifier)
    try:
        if journal.path.stat().st_size > MAX_JOURNAL_BYTES:
            raise ValueError("Ajan günlüğü boyut sınırını aşıyor.")
    except FileNotFoundError:
        return _load_named(memory, root, session, identifier)
    entry = journal.load()
    if entry is None or entry.agent_state is None:
        return None
    state = entry.agent_state
    if (
        state.agent_id != identifier
        or state.parent_session != session
        or state.root != str(root.resolve())
    ):
        raise ValueError("Ajan günlüğünün oturum veya proje sınırı uyuşmuyor.")
    return entry


class AgentTranscript:
    """Sıkıştırma öncesi üretici mesajlarını yakala; özetleri özgün diye ekleme."""

    def __init__(
        self, journal: FileTurnJournal, *, history: Sequence[Message] = (), complete_history: bool
    ) -> None:
        self.journal = journal
        self.messages = tuple(history)
        self.complete_history = complete_history
        self._cursor = 0
        self._started = False

    async def begin(self, messages: Sequence[Message]) -> None:
        if self._started or self.messages:
            self._cursor = max(0, len(messages) - 1)
        self._started = True
        await self.capture(messages)

    async def capture(self, messages: Sequence[Message]) -> None:
        if self._cursor > len(messages):
            self.complete_history = False
            self._cursor = len(messages)
        additions = tuple(messages[self._cursor :])
        self._cursor = len(messages)
        if any(message.images for message in additions):
            self.complete_history = False
        combined = (*self.messages, *additions)
        size = sum(
            len(json.dumps(message_to(message), ensure_ascii=False).encode())
            for message in combined
        )
        if size <= MAX_JOURNAL_BYTES - 8000:
            self.messages = combined
        else:
            self.complete_history = False
        if self.journal.agent_state is not None:
            self.journal.agent_state = replace(
                self.journal.agent_state, complete_history=self.complete_history
            )
        try:
            await asyncio.to_thread(self.journal.save, self.messages)
            saved = await asyncio.to_thread(self.journal.load)
            if saved is None or [message_to(item) for item in saved.messages] != [
                message_to(item) for item in self.messages
            ]:
                self.complete_history = False
        except OSError:
            self.complete_history = False
        if self.journal.agent_state is not None and not self.complete_history:
            self.journal.agent_state = replace(self.journal.agent_state, complete_history=False)

    def reset(self, messages: Sequence[Message]) -> None:
        self._cursor = len(messages)


@asynccontextmanager
async def agent_lease(journal: FileTurnJournal) -> AsyncIterator[None]:
    """Aynı kayıt iki süreçte eşzamanlı devam ettirilemez."""
    lease = FileLease(journal.path.with_suffix(".run.lock"))
    acquired = await asyncio.to_thread(lease.try_acquire)
    if not acquired:
        raise ValueError("Ajan başka bir çalıştırmada sürüyor.")
    try:
        yield
    finally:
        lease.close()


def _admit_record(folder: Path) -> None:
    lease = FileLease(folder / ".records.lock")
    if not lease.try_acquire():
        raise ValueError("Ajan kayıtları başka bir işlemde güncelleniyor.")
    try:
        paths = sorted(folder.glob("agent-*.json"), key=lambda path: path.stat().st_mtime)
        while len(paths) >= MAX_AGENT_RECORDS:
            removed = False
            for path in tuple(paths):
                if path.is_symlink():
                    continue
                entry = FileTurnJournal(path).load()
                if (
                    entry is None
                    or entry.agent_state is None
                    or entry.agent_state.status == "running"
                ):
                    continue
                candidate = FileLease(path.with_suffix(".run.lock"))
                if not candidate.try_acquire():
                    continue
                try:
                    path.unlink(missing_ok=True)
                    path.with_suffix(path.suffix + ".original.jsonl").unlink(missing_ok=True)
                finally:
                    candidate.close()
                paths.remove(path)
                removed = True
                break
            if not removed:
                raise ValueError(
                    "Saklanabilecek ajan sayısı doldu; çalışan görevlerin bitmesini bekleyin."
                )
    finally:
        lease.close()


def _load_named(memory: Path, root: Path, session: str, name: str) -> JournalEntry | None:
    """Adı yalnız aynı sahibin sınırlı ve doğrulanmış kayıtlarında ara."""
    from itertools import islice

    probe = agent_journal(memory, root, session, "probe")
    candidates = list(islice(probe.path.parent.glob("agent-*.json"), MAX_AGENT_RECORDS + 1))
    if len(candidates) > MAX_AGENT_RECORDS:
        raise ValueError("Ajan kayıt sınırı aşılmış.")
    found: list[JournalEntry] = []
    for path in candidates:
        if path.is_symlink() or path.stat().st_size > MAX_JOURNAL_BYTES:
            continue
        entry = FileTurnJournal(path).load()
        if entry is None or entry.agent_state is None:
            continue
        state = entry.agent_state
        if (
            state.name == name
            and state.parent_session == session
            and state.root == str(root.resolve())
        ):
            found.append(entry)
    if len(found) > 1:
        raise ValueError("Ajan adı belirsiz; kimliği kullanın.")
    return found[0] if found else None
