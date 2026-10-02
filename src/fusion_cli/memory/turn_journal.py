"""Tur günlüğü — süren turun atomik JSON kopyası (çökme sonrası devam için).

Dosya konuşma başınadır ve tur bitince silinir. Kalmışsa süreç turun ortasında
kapanmış demektir; sekme açılırken geri yüklenir. Görseller yazılmaz (data URI'ler
megabaytlarca olabilir ve devam için gerekmez); metin `redact`'tan geçer çünkü
araç çıktıları sır taşıyabilir ve dosya diskte kalır.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.clock import SystemClock
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
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            _LOG.warning("tur günlüğü okunamadı", extra={"hata": str(error)})
            return None
        if not isinstance(raw, dict) or raw.get("surum") != _SCHEMA:
            return None
        messages = tuple(
            message
            for item in raw.get("mesajlar", [])
            if (message := _message_from(item)) is not None
        )
        return JournalEntry(
            task=str(raw.get("gorev", "")),
            messages=messages,
            saved_at=float(raw.get("zaman", 0.0)),
            notified=bool(raw.get("bildirildi", False)),
        )

    def mark_notified(self, entry: JournalEntry) -> None:
        self._write(entry.task, entry.messages, notified=True)

    def clear(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()

    def _write(self, task: str, messages: Sequence[Message], *, notified: bool) -> None:
        payload = {
            "surum": _SCHEMA,
            "gorev": redact(task),
            "zaman": self._clock.now(),
            "bildirildi": notified,
            "mesajlar": [_message_to(message) for message in messages],
        }
        temporary = self._path.with_suffix(".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with contextlib.suppress(OSError):
                temporary.chmod(0o600)
            temporary.replace(self._path)
        except OSError as error:
            # Günlük bir iyileştirmedir: yazılamaması turu düşürmez, yalnız log'lanır.
            _LOG.warning("tur günlüğü yazılamadı", extra={"hata": str(error)})


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
        "harness": message.harness_note,
    }


def _message_from(item: object) -> Message | None:
    if not isinstance(item, dict):
        return None
    role, content = item.get("rol"), item.get("icerik")
    if not isinstance(role, str) or not isinstance(content, str):
        return None
    calls = tuple(
        ToolCall(
            id=str(call.get("id", "")),
            name=str(call.get("ad", "")),
            arguments=str(call.get("arguman", "")),
        )
        for call in item.get("araclar", [])
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
        harness_note=bool(item.get("harness", False)),
    )
