"""Workspace'e özel kalıcı TUI transcript ve olay günlüğü.

Tam ekran terminal alternatif buffer kullandığı için terminal scrollback güvenilir değildir.
Bu depo, görünür konuşmanın kırpılmış bir anlık görüntüsünü ve redakte edilmiş JSONL
olaylarını kullanıcı memory dizininde atomik biçimde saklar.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from ...core.events import Event
from ...core.redaction import redact
from ...core.types import Message

_MAX_SNAPSHOT_BYTES = 1_500_000
_MAX_EVENTS_BYTES = 8_000_000
_MAX_HISTORY_MESSAGES = 100


def load_transcript_messages(base_dir: Path, root: Path) -> list[Message]:
    """Load resumable user/final-answer messages for one workspace without writing."""
    digest = hashlib.sha256(str(root.expanduser().resolve()).encode()).hexdigest()[:16]
    path = base_dir.expanduser().resolve() / "transcripts" / digest / "events.jsonl"
    messages: list[Message] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return messages
    for line in lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        text = event.get("text") if isinstance(event, dict) else None
        if not isinstance(text, str) or not text.strip():
            continue
        safe_text = redact(text)
        if event.get("event") == "UserMessage":
            messages.append(Message("user", safe_text))
        elif event.get("event") == "TurnAnswered":
            messages.append(Message("assistant", safe_text))
    return messages[-_MAX_HISTORY_MESSAGES:]


class TranscriptStore:
    """Bir workspace için son transcript ve denetlenebilir olay günlüğü."""

    def __init__(self, base_dir: Path, root: Path) -> None:
        digest = hashlib.sha256(str(root.expanduser().resolve()).encode()).hexdigest()[:16]
        self.base_dir = base_dir.expanduser().resolve() / "transcripts" / digest
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # İzin daraltma bir sıkılaştırmadır, ön koşul değil: chmod desteklemeyen
        # dosya sisteminde (Windows paylaşımı, bazı konteyner mount'ları) transcript
        # yine yazılabilmelidir.
        with contextlib.suppress(OSError):
            self.base_dir.chmod(0o700)
        self.snapshot_path = self.base_dir / "latest.ansi"
        self.events_path = self.base_dir / "events.jsonl"
        self.session_id = f"session-{int(time.time())}-{uuid.uuid4().hex[:8]}"

    def load_snapshot(self) -> str:
        try:
            return self.snapshot_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def save_snapshot(self, text: str) -> None:
        safe = redact(text)
        encoded = safe.encode("utf-8", errors="replace")
        if len(encoded) > _MAX_SNAPSHOT_BYTES:
            encoded = encoded[-_MAX_SNAPSHOT_BYTES:]
            # UTF-8 kesim sınırını temizle.
            safe = encoded.decode("utf-8", errors="ignore")
            safe = "\n[önceki transcript boyut sınırı nedeniyle kırpıldı]\n" + safe
        temporary = self.snapshot_path.with_suffix(".tmp")
        try:
            temporary.write_text(safe, encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(self.snapshot_path)
        except OSError:
            # Anlık görüntü yazılamadıysa yarım geçici dosyayı bırakma. Temizliğin
            # kendisi de başarısız olabilir (disk dolu, izin yok); o durumda yapılacak
            # bir şey yoktur ve transcript kaydı turu düşürmemelidir.
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)

    def record_user(self, text: str) -> None:
        self._append({"event": "UserMessage", "text": text})

    def record_assistant(self, text: str) -> None:
        self._append({"event": "TurnAnswered", "channel": "text", "text": text})

    def handle(self, event: Event) -> None:
        # JSONL sınırı: alan değerleri olay tipine göre değişir ve `_jsonable`
        # bunları serileştirilebilir bir değere indirger. `Any` bu sınırda kalır.
        payload: dict[str, Any] = {"event": type(event).__name__}
        for field in dataclasses.fields(event):
            payload[field.name] = _jsonable(getattr(event, field.name))
        self._append(payload)

    def _append(self, payload: dict[str, Any]) -> None:
        payload = {
            "session_id": self.session_id,
            "timestamp": time.time(),
            **payload,
        }
        line = redact(json.dumps(payload, ensure_ascii=False, default=str)) + "\n"
        try:
            self._rotate_if_needed()
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
            self.events_path.chmod(0o600)
        except OSError:
            return

    def _rotate_if_needed(self) -> None:
        try:
            if self.events_path.stat().st_size < _MAX_EVENTS_BYTES:
                return
        except OSError:
            return
        older = self.events_path.with_suffix(".jsonl.1")
        try:
            older.unlink(missing_ok=True)
            self.events_path.replace(older)
        except OSError:
            return


def _jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
