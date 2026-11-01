"""Ctrl+B ile devredilen `run_shell` komutu: süreç yaşar, çıktı günlüğe gider (#218).

Claude Code: "Background Bash commands" — çalışan komut durdurulmadan arka plana taşınır,
çıktı bir dosyaya yazılır, Claude çalışmaya devam eder ve dosyayı okuyarak sonucu alır.
Devirde ön plan süre sınırı kalkar. Günlük `<kök>/.fusion/is/devir-<kimlik>.log`; komut
bitince son satır `(çıkış kodu N)` olur. Oturum kapanınca süren komutlar öldürülür
(`kill_handed_off`).
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from pathlib import Path

from ..core.bounded_capture import BoundedCapture
from ..core.constants import EXIT_CODE_PREFIX, PROCESS_TERMINATE_GRACE_S
from ..core.process_control import ProcessDetachedError, terminate_process_tree
from ..core.shell_handoff import HandedOffShell, ShellHandoff
from ..core.tools import ToolContext, ToolResult
from .jobs import JOBS_DIR

_LOG = logging.getLogger(__name__)
_POLL_S = 0.2


def _log_path(context: ToolContext, job_id: str) -> Path:
    folder = context.root / JOBS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"devir-{job_id}-{int(time.time())}.log"


def hand_off(
    command: str, detached: ProcessDetachedError, context: ToolContext, handoff: ShellHandoff
) -> ToolResult:
    """Süreci devral: izleyici iş parçacığı bitişi bekler, çıktıyı günlüğe yazar."""
    placeholder = Path("-")
    job = handoff.add(command, detached.process.pid, placeholder)
    try:
        job.log_path = _log_path(context, job.id)
        _write_snapshot(job, detached.captures, final=False)
    except OSError as error:
        _LOG.warning("devir günlüğü açılamadı: %s", error)
    threading.Thread(
        target=_watch, args=(job, detached), name=f"fusion-devir-{job.id}", daemon=True
    ).start()
    return ToolResult(
        f"Komut kullanıcı isteğiyle (Ctrl+B) arka plana alındı ve sürüyor: {job.id}.\n"
        f"Çıktı dosyası: {job.log_path} — sonucu görmek için bu dosyayı oku; bitince son "
        f"satırı `{EXIT_CODE_PREFIX}N)` olur. Komutu yeniden çalıştırma; işine devam et.",
        ok=True,
    )


def _watch(job: HandedOffShell, detached: ProcessDetachedError) -> None:
    process = detached.process
    last = 0.0
    while process.poll() is None and not job.stopped:
        time.sleep(_POLL_S)
        if time.monotonic() - last > 1.0:
            last = time.monotonic()
            with contextlib.suppress(OSError):
                _write_snapshot(job, detached.captures, final=False)
    with contextlib.suppress(Exception):
        process.wait(timeout=PROCESS_TERMINATE_GRACE_S)
    for capture in detached.captures:
        capture.wait_eof(PROCESS_TERMINATE_GRACE_S)
    job.returncode = process.returncode
    with contextlib.suppress(OSError):
        _write_snapshot(job, detached.captures, final=True)


def _write_snapshot(
    job: HandedOffShell, captures: tuple[BoundedCapture, ...], *, final: bool
) -> None:
    body = "\n".join(text for capture in captures if (text := capture.text().strip()))
    tail = f"\n{EXIT_CODE_PREFIX}{job.returncode})\n" if final else "\n"
    job.log_path.write_text(f"$ {job.command}\n{body}{tail}", encoding="utf-8")


def stop_handed_off(handoff: ShellHandoff, job_id: str) -> HandedOffShell | None:
    job = handoff.get(job_id)
    if job is None or not job.running:
        return job
    job.stopped = True
    with contextlib.suppress(Exception):
        terminate_process_tree(job.pid, force=True)
    return job


def kill_handed_off(handoff: ShellHandoff | None) -> int:
    """Oturum kapanışı: süren devredilmiş komutları öldür."""
    if handoff is None:
        return 0
    alive = [job.id for job in handoff.jobs if job.running]
    for job_id in alive:
        stop_handed_off(handoff, job_id)
    return len(alive)
