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


def load_transcript_messages(
    base_dir: Path, root: Path, *, conversation_id: str | None = None
) -> list[Message]:
    """Bir workspace'in sürdürülebilir kullanıcı/cevap mesajlarını yaz-madan oku.

    `conversation_id` verilirse YALNIZ o konuşmanın satırları döner. Uygulamada
    aynı proje kökünde birden çok sekme açılabilir; kimlik olmadan hepsi tek bir
    geçmişte birikir ve bir sekmeye tıklayan kullanıcı başka bir sekmenin
    konuşmasını görür. TUI kimlik vermez ve proje genelini okumaya devam eder.
    """
    digest = _workspace_digest(root)
    path = base_dir.expanduser().resolve() / "transcripts" / digest / "events.jsonl"
    deleted = _deleted_conversations(path.parent)
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
        if not isinstance(event, dict):
            continue
        if _conversation_digest(event.get("session_id")) in deleted:
            continue
        if conversation_id is not None and event.get("session_id") != conversation_id:
            continue
        text = event.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        safe_text = redact(text)
        if event.get("event") == "UserMessage":
            messages.append(Message("user", safe_text))
        elif event.get("event") == "TurnAnswered":
            messages.append(Message("assistant", safe_text))
    return messages[-_MAX_HISTORY_MESSAGES:]


def _conversation_digest(conversation_id: object) -> str:
    return hashlib.sha256(str(conversation_id).encode()).hexdigest()


def _deleted_conversations(directory: Path) -> set[str]:
    deleted = directory / "deleted"
    try:
        return {entry.name for entry in deleted.iterdir()}
    except FileNotFoundError:
        return set()


def delete_conversation(base_dir: Path, root: Path, conversation_id: str) -> None:
    """Kimliği kalıcı olarak kaldır; geç gelen olaylar sohbeti diriltmesin.

    Her kimlik ayrı işaret taşır: eşzamanlı süreçler ortak olay dosyasını
    yeniden yazmaz ve başka sohbetlerin mesajlarını kaybetmez. Denetim
    günlüğü korunur; silinen sohbet listeye ve model bağlamına alınmaz.
    """
    directory = base_dir.expanduser().resolve() / "transcripts" / _workspace_digest(root)
    deleted = directory / "deleted"
    deleted.mkdir(parents=True, exist_ok=True, mode=0o700)
    (deleted / _conversation_digest(conversation_id)).touch(mode=0o600, exist_ok=True)


def _workspace_digest(root: Path) -> str:
    """Workspace kökünün depo dizin adı. Tek yerde durur ki okuma ve yazma ayrışmasın."""
    return hashlib.sha256(str(root.expanduser().resolve()).encode()).hexdigest()[:16]


#: Sohbet listesinde gösterilecek başlığın en fazla uzunluğu.
#
# Başlık bir ÖZET değil, tanıma ipucudur: kullanıcı kendi cümlesinin ilk satırından
# konuşmayı tanır. Uzun metin listeyi okunmaz hâle getirir.
TITLE_BUDGET = 80


@dataclasses.dataclass(frozen=True, slots=True)
class ConversationRef:
    """Diskte duran bir sohbetin listelenebilir künyesi."""

    conversation_id: str
    title: str
    updated_at: float
    message_count: int


def list_conversations(base_dir: Path, root: Path) -> tuple[ConversationRef, ...]:
    """Bir workspace'te kayıtlı sohbetleri en yeniden eskiye sırala.

    Ölçüldü (kullanıcının diski, 8 Eylül): 110 sohbet transcript dosyalarında
    duruyordu ama arayüz yalnız AÇIK sekmeleri gösteriyordu; dünkü konuşmaya
    ulaşmanın hiçbir yolu yoktu. Ulaşılamayan geçmiş, yok sayılmış geçmiştir.

    Kullanıcı mesajı olmayan kayıt sohbet sayılmaz: yalnız araç olayı taşıyan
    bir kimlik kullanıcı için hiçbir şey ifade etmez.
    """
    digest = _workspace_digest(root)
    path = base_dir.expanduser().resolve() / "transcripts" / digest / "events.jsonl"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()
    deleted = _deleted_conversations(path.parent)
    titles: dict[str, str] = {}
    stamps: dict[str, float] = {}
    counts: dict[str, int] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict) or event.get("event") not in {
            "UserMessage",
            "TurnAnswered",
        }:
            continue
        conversation = event.get("session_id")
        if _conversation_digest(conversation) in deleted:
            continue
        text = event.get("text")
        if not isinstance(conversation, str) or not isinstance(text, str) or not text.strip():
            continue
        counts[conversation] = counts.get(conversation, 0) + 1
        stamp = event.get("timestamp")
        if isinstance(stamp, (int, float)):
            stamps[conversation] = max(stamps.get(conversation, 0.0), float(stamp))
        if event.get("event") == "UserMessage" and conversation not in titles:
            titles[conversation] = redact(text.strip().splitlines()[0])[:TITLE_BUDGET]
    refs = tuple(
        ConversationRef(
            conversation_id=conversation,
            title=title,
            updated_at=stamps.get(conversation, 0.0),
            message_count=counts.get(conversation, 0),
        )
        for conversation, title in titles.items()
    )
    return tuple(sorted(refs, key=lambda ref: ref.updated_at, reverse=True))


class TranscriptStore:
    """Bir workspace için son transcript ve denetlenebilir olay günlüğü."""

    def __init__(self, base_dir: Path, root: Path, *, conversation_id: str | None = None) -> None:
        digest = _workspace_digest(root)
        self.base_dir = base_dir.expanduser().resolve() / "transcripts" / digest
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # İzin daraltma bir sıkılaştırmadır, ön koşul değil: chmod desteklemeyen
        # dosya sisteminde (Windows paylaşımı, bazı konteyner mount'ları) transcript
        # yine yazılabilmelidir.
        with contextlib.suppress(OSError):
            self.base_dir.chmod(0o700)
        self.snapshot_path = self.base_dir / "latest.ansi"
        self.events_path = self.base_dir / "events.jsonl"
        # Kimlik dışarıdan geldiğinde ONA yazılır: uygulamanın sekmesi kapanıp
        # yeniden açıldığında aynı kimlikle bağlanır ve konuşma kaldığı yerden
        # sürer. Kimlik verilmezse (TUI) her koşu kendi kimliğini üretir.
        self.session_id = conversation_id or f"session-{int(time.time())}-{uuid.uuid4().hex[:8]}"

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
        if _conversation_digest(self.session_id) in _deleted_conversations(self.base_dir):
            return
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
