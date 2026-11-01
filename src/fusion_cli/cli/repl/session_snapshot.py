"""Sürdürülen oturumun tam durumu: geçmiş, model, izin kipi ve checkpoint'ler (#187, #189).

Claude Code sürdürmede mesajları, araç çağrılarını ve sonuçlarını, compaction durumunu,
modeli ve (terminalde) izin kipini geri yükler; checkpoint'ler konuşmayla birlikte saklanır
ve oturum sürdürüldükten sonra da `/rewind` çalışır. Anlık görüntüler `cleanupPeriodDays`
(varsayılan 30) gün tutulur.

Transcript (`transcript_store`) yalnız kullanıcı/cevap METNİNİ tutar. Bu modül her turun
sonunda sohbetin motor geçmişini (araç çağrıları, sonuçları, compaction özeti dahil), agent
modelini, izin kipini ve tur checkpoint'lerini (dosyaların ilk hâlleri) tek bir dosyaya
yazar: `memory_dir/oturum-durum/<sohbet>.json` (dizin 0700, dosya 0600, atomik).

Güvenlik: mesaj metinleri `turn_journal_codec` ile maskelenir; dosya içerikleri geri alma
için birebir saklanmak zorundadır (Claude'un dosya geçmişi de öyledir). `bypass` kipi
sürdürmede geri yüklenmez: Claude'da da bu kip yalnız açılış bayrağıyla girilir.
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...core.changeset import ChangeSet, Snapshot
from ...core.errors import ConfigError
from ...core.turn_checkpoints import TurnCheckpoint
from ...core.types import Message
from ...engines.agent.approval import ApprovalMode
from ...memory.turn_journal_codec import message_from, message_to
from .transcript_store import last_turn_timestamp

if TYPE_CHECKING:
    from .state import ReplState

_LOG = logging.getLogger(__name__)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
STORE_DIR = "oturum-durum"
FORMAT_VERSION = 1
#: Claude Code `cleanupPeriodDays` varsayılanı.
DEFAULT_CLEANUP_DAYS = 30
_DAY_S = 86_400
_CLAUDE_SETTINGS = Path(".claude") / "settings.json"


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Diskten okunan oturum durumu."""

    conversation_id: str
    saved_at: float
    history: tuple[Message, ...]
    model: str
    approval: str
    checkpoints: tuple[TurnCheckpoint, ...]


def store_path(memory_dir: Path, conversation_id: str) -> Path:
    stem = _UNSAFE.sub("_", conversation_id).strip("._") or "oturum"
    return memory_dir.expanduser() / STORE_DIR / f"{stem}.json"


def cleanup_period_days(home: Path | None = None) -> int:
    """Claude kullanıcı ayarındaki `cleanupPeriodDays`; yoksa ya da geçersizse 30."""
    path = (home or Path.home()) / _CLAUDE_SETTINGS
    try:
        raw = json.loads(path.read_text(encoding="utf-8")).get("cleanupPeriodDays")
    except (OSError, ValueError, AttributeError):
        return DEFAULT_CLEANUP_DAYS
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        return DEFAULT_CLEANUP_DAYS
    return int(raw)


# --------------------------------------------------------------------------- #
# Kodlama
# --------------------------------------------------------------------------- #


def _changes_to(changes: ChangeSet) -> dict[str, Any]:
    snapshots, applied, acquired = changes.export_state()
    return {
        "ilk": [
            {
                "yol": str(snapshot.path),
                "icerik": (
                    base64.b64encode(snapshot.content).decode("ascii")
                    if snapshot.content is not None
                    else None
                ),
            }
            for snapshot in snapshots
        ],
        "kimlik": {str(path): identity for path, identity in applied.items()},
        "edinilen": sorted(str(path) for path in acquired),
    }


def _changes_from(raw: object) -> ChangeSet:
    if not isinstance(raw, dict):
        return ChangeSet()
    snapshots: list[Snapshot] = []
    for item in _list(raw.get("ilk")):
        if not isinstance(item, dict) or not isinstance(item.get("yol"), str):
            continue
        content = item.get("icerik")
        try:
            data = base64.b64decode(content) if isinstance(content, str) else None
        except ValueError:
            continue
        snapshots.append(Snapshot(Path(item["yol"]), data))
    identities = _dict(raw.get("kimlik"))
    applied = {
        Path(path): value
        for path, value in identities.items()
        if isinstance(path, str) and (value is None or isinstance(value, str))
    }
    acquired_raw = _list(raw.get("edinilen"))
    acquired = frozenset(Path(path) for path in acquired_raw if isinstance(path, str))
    return ChangeSet.from_state(tuple(snapshots), applied, acquired)


def _list(raw: object) -> list[object]:
    return list(raw) if isinstance(raw, list) else []


def _dict(raw: object) -> dict[object, object]:
    return dict(raw) if isinstance(raw, dict) else {}


def _checkpoint_to(entry: TurnCheckpoint) -> dict[str, Any]:
    return {
        "no": entry.index,
        "gorev": entry.task,
        "zaman": entry.created_at,
        "gecmis": [message_to(message) for message in entry.history_before],
        "degisiklik": _changes_to(entry.changes),
    }


def _checkpoint_from(raw: object) -> TurnCheckpoint | None:
    if not isinstance(raw, dict):
        return None
    index, task, created = raw.get("no"), raw.get("gorev"), raw.get("zaman")
    if isinstance(index, bool) or not isinstance(index, int) or not isinstance(task, str):
        return None
    history = _messages_from(raw.get("gecmis"))
    return TurnCheckpoint(
        index=index,
        task=task,
        created_at=float(created) if isinstance(created, int | float) else 0.0,
        history_before=history,
        changes=_changes_from(raw.get("degisiklik")),
    )


def _messages_from(raw: object) -> tuple[Message, ...]:
    if not isinstance(raw, list):
        return ()
    decoded = (message_from(item) for item in raw)
    return tuple(message for message in decoded if message is not None)


# --------------------------------------------------------------------------- #
# Yazma / okuma
# --------------------------------------------------------------------------- #


def save(state: ReplState, *, now: float | None = None) -> None:
    """Etkin sohbetin durumunu yaz; hata turu düşürmez (yalnız günlüğe düşer)."""
    conversation_id = getattr(state, "conversation_id", "")
    memory_dir = getattr(state.config, "memory_dir", None)
    if not conversation_id or memory_dir is None:
        return
    stamp = time.time() if now is None else now
    payload = {
        "surum": FORMAT_VERSION,
        "sohbet": conversation_id,
        "zaman": stamp,
        "gecmis": [message_to(message) for message in state.history],
        "model": state.config.agent.model,
        "izin": state.approval.value,
        "checkpointler": [_checkpoint_to(entry) for entry in state.checkpoints.entries()],
    }
    path = store_path(Path(memory_dir), conversation_id)
    try:
        _write_private(path, json.dumps(payload, ensure_ascii=False))
    except OSError:
        _LOG.info("oturum durumu yazılamadı", extra={"sohbet": conversation_id})
        return
    prune(Path(memory_dir), now=stamp)


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.parent.chmod(0o700)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        temporary.replace(path)
    except OSError:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise


def prune(memory_dir: Path, *, now: float | None = None, home: Path | None = None) -> int:
    """`cleanupPeriodDays` günden eski anlık görüntüleri sil; silinen sayısını döndür."""
    directory = memory_dir.expanduser() / STORE_DIR
    cutoff = (time.time() if now is None else now) - cleanup_period_days(home) * _DAY_S
    removed = 0
    try:
        candidates = tuple(directory.glob("*.json"))
    except OSError:
        return removed
    for path in candidates:
        with contextlib.suppress(OSError):
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
    return removed


def load(memory_dir: Path, conversation_id: str) -> SessionSnapshot | None:
    """Sohbetin kayıtlı durumu; yoksa, bozuksa ya da başka sohbete aitse `None`."""
    try:
        raw = json.loads(store_path(memory_dir, conversation_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or raw.get("sohbet") != conversation_id:
        return None
    if raw.get("surum") != FORMAT_VERSION:
        return None
    stamp = raw.get("zaman")
    entries = _list(raw.get("checkpointler"))
    decoded = (_checkpoint_from(item) for item in entries)
    return SessionSnapshot(
        conversation_id=conversation_id,
        saved_at=float(stamp) if isinstance(stamp, int | float) else 0.0,
        history=_messages_from(raw.get("gecmis")),
        model=raw["model"] if isinstance(raw.get("model"), str) else "",
        approval=raw["izin"] if isinstance(raw.get("izin"), str) else "",
        checkpoints=tuple(entry for entry in decoded if entry is not None),
    )


def restore(state: ReplState) -> bool:
    """Sürdürülen sohbetin tam durumunu yükle; anlık görüntü güncel değilse `False`.

    Transcript anlık görüntüden yeniyse (sohbet başka bir yüzeyde sürdü) dokunulmaz:
    eski bir tam geçmiş, yeni metin geçmişini ezmesin.
    """
    memory_dir = Path(state.config.memory_dir)
    snapshot = load(memory_dir, state.conversation_id)
    if snapshot is None:
        return False
    if last_turn_timestamp(memory_dir, state.root, state.conversation_id) > snapshot.saved_at:
        return False
    state.history = list(snapshot.history)
    state.checkpoints.restore_entries(snapshot.checkpoints)
    _restore_model(state, snapshot.model)
    _restore_approval(state, snapshot.approval)
    return True


def _restore_model(state: ReplState, model: str) -> None:
    if not model or model == state.config.agent.model:
        return
    from ...config import model_select

    try:
        state.config = model_select.set_agent_model(state.config, model)
    except ConfigError:
        _LOG.info("sürdürülen oturumun modeli artık geçersiz", extra={"model": model})


def _restore_approval(state: ReplState, value: str) -> None:
    try:
        mode = ApprovalMode(value)
    except ValueError:
        return
    if mode is ApprovalMode.BYPASS:
        # Claude Code: bypassPermissions yalnız açılış bayrağıyla girilir; sürdürme açmaz.
        return
    state.approval = mode
