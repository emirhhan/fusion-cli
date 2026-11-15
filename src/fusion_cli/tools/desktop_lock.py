"""Tek oturum kilidi: aynı anda yalnız bir Fusion oturumu masaüstünü yönetir (P-033, #429).

Claude Code: "A session takes a lock at its first computer use action and releases it when the
session exits, not when the task finishes. A second session's computer use fails with an error
naming the session that holds the lock." Çöken oturumun kilidi süreç ölünce kalkar.

Kilit, yerel yardımcı önbelleğiyle aynı özel dizinde (`$TMPDIR/fusion-desktop-<uid>/oturum.lock`)
tutulur; sahibi süreç kimliği + oturum belirteci ikilisidir (`desktop_turn.lock_token`: CLI'de
süreç = oturum, masaüstü uygulamasında sohbet). Tur sonunda BIRAKILMAZ; süreç çıkınca (sahip
ölü) ya da masaüstünde sohbetten çıkılınca (`release`) kalkar. Süreye bağlı devralma yoktur.
Dosya `flock` altında okunup yazılır (oku-sonra-yaz atomik).
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

LOCK_DIRECTORY_TEMPLATE = "fusion-desktop-{uid}"
LOCK_FILE_NAME = "oturum.lock"
_READ_CHUNK = 4096


@dataclass(frozen=True, slots=True)
class LockOwner:
    """Kilidi tutan oturum: süreç + oturum belirteci + son dokunma zamanı + görünen ad."""

    pid: int
    token: str
    touched: float
    label: str = ""


def lock_path() -> Path:
    directory = Path(tempfile.gettempdir()) / LOCK_DIRECTORY_TEMPLATE.format(uid=os.getuid())
    directory.mkdir(mode=0o700, exist_ok=True)
    return directory / LOCK_FILE_NAME


def _is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _parse(raw: bytes) -> LockOwner | None:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    pid, touched, token = payload.get("pid"), payload.get("touched"), payload.get("token", "")
    if type(pid) is not int or not isinstance(touched, (int, float)) or not isinstance(token, str):
        return None
    label = payload.get("label")
    return LockOwner(pid, token, float(touched), label if isinstance(label, str) else "")


def _read(path: Path) -> LockOwner | None:
    """Kilit dosyasını kilitlemeden oku (teşhis ve test için)."""
    try:
        return _parse(path.read_bytes())
    except OSError:
        return None


@contextmanager
def _guarded(path: Path) -> Iterator[int]:
    """Dosyayı `flock(LOCK_EX)` altında aç: oku-karar ver-yaz tek parça olur."""
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield descriptor
    finally:
        os.close(descriptor)


def _read_fd(descriptor: int) -> LockOwner | None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    return _parse(os.read(descriptor, _READ_CHUNK))


def _write_fd(descriptor: int, owner: LockOwner) -> None:
    os.ftruncate(descriptor, 0)
    os.lseek(descriptor, 0, os.SEEK_SET)
    os.write(descriptor, json.dumps(asdict(owner)).encode("utf-8"))


def _is_held_by_other(current: LockOwner | None, owner: LockOwner) -> bool:
    if current is None or (current.pid, current.token) == (owner.pid, owner.token):
        return False
    return _is_alive(current.pid)


#: İkinci oturumun hatası (Claude: "Computer use is in use by another Claude session").
BUSY_MESSAGE = (
    "Computer use başka bir Fusion oturumunda kullanılıyor: {label}. Kilit o oturum çıkana "
    "kadar tutulur; önce o oturumdan çık."
)


def claim(
    *,
    pid: int | None = None,
    token: str = "",
    now: float | None = None,
    path: Path | None = None,
    label: str = "",
) -> str | None:
    """Kilidi al ya da tazele; başka canlı oturum tutuyorsa Türkçe hata metni döner."""
    owner_pid = os.getpid() if pid is None else pid
    owner = LockOwner(
        owner_pid, token, time.time() if now is None else now, label or f"süreç {owner_pid}"
    )
    target = lock_path() if path is None else path
    try:
        with _guarded(target) as descriptor:
            current = _read_fd(descriptor)
            if _is_held_by_other(current, owner):
                assert current is not None
                return BUSY_MESSAGE.format(label=current.label or f"süreç {current.pid}")
            _write_fd(descriptor, owner)
    except OSError as exc:
        return f"Masaüstü kilidi yazılamadı: {exc}"
    return None


def release(*, pid: int | None = None, token: str = "", path: Path | None = None) -> None:
    """Kilit bu oturumunsa kaldır (oturumdan çıkış). Kilit dosyası yoksa dizin bile açılmaz."""
    owner_pid = os.getpid() if pid is None else pid
    target = _existing_lock_path() if path is None else path
    if target is None or not target.exists():
        return
    try:
        with _guarded(target) as descriptor:
            current = _read_fd(descriptor)
            if current is not None and (current.pid, current.token) == (owner_pid, token):
                target.unlink()
    except OSError:
        return


def _existing_lock_path() -> Path | None:
    directory = Path(tempfile.gettempdir()) / LOCK_DIRECTORY_TEMPLATE.format(uid=os.getuid())
    return directory / LOCK_FILE_NAME if directory.is_dir() else None
