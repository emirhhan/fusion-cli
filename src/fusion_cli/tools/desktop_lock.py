"""Tek oturum kilidi: aynı anda yalnız bir Fusion süreci masaüstünü yönetir (P-033).

İki oturum aynı anda fare/klavye gönderirse olaylar birbirine karışır (Claude CLI "one session
at a time" kilidiyle aynı gerekçe). Kilit, yerel yardımcı önbelleğiyle aynı özel dizinde
(`$TMPDIR/fusion-desktop-<uid>/oturum.lock`) tutulur; sahibi süreç kimliğidir. Sahip süreç
ölmüşse ya da `LOCK_STALE_S` boyunca masaüstü eylemi yapmamışsa kilit devralınır; açık bırakma
hakkı yoktur, bu yüzden ayrı bir "bırak" adımı gerekmez (süreç çıkınca kendiliğinden düşer).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

LOCK_DIRECTORY_TEMPLATE = "fusion-desktop-{uid}"
LOCK_FILE_NAME = "oturum.lock"
#: Bu kadar süre eylem yapmayan sahip "bitmiş" sayılır (uzun tur bile bu arayla dokunur).
LOCK_STALE_S = 300.0


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


def _read(path: Path) -> tuple[int, float] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pid, touched = payload.get("pid"), payload.get("touched")
    if type(pid) is not int or not isinstance(touched, (int, float)):
        return None
    return pid, float(touched)


def claim(
    *, pid: int | None = None, now: float | None = None, path: Path | None = None
) -> str | None:
    """Kilidi al ya da tazele; başka canlı süreç tutuyorsa Türkçe hata metni döner."""
    owner = os.getpid() if pid is None else pid
    moment = time.time() if now is None else now
    target = lock_path() if path is None else path
    current = _read(target)
    if current is not None:
        holder, touched = current
        if holder != owner and _is_alive(holder) and moment - touched < LOCK_STALE_S:
            return (
                f"Başka bir Fusion oturumu (süreç {holder}) şu an bilgisayarı kullanıyor. "
                "Aynı anda tek oturum masaüstünü yönetebilir; o tur bitince yeniden dene."
            )
    try:
        target.write_text(json.dumps({"pid": owner, "touched": moment}), encoding="utf-8")
    except OSError as exc:
        return f"Masaüstü kilidi yazılamadı: {exc}"
    return None


def release(*, pid: int | None = None, path: Path | None = None) -> None:
    """Kilit bizimse kaldır (tur sonu temizliği; zorunlu değil)."""
    owner = os.getpid() if pid is None else pid
    target = lock_path() if path is None else path
    current = _read(target)
    if current is not None and current[0] == owner:
        try:
            target.unlink()
        except OSError:
            return
