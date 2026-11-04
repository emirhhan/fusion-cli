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
import os
import time
import uuid
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from ...core.events import Event
from ...core.leak_filter import is_harness_note, strip_harness_leaks
from ...core.redaction import redact
from ...core.types import Message
from ...core.worktree import project_root_of

_MAX_SNAPSHOT_BYTES = 1_500_000
_MAX_HISTORY_MESSAGES = 100
_REQUIREMENT_EVENT = "ConversationOriginalRequirement"
_REQUIREMENT_NAME = "transcript.original_requirement"
_REQUIREMENT_NOTE_CHARS = 8400

#: Sohbete ad verme olayı (`/rename`, `--name`). Mesaj değildir; listede başlık olur.
_NAME_EVENT = "ConversationNamed"
#: Kopyanın kaynağı (`/branch`, `--fork-session`, `/fork`); seçici dalları gruplar (#202).
_FORK_EVENT = "ConversationForked"
#: Konuşmanın geri sarıldığı olay (`/rewind`): ilk `keep_users` kullanıcı mesajı ve
#: cevapları kalır, sonrası düşer. Sayım KULLANICI mesajıyla yapılır: motor geçmişindeki
#: araç/ara mesajlar transcript'te yoktur, kullanıcı mesajı ise iki tarafta da birdir.
#: Olay günlüğü EKLEMELİDİR; silinen mesajlar denetim için dosyada kalır, yalnız
#: yüklemede atlanır.
_REWIND_EVENT = "ConversationRewound"
#: `--resume <kimlik-öneki>` için önekin en az uzunluğu; daha kısası yanlış sohbeti açar.
_ID_PREFIX_MIN = 6


def load_transcript_messages(
    base_dir: Path,
    root: Path,
    *,
    conversation_id: str | None = None,
    events_path: Path | None = None,
) -> list[Message]:
    """Bir workspace'in sürdürülebilir kullanıcı/cevap mesajlarını yaz-madan oku.

    `conversation_id` verilirse YALNIZ o konuşmanın satırları döner. Uygulamada
    aynı proje kökünde birden çok sekme açılabilir; kimlik olmadan hepsi tek bir
    geçmişte birikir ve bir sekmeye tıklayan kullanıcı başka bir sekmenin
    konuşmasını görür. TUI kimlik vermez ve proje genelini okumaya devam eder.
    """
    # `events_path`: başka projenin dosyası (`--resume <kimlik>` projeler arası arama, #203).
    path = events_path or transcript_events_path(base_dir, root)
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
        if event.get("event") == _REWIND_EVENT:
            keep = event.get("keep_users")
            if isinstance(keep, int) and not isinstance(keep, bool) and keep >= 0:
                _truncate_after_users(messages, keep)
            continue
        text = event.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        safe_text = strip_harness_leaks(redact(text))
        if not safe_text or (event.get("event") == "UserMessage" and is_harness_note(text)):
            continue
        if event.get("event") == _REQUIREMENT_EVENT:
            messages.append(
                Message(
                    "user",
                    safe_text[:_REQUIREMENT_NOTE_CHARS],
                    harness_note=True,
                    name=_REQUIREMENT_NAME,
                )
            )
        elif event.get("event") == "UserMessage":
            _upsert_message(
                messages, Message("user", safe_text, message_id=event.get("message_id"))
            )
        elif event.get("event") == "TurnAnswered":
            _upsert_message(
                messages, Message("assistant", safe_text, message_id=event.get("message_id"))
            )
    return _bounded_history(messages)


def _bounded_history(messages: list[Message]) -> list[Message]:
    """Keep recent context and one bounded, explicitly identified original requirement."""
    if len(messages) <= _MAX_HISTORY_MESSAGES:
        return messages
    tail = messages[-(_MAX_HISTORY_MESSAGES - 1) :]
    requirement = next((m for m in messages if _is_requirement_note(m)), None)
    if requirement is not None:
        return [
            dataclasses.replace(requirement, content=requirement.content[:_REQUIREMENT_NOTE_CHARS]),
            *tail,
        ]
    omitted = messages[: len(messages) - len(tail)]
    first = next((m for m in omitted if m.role == "user" and not m.harness_note), None)
    text = "Geçmişin eski bölümü bağlam sınırı nedeniyle kısaltıldı."
    if first is not None:
        text += "\nİlk kullanıcı isteği (en fazla 8000 karakter):\n" + first.content[:8000]
        if len(first.content) > 8000:
            text += "\n[İlk istek kısaltıldı; tam metin transcript kaydında.]"
    return [Message("user", text, harness_note=True, name=_REQUIREMENT_NAME), *tail]


def _is_requirement_note(message: Message) -> bool:
    return message.role == "user" and message.harness_note and message.name == _REQUIREMENT_NAME


#: Konuşmayı değiştiren olaylar; `last_turn_timestamp` yalnız bunlara bakar (ad vermek sayılmaz).
_TURN_EVENTS = frozenset({"UserMessage", "TurnAnswered", _REWIND_EVENT})


def last_turn_timestamp(base_dir: Path, root: Path, conversation_id: str) -> float:
    """Sohbetin son mesaj/geri sarma olayının zamanı; hiç yoksa 0.

    Oturum anlık görüntüsü (`session_snapshot`) bundan yeniyse transcript'ten tam
    geçmişe geçilir; transcript daha yeniyse (ör. sohbet masaüstünde sürdü) metin geçmişi
    kullanılır.
    """
    path = (
        base_dir.expanduser().resolve() / "transcripts" / _workspace_digest(root) / "events.jsonl"
    )
    latest = 0.0
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return latest
    for line in lines:
        if conversation_id not in line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict) or event.get("session_id") != conversation_id:
            continue
        stamp = event.get("timestamp")
        if event.get("event") in _TURN_EVENTS and isinstance(stamp, int | float):
            latest = max(latest, float(stamp))
    return latest


def read_workspace_events(base_dir: Path, root: Path) -> list[dict[str, object]]:
    """Workspace'in olay günlüğünü dosya sırasıyla oku; silinmiş sohbetlerin kayıtları ATLANIR.

    Kendini geliştirme hattı (`fusion eval taslak-uret`) bunu okur. Çoğu olay kaydı
    `session_id` taşımaz (`handle` olayın boş alanını yazar); bu yüzden silinmiş bir
    sohbetin kimliksiz olayları, sohbetin kimlikli kayıtlarındaki işarete bakılarak
    atlanır — aksi halde bir sonraki görünür sohbete yapışırdı.
    """
    path = (
        base_dir.expanduser().resolve() / "transcripts" / _workspace_digest(root) / "events.jsonl"
    )
    deleted = _deleted_conversations(path.parent)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    records: list[dict[str, object]] = []
    skipping = False
    for line in lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        session = event.get("session_id")
        if isinstance(session, str):
            skipping = _conversation_digest(session) in deleted
        if not skipping:
            records.append(event)
    return records


def _truncate_after_users(messages: list[Message], keep_users: int) -> None:
    """Listeyi `keep_users + 1`. kullanıcı mesajından itibaren kes (yerinde)."""
    seen = 0
    for index, message in enumerate(messages):
        if message.role != "user" or message.harness_note:
            continue
        if seen == keep_users:
            del messages[index:]
            return
        seen += 1


def _truncate_roles(roles: list[str], keep_users: int) -> None:
    """`_truncate_after_users`'ın rol listesi biçimi (liste sayımı için)."""
    seen = 0
    for index, role in enumerate(roles):
        if role != "user":
            continue
        if seen == keep_users:
            del roles[index:]
            return
        seen += 1


def _upsert_message(messages: list[Message], message: Message) -> None:
    """Aynı gönderimin final düzeltmesi geçmişte ikinci mesaj oluşturmaz."""
    if message.message_id:
        for index, existing in enumerate(messages):
            if existing.message_id == message.message_id:
                messages[index] = message
                return
    messages.append(message)


def _conversation_digest(conversation_id: object) -> str:
    return hashlib.sha256(str(conversation_id).encode()).hexdigest()


def _deleted_conversations(directory: Path) -> set[str]:
    deleted = directory / "deleted"
    try:
        return {entry.name for entry in deleted.iterdir()}
    except FileNotFoundError:
        return set()


def delete_conversation(base_dir: Path, root: Path, conversation_id: str) -> None:
    """Sohbeti listeden ve model bağlamından kaldır; disk dökümünü koru.

    Her kimlik ayrı işaret taşır: eşzamanlı süreçler ortak olay dosyasını
    yeniden yazmaz ve başka sohbetlerin mesajlarını kaybetmez. Denetim
    günlüğü korunur; silinen sohbet listeye ve model bağlamına alınmaz.
    """
    directory = base_dir.expanduser().resolve() / "transcripts" / _workspace_digest(root)
    deleted = directory / "deleted"
    deleted.mkdir(parents=True, exist_ok=True, mode=0o700)
    (deleted / _conversation_digest(conversation_id)).touch(mode=0o600, exist_ok=True)


def move_conversation(
    base_dir: Path, source_root: Path, target_root: Path, conversation_id: str
) -> None:
    """Bir sohbetin olaylarını hedef projeye taşı; özgün kaydı sonra gizle.

    Hedefe tam yazılmadan kaynak tombstone oluşturulmaz. Çökme durumunda iki
    listede görünmesi, konuşma kaybına tercih edilir. Çağıran açık turu kapatır.
    """
    validate_conversation_move(base_dir, source_root, target_root, conversation_id)
    base = base_dir.expanduser().resolve() / "transcripts"
    source = base / _workspace_digest(source_root)
    destination = base / _workspace_digest(target_root)
    try:
        lines = (source / "events.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError("Kaynak sohbet okunamadı.") from error
    selected: list[str] = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("session_id") == conversation_id:
            selected.append(line)
    if not selected:
        raise ValueError("Taşınacak sohbet olayı bulunamadı.")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = destination / "events.jsonl"
    with target.open("a", encoding="utf-8") as stream:
        stream.write("\n".join(selected) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    with contextlib.suppress(OSError):
        target.chmod(0o600)
    delete_conversation(base_dir, source_root, conversation_id)


def validate_conversation_move(
    base_dir: Path, source_root: Path, target_root: Path, conversation_id: str
) -> None:
    """Taşıma uygulanabilirliğini herhangi bir kalıcı yazmadan önce doğrular."""
    if source_root.resolve() == target_root.resolve():
        return
    if not target_root.is_dir():
        raise ValueError("Hedef proje klasörü bulunamadı.")
    base = base_dir.expanduser().resolve() / "transcripts"
    source = base / _workspace_digest(source_root)
    destination = base / _workspace_digest(target_root)
    if _conversation_digest(conversation_id) in _deleted_conversations(source):
        raise ValueError("Kaynak sohbet silinmiş.")
    if not any(
        ref.conversation_id == conversation_id for ref in list_conversations(base_dir, source_root)
    ):
        raise ValueError("Kaynak sohbet bulunamadı.")
    if _conversation_digest(conversation_id) in _deleted_conversations(destination):
        raise ValueError("Hedef projede bu sohbet kimliği daha önce silinmiş.")
    if any(
        ref.conversation_id == conversation_id for ref in list_conversations(base_dir, target_root)
    ):
        raise ValueError("Hedef projede aynı kimlikli sohbet zaten var.")


def _workspace_digest(root: Path) -> str:
    """Workspace kökünün depo dizin adı. Tek yerde durur ki okuma ve yazma ayrışmasın.

    Git çalışma ağacı (`.claude/worktrees/<ad>`) ana projenin anahtarını kullanır: `/worktree`
    ve `--worktree` konuşmayı bölmez, `--continue` ağacın içinden de projenin sohbetini bulur.
    """
    return hashlib.sha256(str(project_root_of(root.expanduser().resolve())).encode()).hexdigest()[
        :16
    ]


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
    #: Kullanıcının verdiği ad (`/rename`, `--name`); yoksa boş. Varsa `title` da budur.
    name: str = ""
    #: Son kullanıcı mesajındaki git dalı ve çalışma dizini (seçici süzgeçleri, #202).
    git_branch: str = ""
    cwd: str = ""
    #: Sohbetin transcript satırlarının toplam boyutu (bayt).
    size_bytes: int = 0
    #: Kopyalandığı sohbet (`/branch`, `--fork-session`); kök oturumda boş.
    forked_from: str = ""


def find_conversation(base_dir: Path, root: Path, query: str) -> ConversationRef | None:
    """`--resume <kimlik|ad|kimlik-öneki>` sorgusunu bu projedeki tek bir sohbete çöz.

    Sıra: tam kimlik → ad (büyük/küçük duyarsız) → tek eşleşen kimlik öneki
    (en az `_ID_PREFIX_MIN` karakter). Birden çok sohbet önekle eşleşirse hiçbiri
    seçilmez: yanlış sohbeti açmak, bulamamaktan kötüdür.
    """
    wanted = query.strip()
    if not wanted:
        return None
    refs = list_conversations(base_dir, root)
    for ref in refs:
        if ref.conversation_id == wanted:
            return ref
    folded = wanted.casefold()
    named = [ref for ref in refs if ref.name and ref.name.casefold() == folded]
    if len(named) == 1:
        return named[0]
    if len(wanted) >= _ID_PREFIX_MIN:
        prefixed = [ref for ref in refs if ref.conversation_id.startswith(wanted)]
        if len(prefixed) == 1:
            return prefixed[0]
    return None


def conversation_prefix(messages: Sequence[Message]) -> list[Message]:
    """Transcript'e yazılabilir kullanıcı/cevap mesajları: harness notları ve boş metin dışarıda.

    Ölçüldü (31 Ekim): `/branch` motor geçmişini olduğu gibi veriyordu; FUSION_NOT: notunu
    `record_user` atlıyor, doğrulama uyuşmazlık görüp `ValueError` fırlatıyordu; öneksiz
    harness notu (compaction özeti) ise kopyaya sıradan kullanıcı mesajı olarak giriyordu.
    """
    return [
        message
        for message in messages
        if message.role in {"user", "assistant"}
        and message.content.strip()
        and not message.harness_note
        and not (message.role == "user" and is_harness_note(message.content))
    ]


def copy_conversation(
    base_dir: Path, root: Path, messages: Sequence[Message], *, target_id: str, name: str = ""
) -> int:
    """Kullanıcı/cevap mesajlarını YENİ bir sohbet kimliğine yaz; yazılan sayıyı döndür.

    `/branch`, `--fork-session` ve masaüstü `sohbet.dallan` aynı çekirdeği kullanır.
    Yazılan geçmiş geri okunarak doğrulanır; eşleşmezse yarım sohbet silinir ve
    `ValueError` fırlatılır — kullanıcı "dallandı" sanıp boş bir sohbette kalmasın.
    """
    prefix = conversation_prefix(messages)
    requirement = next((message for message in messages if _is_requirement_note(message)), None)
    if requirement is not None:
        requirement = dataclasses.replace(
            requirement, content=redact(requirement.content[:_REQUIREMENT_NOTE_CHARS])
        )
    if not any(message.role == "user" for message in prefix) and requirement is None:
        raise ValueError("Kopyalanacak kullanıcı mesajı yok.")
    store = TranscriptStore(base_dir, root, conversation_id=target_id)
    if name.strip():
        store.record_name(name.strip())
    if requirement is not None:
        store.record_requirement(requirement.content)
    for message in prefix:
        record = store.record_user if message.role == "user" else store.record_assistant
        record(message.content, message_id=str(uuid.uuid4()))
    restored = load_transcript_messages(base_dir, root, conversation_id=target_id)
    expected = [
        message.content
        for message in _bounded_history(
            [
                *([requirement] if requirement is not None else []),
                *[
                    dataclasses.replace(message, content=redact(message.content))
                    for message in prefix
                ],
            ]
        )
    ]
    if [message.content for message in restored] != expected:
        delete_conversation(base_dir, root, target_id)
        raise ValueError("Yeni sohbet geçmişi doğrulanamadı.")
    return len(restored)


def transcript_events_path(base_dir: Path, root: Path) -> Path:
    """Bu çalışma alanının transcript dosyası (durum satırı `transcript_path`, #191)."""
    return (
        base_dir.expanduser().resolve() / "transcripts" / _workspace_digest(root) / "events.jsonl"
    )


def list_conversations(
    base_dir: Path, root: Path, *, events_path: Path | None = None
) -> tuple[ConversationRef, ...]:
    """Bir workspace'te kayıtlı sohbetleri en yeniden eskiye sırala.

    Ölçüldü (kullanıcının diski, 8 Eylül): 110 sohbet transcript dosyalarında
    duruyordu ama arayüz yalnız AÇIK sekmeleri gösteriyordu; dünkü konuşmaya
    ulaşmanın hiçbir yolu yoktu. Ulaşılamayan geçmiş, yok sayılmış geçmiştir.

    Kullanıcı mesajı olmayan kayıt sohbet sayılmaz: yalnız araç olayı taşıyan
    bir kimlik kullanıcı için hiçbir şey ifade etmez.
    """
    path = events_path or transcript_events_path(base_dir, root)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()
    deleted = _deleted_conversations(path.parent)
    titles: dict[str, str] = {}
    names: dict[str, str] = {}
    stamps: dict[str, float] = {}
    #: Sohbet başına mesaj rolleri; geri sarma olayı listeyi keser, sayım yüklenenle eşleşir.
    roles: dict[str, list[str]] = {}
    places: dict[str, tuple[str, str]] = {}
    forks: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for line in lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        conversation = event.get("session_id")
        if isinstance(conversation, str):
            sizes[conversation] = sizes.get(conversation, 0) + len(line.encode("utf-8")) + 1
            if event.get("event") == "UserMessage" and isinstance(event.get("cwd"), str):
                places[conversation] = (str(event.get("git_branch") or ""), event["cwd"])
        if _conversation_digest(conversation) in deleted:
            continue
        if event.get("event") == _FORK_EVENT and isinstance(conversation, str):
            source = event.get("forked_from")
            if isinstance(source, str):
                forks[conversation] = source
            continue
        if event.get("event") == _NAME_EVENT:
            # Son verilen ad geçerlidir; ad bir mesaj değildir, sayılmaz ve zaman damgası vermez.
            name = event.get("name")
            if isinstance(conversation, str) and isinstance(name, str) and name.strip():
                names[conversation] = redact(name.strip())[:TITLE_BUDGET]
            continue
        if event.get("event") == _REWIND_EVENT and isinstance(conversation, str):
            keep = event.get("keep_users")
            if isinstance(keep, int) and not isinstance(keep, bool) and keep >= 0:
                _truncate_roles(roles.setdefault(conversation, []), keep)
            continue
        if event.get("event") == _REQUIREMENT_EVENT and isinstance(conversation, str):
            # Requirement metadata is preserved without becoming a user turn.
            if isinstance(event.get("text"), str) and event["text"].strip():
                titles.setdefault(conversation, "Devralınan görev")
                roles.setdefault(conversation, []).append("context")
            continue
        if event.get("event") not in {"UserMessage", "TurnAnswered"}:
            continue
        text = event.get("text")
        if not isinstance(conversation, str) or not isinstance(text, str) or not text.strip():
            continue
        if event.get("event") == "UserMessage" and is_harness_note(text):
            continue
        roles.setdefault(conversation, []).append(
            "user" if event.get("event") == "UserMessage" else "assistant"
        )
        stamp = event.get("timestamp")
        if isinstance(stamp, (int, float)):
            stamps[conversation] = max(stamps.get(conversation, 0.0), float(stamp))
        if event.get("event") == "UserMessage" and conversation not in titles:
            titles[conversation] = redact(text.strip().splitlines()[0])[:TITLE_BUDGET]
    refs = tuple(
        ConversationRef(
            conversation_id=conversation,
            title=names.get(conversation) or title,
            updated_at=stamps.get(conversation, 0.0),
            message_count=len(roles.get(conversation, ())),
            name=names.get(conversation, ""),
            git_branch=places.get(conversation, ("", ""))[0],
            cwd=places.get(conversation, ("", ""))[1],
            size_bytes=sizes.get(conversation, 0),
            forked_from=forks.get(conversation, ""),
        )
        for conversation, title in titles.items()
    )
    return tuple(sorted(refs, key=lambda ref: ref.updated_at, reverse=True))


class TranscriptStore:
    """Bir workspace için son transcript ve denetlenebilir olay günlüğü."""

    def __init__(self, base_dir: Path, root: Path, *, conversation_id: str | None = None) -> None:
        digest = _workspace_digest(root)
        #: Bağlanılan proje kökü; `/worktree` kökü değiştirince depo yeniden bağlanır.
        self.root = root.expanduser().resolve()
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

    def record_user(self, text: str, *, message_id: str | None = None) -> None:
        if is_harness_note(text):
            return
        branch = current_git_branch(self.root)
        self._append(
            {
                "event": "UserMessage",
                "text": text,
                **({"message_id": message_id} if message_id else {}),
                # Claude Code oturum seçicisi dal/worktree süzgeçleri için (#202).
                "cwd": str(self.root),
                **({"git_branch": branch} if branch else {}),
            }
        )

    def record_assistant(self, text: str, *, message_id: str | None = None) -> None:
        self._append(
            {
                "event": "TurnAnswered",
                "channel": "text",
                "text": strip_harness_leaks(text),
                **({"message_id": message_id} if message_id else {}),
            }
        )

    def record_name(self, name: str) -> None:
        """Sohbete ad ver (`/rename`, `--name`). Son ad geçerlidir."""
        self._append({"event": _NAME_EVENT, "name": name})

    def record_visible_tool(self, payload: dict[str, object], *, identifier: str) -> None:
        """Append a pre-sanitized public UI record; the model loader ignores this type."""
        self._append(
            {
                "event": "VisibleToolExecuted",
                "visible_version": 1,
                "visible_id": identifier,
                "payload": payload,
            }
        )

    def record_visible_limit(self) -> None:
        """Expose the bounded per-turn UI history limit without inventing a tool."""
        self._append({"event": "VisibleHistoryLimited", "visible_version": 1})

    def record_visible_clear(self) -> None:
        """A UI reset also fences old persisted work rows on reopening."""
        self._append({"event": "VisibleHistoryCleared", "visible_version": 1})

    def record_requirement(self, text: str) -> None:
        """Persist only the explicitly typed original-requirement note for a branch."""
        self._append({"event": _REQUIREMENT_EVENT, "text": text[:_REQUIREMENT_NOTE_CHARS]})

    def record_fork(self, source_id: str) -> None:
        """Bu sohbet `source_id`'nin kopyasıdır (oturum seçicisi gruplaması, #202)."""
        self._append({"event": _FORK_EVENT, "forked_from": source_id})

    def record_rewind(self, keep_users: int) -> None:
        """Konuşmayı ilk `keep_users` kullanıcı mesajına (ve cevaplarına) geri sar (`/rewind`).

        Dosyadan hiçbir satır silinmez; yükleyici bu olaydan sonra fazlasını atlar.
        """
        self._append({"event": _REWIND_EVENT, "keep_users": max(0, keep_users)})

    def handle(self, event: Event) -> None:
        # JSONL sınırı: alan değerleri olay tipine göre değişir ve `_jsonable`
        # bunları serileştirilebilir bir değere indirger. `Any` bu sınırda kalır.
        payload: dict[str, Any] = {"event": type(event).__name__}
        for field in dataclasses.fields(event):
            payload[field.name] = _jsonable(getattr(event, field.name))
        if isinstance(payload.get("text"), str):
            payload["text"] = strip_harness_leaks(payload["text"])
        self._append(payload)

    def _append(self, payload: dict[str, Any]) -> None:
        if _conversation_digest(self.session_id) in _deleted_conversations(self.base_dir):
            return
        payload = {
            "session_id": self.session_id,
            "timestamp": time.time(),
            **payload,
        }
        # Maskeleme DEĞERLER üzerinde yapılır, serileştirilmiş satırda DEĞİL: Ölçüldü (30 Ekim)
        # `api_key="…"` gibi bir desen JSON'daki tırnağı/kaçışı da yutuyor, satır geçersiz
        # JSON oluyor ve okuyucu onu sessizce atlayıp mesajı kaybediyordu (L2-17).
        line = json.dumps(_redact_values(payload), ensure_ascii=False, default=str) + "\n"
        try:
            # Kalıcı sohbet günlüğü eklemelidir; döndürme başka sohbetleri kaybettirir.
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
            self.events_path.chmod(0o600)
        except OSError:
            return


def current_git_branch(root: Path) -> str:
    """`root`'un git dalı (alt süreçsiz, `.git/HEAD` okunur); dal yoksa ya da ayrık HEAD'de boş."""
    for folder in (root, *root.parents):
        marker = folder / ".git"
        try:
            if marker.is_file():
                text = marker.read_text(encoding="utf-8").strip()
                marker = Path(text.removeprefix("gitdir:").strip())
                if not marker.is_absolute():
                    marker = folder / marker
            elif not marker.is_dir():
                continue
            head = (marker / "HEAD").read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        return head.removeprefix("ref: refs/heads/") if head.startswith("ref: refs/heads/") else ""
    return ""


def _redact_values(value: object) -> object:
    """Yapıdaki tüm metin DEĞERLERİNİ maskele; yapı (anahtarlar, tırnaklar) bozulmaz."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: _redact_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_values(item) for item in value]
    return value


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
