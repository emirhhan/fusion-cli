"""Arka plan kabuk işlerinin ömrü: çıkışta temizlik, 5 GB tavanı, gözetimsiz süre sınırı (#335).

Claude Code (interactive-mode "How backgrounding works"; tools-reference "Time limit for
background commands"):
- Arka plan işleri Claude Code kapanırken temizlenir; kabuktan kopmuş süreçler de durur.
- Çıktısı 5 GB'ı geçen iş durdurulur ve nedeni çıktıya yazılır.
- Yalnız gözetimsiz oturumda (`-p`, SDK, CI) süre sınırı vardır: arka planda başlayan komut
  30 dk ya da verilen `timeout` (en çok 2 sa); ön plandan taşınan komut taşındığı andan 30 dk.
  Metin istemli `-p` koşusunda iki varsayılan 10 dk'dır. `BASH_DEFAULT_TIMEOUT_MS` 30 dk'nın
  (metin istemli `-p`'de 10 dk'nın) üstündeyse varsayılanın yerine geçer; `BASH_MAX_TIMEOUT_MS`
  2 sa'nın üstündeyse tavanı yükseltir. Daha düşük değer sınırı kısaltmaz.
Etkileşimli oturumda (terminal, masaüstü) süre sınırı yoktur.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.errors import CleanupFailedError
from ..core.process_control import ensure_process_group_exit, terminate_process_tree

_LOG = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 5 * 1024**3
UNATTENDED_DEFAULT_S = 30 * 60
UNATTENDED_TEXT_PROMPT_DEFAULT_S = 10 * 60
UNATTENDED_MAX_S = 2 * 60 * 60
_POLL_S = 1.0
_TERMINATED_EXIT = 128 + signal.SIGTERM


@dataclass(frozen=True, slots=True)
class _Unattended:
    text_prompt: bool


_LOCK = threading.Lock()
_OWNED: dict[str, tuple[int, Path]] = {}
_unattended: _Unattended | None = None
_atexit_registered = False


def set_unattended(*, text_prompt: bool) -> None:
    """Bu süreç gözetimsiz koşuyor (`fusion agent`): arka plan işlerine süre sınırı uygula."""
    global _unattended
    _unattended = _Unattended(text_prompt)


def clear_unattended() -> None:
    global _unattended
    _unattended = None


def _ms(env: Mapping[str, str], name: str) -> int:
    try:
        return int(env.get(name, "").strip())
    except ValueError:
        return 0


def time_limit_s(
    requested_ms: object = None, *, moved: bool = False, env: Mapping[str, str] | None = None
) -> float | None:
    """İşin süre sınırı (sn); etkileşimli oturumda `None` (sınır yok)."""
    if _unattended is None:
        return None
    source = os.environ if env is None else env
    default = (
        UNATTENDED_TEXT_PROMPT_DEFAULT_S if _unattended.text_prompt else UNATTENDED_DEFAULT_S
    )
    configured = _ms(source, "BASH_DEFAULT_TIMEOUT_MS") / 1000
    if configured > default:
        default = configured
    ceiling = max(UNATTENDED_MAX_S, _ms(source, "BASH_MAX_TIMEOUT_MS") / 1000, configured)
    asked = requested_ms
    if moved or isinstance(asked, bool) or not isinstance(asked, (int, float)) or asked <= 0:
        return float(default)
    return float(min(asked / 1000, ceiling))


def own(job_id: str, pid: int, folder: Path, *, log: Path, command: str, limit_s: float | None) -> None:
    """İşi bu sürecin sahipliğine al ve gözetimini başlat (5 GB, süre sınırı, çıkış)."""
    global _atexit_registered
    with _LOCK:
        _OWNED[job_id] = (pid, folder)
        if not _atexit_registered:
            atexit.register(cleanup_owned_jobs)
            _atexit_registered = True
    threading.Thread(
        target=_guard,
        args=(job_id, pid, folder, log, command, limit_s, time.monotonic),
        name=f"fusion-job-guard-{job_id}",
        daemon=True,
    ).start()


def _guard(
    job_id: str,
    pid: int,
    folder: Path,
    log: Path,
    command: str,
    limit_s: float | None,
    clock: Callable[[], float],
) -> None:
    started = clock()
    while not (folder / f"{job_id}.exit").exists() and _group_alive(pid):
        reason = _over_limit(log, command, limit_s, clock() - started)
        if reason:
            _stop(job_id, pid, folder, log, reason)
            return
        time.sleep(_POLL_S)
    with _LOCK:
        _OWNED.pop(job_id, None)


def _over_limit(log: Path, command: str, limit_s: float | None, elapsed: float) -> str:
    try:
        size = log.stat().st_size
    except OSError:
        size = 0
    if size > MAX_OUTPUT_BYTES:
        return "Arka plan işi durduruldu: çıktısı 5 GB'ı geçti."
    if limit_s is not None and elapsed > limit_s:
        return (
            f'Arka plan komutu "{command}" arka plan süre sınırına ({limit_s / 60:.0f} dk) '
            "ulaştığı için durduruldu. İş hâlâ gerekiyorsa daha uzun timeout ile yeniden başlat."
        )
    return ""


def _stop(job_id: str, pid: int, folder: Path, log: Path, reason: str) -> None:
    try:
        terminate_process_tree(pid, force=False)
        ensure_process_group_exit(pid, graceful=True)
    except (OSError, CleanupFailedError):
        _LOG.exception("Arka plan işi durdurulamadı", extra={"is": job_id})
        return
    finally:
        with _LOCK:
            _OWNED.pop(job_id, None)
    try:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(f"\n[stderr]\n{reason}\n")
        if not (folder / f"{job_id}.exit").exists():
            atomic_replace_text(folder / f"{job_id}.exit", str(_TERMINATED_EXIT))
    except OSError:
        _LOG.exception("Durdurulan işin kaydı yazılamadı", extra={"is": job_id})


def cleanup_owned_jobs() -> int:
    """Bu sürecin başlattığı, hâlâ süren işleri durdur (oturum kapanışı); sayıyı döndür."""
    with _LOCK:
        owned = dict(_OWNED)
        _OWNED.clear()
    stopped = 0
    for job_id, (pid, folder) in owned.items():
        if (folder / f"{job_id}.exit").exists() or not _group_alive(pid):
            continue
        try:
            terminate_process_tree(pid, force=False)
            ensure_process_group_exit(pid, graceful=True)
            atomic_replace_text(folder / f"{job_id}.exit", str(_TERMINATED_EXIT))
            stopped += 1
        except (OSError, CleanupFailedError):
            _LOG.exception("Oturum kapanışında arka plan işi durdurulamadı", extra={"is": job_id})
    return stopped


def _group_alive(pid: int) -> bool:
    if os.name == "nt":
        return True
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
