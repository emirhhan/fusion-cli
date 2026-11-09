"""Tur günlüğü: atomik devam snapshot'ı ve ayrı, maskelenmiş özgün segmentler.

İki kayıt aynı kilit ve clear yaşam döngüsünü paylaşır; snapshot özgün iz değildir.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import math
import os
import tempfile
import threading
import time
import weakref
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.agent_runtime_state import AgentRunState
from ..core.atomic_file import atomic_replace_text
from ..core.clock import SystemClock
from ..core.file_lease import FileLease
from ..core.optional_mutation import OptionalMutationWorker
from ..core.optional_read import OptionalReadWorker
from ..core.original_trace import OriginalTraceRead, OriginalTraceScope
from ..core.protocols import Clock
from ..core.redaction import redact
from ..core.types import Message
from .turn_journal_codec import (
    agent_state_from,
    agent_state_to,
    message_from,
    message_to,
    original_messages_from,
)

_LOG = logging.getLogger(__name__)
_SCHEMA = 1
_ORIGINAL_SCHEMA = 1
_ORIGINAL_FILE_BYTES = 2_000_000
_MAX_JOURNAL_BYTES = 64 * 1024 * 1024
_MAX_JOURNAL_IMAGE_CHARS = 56 * 1024 * 1024
#: Günlük kilidi için bekleme: en çok `_LOCK_ATTEMPTS * _LOCK_RETRY_S` ≈ 0,6 sn.
_LOCK_ATTEMPTS = 12
_LOCK_RETRY_S = 0.05
ORIGINAL_READ_TIMEOUT_S = 1.0
ORIGINAL_WRITE_TIMEOUT_S = 1.0
_original_reader = OptionalReadWorker("fusion-original-read")
_original_writer = OptionalMutationWorker("fusion-original-write")


class _OriginalReadEpoch:
    def __init__(self) -> None:
        self.generation = 0
        self.mutation_lock = threading.Lock()
        self.generation_lock = threading.Lock()


_read_epochs: weakref.WeakValueDictionary[str, _OriginalReadEpoch] = weakref.WeakValueDictionary()
_read_epochs_lock = threading.Lock()


def _read_epoch(path: Path) -> _OriginalReadEpoch:
    """Live handles for one owned path share invalidation, without a growing path cache."""
    # Keep construction filesystem-free; resolving symlinks can block on I/O.
    key = os.path.abspath(path)  # noqa: PTH100
    with _read_epochs_lock:
        epoch = _read_epochs.get(key)
        if epoch is None:
            epoch = _OriginalReadEpoch()
            _read_epochs[key] = epoch
        return epoch


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """Yarıda kalmış bir turun geri yüklenebilir hâli."""

    task: str
    messages: tuple[Message, ...]
    saved_at: float
    #: Kullanıcıya "yarıda kaldı" notu zaten gösterildi mi? İki kez yazılmasın.
    notified: bool
    revision: str = ""
    agent_state: AgentRunState | None = None
    execution_finished: bool = False


class FileTurnJournal:
    """`TurnJournal` protokolünün dosya uygulaması."""

    def __init__(
        self,
        path: Path,
        *,
        task: str = "",
        clock: Clock | None = None,
        original_owner_id: str = "",
        agent_state: AgentRunState | None = None,
    ) -> None:
        self._path = path
        #: Kullanıcıya "şu iş yarıda kaldı" diye gösterilecek görev metni.
        self._task = task
        self._clock = clock or SystemClock()
        self._original_owner_id = original_owner_id
        self._original_read_epoch = _read_epoch(path)
        self.agent_state = agent_state

    @property
    def path(self) -> Path:
        return self._path

    def save(self, messages: Sequence[Message]) -> None:
        self._write(self._task, messages, notified=False)

    def save_finished(self, messages: Sequence[Message]) -> None:
        """Keep continuation context after execution ended, without claiming a crash."""
        self._write(self._task, messages, notified=False, execution_finished=True)

    def load(self) -> JournalEntry | None:
        try:
            with self._path.open(encoding="utf-8") as stream:
                serialized = stream.read(_MAX_JOURNAL_BYTES + 1)
            if len(serialized) > _MAX_JOURNAL_BYTES:
                return None
            raw = json.loads(serialized)
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            _LOG.warning("tur günlüğü okunamadı", extra={"hata": type(error).__name__})
            return None
        if (
            not isinstance(raw, dict)
            or isinstance(raw.get("surum"), bool)
            or raw.get("surum") != _SCHEMA
        ):
            return None
        items = raw.get("mesajlar", [])
        saved_at = raw.get("zaman", 0.0)
        if (
            not isinstance(items, list)
            or isinstance(saved_at, bool)
            or not isinstance(saved_at, int | float)
            or not math.isfinite(saved_at)
            or saved_at < 0
        ):
            return None
        parsed = tuple(message_from(item) for item in items)
        if any(message is None for message in parsed):
            # Okunamayan bir mesajı sessizce süzmek `assistant tool_calls` / `tool`
            # çiftini bozar (sağlayıcılar yetim `tool` mesajında 400 verir).
            _LOG.warning("tur günlüğünde okunamayan mesaj var; günlük yok sayıldı")
            return None
        messages = tuple(message for message in parsed if message is not None)
        return JournalEntry(
            task=str(raw.get("gorev", "")),
            messages=messages,
            saved_at=float(saved_at),
            notified=bool(raw.get("bildirildi", False)),
            revision=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            agent_state=agent_state_from(raw.get("ajan")),
            execution_finished=raw.get("execution_finished") is True,
        )

    def mark_notified(self, entry: JournalEntry) -> None:
        with self._transaction() as owned:
            if not owned or not entry.revision:
                return
            current = self.load()
            if current is not None and current.revision == entry.revision:
                self._write_payload(
                    entry.task,
                    entry.messages,
                    notified=True,
                    execution_finished=entry.execution_finished,
                )

    def clear(self) -> None:
        # Pending optional reads lose ownership even if deletion cannot get the lease.
        with self._original_read_epoch.generation_lock:
            self._original_read_epoch.generation += 1
        # Synchronous clear serializes with final publication, never with staging.
        # If an OS replace is already in flight, clear must wait for it, then delete.
        with self._original_read_epoch.mutation_lock, self._transaction() as owned:
            if owned:
                for path in (self._path, self.original_path):
                    with contextlib.suppress(FileNotFoundError):
                        path.unlink()

    @property
    def original_owner_id(self) -> str:
        """Composition sınırının atadığı sahip; modelden türetilmez."""
        return self._original_owner_id

    @property
    def original_path(self) -> Path:
        """Aynı günlük sahibinin özgün segment dosyası; clear ile birlikte silinir."""
        return self._path.with_suffix(self._path.suffix + ".original.jsonl")

    async def append_original(self, scope: OriginalTraceScope, messages: Sequence[Message]) -> bool:
        """Gerçek üretici mesajlarını ekle; snapshot veya özet bu kaynağa dönüşmez."""
        if not self._owns_scope(scope) or len(scope.segment_ids) != 1:
            return False
        if not OriginalTraceRead(scope, "redacted_original", tuple(messages)).is_usable():
            return False
        epoch, path = self._original_read_epoch, self._path
        generation = epoch.generation
        return await _original_writer.run(
            lambda valid: self._append_original(scope, tuple(messages), valid),
            timeout_s=ORIGINAL_WRITE_TIMEOUT_S,
            still_owned=lambda: (
                self._owns_scope(scope)
                and self._path == path
                and self._original_read_epoch is epoch
                and epoch.generation == generation
            ),
        )

    async def read_original(self, scope: OriginalTraceScope) -> OriginalTraceRead:
        """Sahibi doğrula, ardından yalnız istenen tur ve segment kapsamını döndür."""
        if not self._owns_scope(scope):
            return OriginalTraceRead(scope, "invalid_scope")
        generation = self._original_read_epoch.generation
        return await _original_reader.run(
            lambda _valid: self._read_original(scope),
            timeout_s=ORIGINAL_READ_TIMEOUT_S,
            fallback=OriginalTraceRead(scope, "unavailable"),
            still_owned=lambda: self._original_read_epoch.generation == generation,
        )

    def _owns_scope(self, scope: OriginalTraceScope) -> bool:
        return (
            bool(self._original_owner_id)
            and scope.is_valid()
            and (scope.owner_id == self._original_owner_id)
        )

    def _append_original(
        self,
        scope: OriginalTraceScope,
        messages: tuple[Message, ...],
        valid: Callable[[], bool],
    ) -> bool:
        if not valid():
            return False
        record = {
            "surum": _ORIGINAL_SCHEMA,
            "sahip": hashlib.sha256(scope.owner_id.encode()).hexdigest(),
            "tur": scope.turn_id,
            "segment": scope.segment_ids[0],
            "mesajlar": [message_to(message) for message in messages],
        }
        # Argüman normalizasyonu büyüyebilir; diske gidecek değerleri yeniden doğrula.
        published = original_messages_from(record["mesajlar"])
        if (
            published is None
            or not OriginalTraceRead(scope, "redacted_original", published).is_usable()
        ):
            return False
        staged: Path | None = None
        try:
            with self._transaction() as owned:
                if not owned or not valid():
                    return False
                records = self._original_records()
                if records is None:
                    return False
                call_ids = _original_call_ids(record)
                for previous in records:
                    if previous["tur"] != scope.turn_id:
                        continue
                    if previous["segment"] == scope.segment_ids[0]:
                        return previous == record
                    if call_ids & _original_call_ids(previous):
                        return False
            serialized = "".join(
                json.dumps(row, ensure_ascii=False) + "\n" for row in [*records, record]
            )
            if len(serialized.encode()) > _ORIGINAL_FILE_BYTES or not valid():
                return False
            staged = self._stage_original(serialized)
            if not valid():
                return False
            with self._original_read_epoch.mutation_lock, self._transaction() as owned:
                if not owned or not valid():
                    return False
                # Another process may have appended while we staged. Do not overwrite
                # its segment or retry with stale data; optional capture fails closed.
                if self._original_records() != records or not valid():
                    return False
                staged.replace(self.original_path)
                return True
        except (OSError, UnicodeError, ValueError) as error:
            _LOG.warning("özgün segment yazılamadı", extra={"hata": type(error).__name__})
            return False
        finally:
            if staged is not None:
                with contextlib.suppress(OSError):
                    staged.unlink(missing_ok=True)

    def _stage_original(self, serialized: str) -> Path:
        """Write/fsync private staging outside the publication/clear critical section."""
        self.original_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, name = tempfile.mkstemp(
            prefix=".fusion-original-", suffix=".tmp", dir=self.original_path.parent
        )
        staged = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            return staged
        except BaseException:
            with contextlib.suppress(OSError):
                staged.unlink(missing_ok=True)
            raise

    def _original_records(self) -> list[dict[str, object]] | None:
        try:
            if (
                self.original_path.is_symlink()
                or self.original_path.stat().st_size > _ORIGINAL_FILE_BYTES
            ):
                return None
            descriptor = os.open(self.original_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, encoding="utf-8") as stream:
                serialized = stream.read(_ORIGINAL_FILE_BYTES + 1)
        except FileNotFoundError:
            return []
        if len(serialized) > _ORIGINAL_FILE_BYTES or not serialized.endswith("\n"):
            return None
        records: list[dict[str, object]] = []
        for line in serialized.splitlines():
            raw = json.loads(line)
            if (
                not isinstance(raw, dict)
                or not isinstance(raw.get("surum"), int)
                or isinstance(raw.get("surum"), bool)
                or raw.get("surum") != _ORIGINAL_SCHEMA
                or not isinstance(raw.get("tur"), str)
                or not isinstance(raw.get("segment"), str)
                or raw.get("sahip") != hashlib.sha256(self._original_owner_id.encode()).hexdigest()
                or set(raw) != {"surum", "sahip", "tur", "segment", "mesajlar"}
            ):
                return None
            messages = original_messages_from(raw["mesajlar"])
            scope = OriginalTraceScope(self._original_owner_id, raw["tur"], (raw["segment"],))
            if (
                messages is None
                or not OriginalTraceRead(scope, "redacted_original", messages).is_usable()
            ):
                return None
            records.append(raw)
        return records

    def _read_original(self, scope: OriginalTraceScope) -> OriginalTraceRead:
        try:
            records = self._original_records()
        except (OSError, UnicodeError, ValueError) as error:
            _LOG.warning("özgün segment okunamadı", extra={"hata": type(error).__name__})
            return OriginalTraceRead(scope, "unavailable")
        if records is None:
            return OriginalTraceRead(scope, "incomplete")
        if not records:
            return OriginalTraceRead(scope, "missing")
        selected = [
            record
            for record in records
            if record.get("tur") == scope.turn_id and record.get("segment") in scope.segment_ids
        ]
        if tuple(record["segment"] for record in selected) != scope.segment_ids:
            return OriginalTraceRead(scope, "incomplete")
        messages: list[Message] = []
        for record in selected:
            decoded = original_messages_from(record["mesajlar"])
            if decoded is None:
                return OriginalTraceRead(scope, "incomplete")
            messages.extend(decoded)
        size = sum(
            len(message.content) + sum(len(call.arguments) for call in message.tool_calls)
            for message in messages
        )
        if size > scope.max_chars:
            return OriginalTraceRead(scope, "truncated")
        result = OriginalTraceRead(scope, "redacted_original", tuple(messages))
        return result if result.is_usable() else OriginalTraceRead(scope, "incomplete")

    def _write(
        self,
        task: str,
        messages: Sequence[Message],
        *,
        notified: bool,
        execution_finished: bool = False,
    ) -> None:
        with self._transaction() as owned:
            if owned:
                self._write_payload(
                    task, messages, notified=notified, execution_finished=execution_finished
                )

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[bool]:
        lease = FileLease(self._path.with_suffix(self._path.suffix + ".lock"))
        try:
            owned = self._acquire(lease)
            if not owned:
                _LOG.warning("tur günlüğü başka yazıcı tarafından kullanılıyor")
        except OSError as error:
            _LOG.warning("tur günlüğü kilitlenemedi", extra={"hata": type(error).__name__})
            owned = False
        try:
            yield owned
        finally:
            lease.close()

    @staticmethod
    def _acquire(lease: FileLease) -> bool:
        """Geçici kilit çakışmasında biten turu diriltmemek için kısa süre bekle."""
        for attempt in range(_LOCK_ATTEMPTS):
            if lease.try_acquire():
                return True
            if attempt + 1 < _LOCK_ATTEMPTS:
                time.sleep(_LOCK_RETRY_S)
        return False

    def _write_payload(
        self,
        task: str,
        messages: Sequence[Message],
        *,
        notified: bool,
        execution_finished: bool = False,
    ) -> None:
        encoded = []
        image_chars = 0
        for message in messages:
            item = message_to(message, include_images=True)
            images = item.get("gorseller", [])
            size = (
                sum(len(image) for image in images if isinstance(image, str))
                if isinstance(images, list)
                else 0
            )
            if image_chars + size > _MAX_JOURNAL_IMAGE_CHARS:
                item.pop("gorseller", None)
                item["icerik"] = (
                    str(item["icerik"])
                    + "\n[Günlük görsel bütçesi aşıldı; görselleri yeniden ekleyin.]"
                )
            else:
                image_chars += size
            encoded.append(item)
        payload = {
            "surum": _SCHEMA,
            "gorev": redact(task),
            "zaman": self._clock.now(),
            "bildirildi": notified,
            "mesajlar": encoded,
            "execution_finished": execution_finished,
        }
        if self.agent_state is not None:
            payload["ajan"] = agent_state_to(self.agent_state)
        try:
            atomic_replace_text(self._path, json.dumps(payload, ensure_ascii=False))
        except OSError as error:
            # Günlük bir iyileştirmedir: yazılamaması turu düşürmez, yalnız log'lanır.
            _LOG.warning("tur günlüğü yazılamadı", extra={"hata": type(error).__name__})


def _original_call_ids(record: dict[str, object]) -> set[str]:
    """Yalnız katı ayrıştırıcıdan geçmiş segmentin çağrı kimliklerini topla."""
    messages = original_messages_from(record.get("mesajlar"))
    if messages is None:
        return set()
    return {call.id for message in messages for call in message.tool_calls}
