"""Tur günlüğü — süren turun atomik JSON kopyası (çökme sonrası devam için).

Dosya konuşma başınadır ve başarıyla kalıcılaşan turdan sonra silinir. Hata veya
iptalde korunur; sekme açılırken geri yüklenir. Görseller yazılmaz (data URI'ler
megabaytlarca olabilir ve devam için gerekmez); metin `redact`'tan geçer çünkü
araç çıktıları sır taşıyabilir ve dosya diskte kalır.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.clock import SystemClock
from ..core.file_lease import FileLease
from ..core.protocols import Clock
from ..core.redaction import redact
from ..core.types import Message, ToolCall

_LOG = logging.getLogger(__name__)
_SCHEMA = 1


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """Yarıda kalmış bir turun geri yüklenebilir hâli."""

    task: str
    messages: tuple[Message, ...]
    saved_at: float
    #: Kullanıcıya "yarıda kaldı" notu zaten gösterildi mi? İki kez yazılmasın.
    notified: bool
    revision: str = ""


class FileTurnJournal:
    """`TurnJournal` protokolünün dosya uygulaması."""

    def __init__(self, path: Path, *, task: str = "", clock: Clock | None = None) -> None:
        self._path = path
        #: Kullanıcıya "şu iş yarıda kaldı" diye gösterilecek görev metni.
        self._task = task
        self._clock = clock or SystemClock()

    @property
    def path(self) -> Path:
        return self._path

    def save(self, messages: Sequence[Message]) -> None:
        self._write(self._task, messages, notified=False)

    def load(self) -> JournalEntry | None:
        try:
            serialized = self._path.read_text(encoding="utf-8")
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
        messages = tuple(message for item in items if (message := _message_from(item)) is not None)
        return JournalEntry(
            task=str(raw.get("gorev", "")),
            messages=messages,
            saved_at=float(saved_at),
            notified=bool(raw.get("bildirildi", False)),
            revision=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        )

    def mark_notified(self, entry: JournalEntry) -> None:
        with self._transaction() as owned:
            if not owned or not entry.revision:
                return
            current = self.load()
            if current is not None and current.revision == entry.revision:
                self._write_payload(entry.task, entry.messages, notified=True)

    def clear(self) -> None:
        with self._transaction() as owned:
            if owned:
                with contextlib.suppress(FileNotFoundError):
                    self._path.unlink()

    def _write(self, task: str, messages: Sequence[Message], *, notified: bool) -> None:
        with self._transaction() as owned:
            if owned:
                self._write_payload(task, messages, notified=notified)

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[bool]:
        lease = FileLease(self._path.with_suffix(self._path.suffix + ".lock"))
        try:
            owned = lease.try_acquire()
            if not owned:
                _LOG.warning("tur günlüğü başka yazıcı tarafından kullanılıyor")
        except OSError as error:
            _LOG.warning("tur günlüğü kilitlenemedi", extra={"hata": type(error).__name__})
            owned = False
        try:
            yield owned
        finally:
            lease.close()

    def _write_payload(self, task: str, messages: Sequence[Message], *, notified: bool) -> None:
        payload = {
            "surum": _SCHEMA,
            "gorev": redact(task),
            "zaman": self._clock.now(),
            "bildirildi": notified,
            "mesajlar": [_message_to(message) for message in messages],
        }
        try:
            atomic_replace_text(self._path, json.dumps(payload, ensure_ascii=False))
        except OSError as error:
            # Günlük bir iyileştirmedir: yazılamaması turu düşürmez, yalnız log'lanır.
            _LOG.warning("tur günlüğü yazılamadı", extra={"hata": type(error).__name__})


def _message_to(message: Message) -> dict[str, object]:
    return {
        "rol": message.role,
        "icerik": redact(message.content),
        "araclar": [
            {"id": call.id, "ad": call.name, "arguman": redact(call.arguments)}
            for call in message.tool_calls
        ],
        "arac_id": message.tool_call_id,
        "ad": message.name,
        "ok": message.ok,
        "tool_diff": redact(message.tool_diff) if message.tool_diff is not None else None,
        "harness": message.harness_note,
    }


def _message_from(item: object) -> Message | None:
    if not isinstance(item, dict):
        return None
    role, content = item.get("rol"), item.get("icerik")
    if not isinstance(role, str) or not isinstance(content, str):
        return None
    raw_calls = item.get("araclar", [])
    if not isinstance(raw_calls, list):
        return None
    calls = tuple(
        ToolCall(
            id=str(call.get("id", "")),
            name=str(call.get("ad", "")),
            arguments=str(call.get("arguman", "")),
        )
        for call in raw_calls
        if isinstance(call, dict)
    )
    tool_call_id = item.get("arac_id")
    name = item.get("ad")
    ok = item.get("ok")
    return Message(
        role,
        content,
        tool_calls=calls,
        tool_call_id=tool_call_id if isinstance(tool_call_id, str) else None,
        name=name if isinstance(name, str) else None,
        ok=ok if isinstance(ok, bool) else None,
        tool_diff=item["tool_diff"] if isinstance(item.get("tool_diff"), str) else None,
        harness_note=bool(item.get("harness", False)),
    )
