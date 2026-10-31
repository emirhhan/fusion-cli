"""Tek oturum kilidi: aynı anda yalnız bir Fusion turu masaüstünü yönetir (P-033).

İki tur aynı anda fare/klavye gönderirse olaylar birbirine karışır (Claude CLI "one session
at a time" kilidiyle aynı gerekçe). Kilit, yerel yardımcı önbelleğiyle aynı özel dizinde
(`$TMPDIR/fusion-desktop-<uid>/oturum.lock`) tutulur; sahibi süreç kimliği + tur belirteci
(`ToolContext.job_scope`) ikilisidir: aynı appserver sürecindeki iki sohbet de birbirini
bekler. Tur bitince `release` çağrılır (`cli/session.py`, REPL); sahip süreç ölmüşse ya da
`LOCK_STALE_S` boyunca eylem yapmamışsa kilit devralınır.

Ölçüldü (31 Ekim): oku-sonra-yaz atomik değildi (iki süreç boş kilidi aynı anda görüp ikisi de
alıyordu), `release` hiçbir yerden çağrılmıyordu (tur bitse de 300 sn 'o tur bitince yeniden
dene' hatası) ve aynı süreçteki sohbetler aynı pid olduğu için hiç korunmuyordu. Artık dosya
`flock` altında okunup yazılır.
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
#: Bu kadar süre eylem yapmayan sahip "bitmiş" sayılır (tur sonu bırakması kaçmış olsa bile).
LOCK_STALE_S = 300.0
_READ_CHUNK = 4096


@dataclass(frozen=True, slots=True)
class LockOwner:
    """Kilidi tutan tur: süreç + tur belirteci + son dokunma zamanı."""

    pid: int
    token: str
    touched: float


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
    return LockOwner(pid, token, float(touched))


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
    return _is_alive(current.pid) and owner.touched - current.touched < LOCK_STALE_S


def claim(
    *,
    pid: int | None = None,
    token: str = "",
    now: float | None = None,
    path: Path | None = None,
) -> str | None:
    """Kilidi al ya da tazele; başka canlı tur tutuyorsa Türkçe hata metni döner."""
    owner = LockOwner(
        os.getpid() if pid is None else pid, token, time.time() if now is None else now
    )
    target = lock_path() if path is None else path
    try:
        with _guarded(target) as descriptor:
            current = _read_fd(descriptor)
            if _is_held_by_other(current, owner):
                assert current is not None
                return (
                    f"Başka bir Fusion oturumu (süreç {current.pid}) şu an bilgisayarı "
                    "kullanıyor. Aynı anda tek oturum masaüstünü yönetebilir; o tur bitince "
                    "yeniden dene."
                )
            _write_fd(descriptor, owner)
    except OSError as exc:
        return f"Masaüstü kilidi yazılamadı: {exc}"
    return None


def release(*, pid: int | None = None, token: str = "", path: Path | None = None) -> None:
    """Kilit bu turunsa kaldır (tur sonu temizliği). Kilit dosyası yoksa dizin bile açılmaz."""
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
