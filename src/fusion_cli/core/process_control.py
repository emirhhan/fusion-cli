"""Çağrıya ait süreç grubunu başlat, durdur ve gerçek çıkışı bekle."""

from __future__ import annotations

import os
import platform
import signal
import subprocess
import time
from pathlib import Path
from threading import Event
from typing import Any

from .clock import SystemClock
from .constants import PROCESS_CONTROL_TIMEOUT_S, PROCESS_POLL_S, PROCESS_TERMINATE_GRACE_S
from .errors import CleanupFailedError, ProcessCancelledError
from .protocols import Clock


def process_group_options() -> dict[str, Any]:
    """Platforma göre farklı subprocess kwargs; bu sınırda Any gereklidir."""
    if platform.system().casefold() == "windows":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)}
    return {"start_new_session": True}


def terminate_process_tree(pid: int, *, force: bool) -> None:
    """Yalnız caller'ın sahipliğini doğruladığı süreç grubuna uygula."""
    try:
        if platform.system().casefold() == "windows":
            flags = ["/F"] if force else []
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", *flags],
                capture_output=True,
                check=False,
                timeout=PROCESS_CONTROL_TIMEOUT_S,
            )
            if result.returncode:
                raise CleanupFailedError("Süreç ağacı Windows tarafından durdurulamadı.")
        else:
            os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        return
    except (OSError, subprocess.SubprocessError) as error:
        raise CleanupFailedError(f"Süreç ağacı temizlenemedi ({type(error).__name__}).") from None


def _group_exists(pid: int) -> bool:
    # macOS can briefly report EPERM while a killed group is being reaped.
    # Retry observation only, never treat a permission error as absent.
    deadline = time.monotonic() + PROCESS_TERMINATE_GRACE_S
    while True:
        try:
            os.killpg(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CleanupFailedError(
                    "Süreç grubu çıkışı doğrulanamadı (PermissionError)."
                ) from None
            time.sleep(min(PROCESS_POLL_S, remaining))
        except OSError as error:
            raise CleanupFailedError(
                f"Süreç grubu çıkışı doğrulanamadı ({type(error).__name__})."
            ) from None


def _drain(process: subprocess.Popen[str], *, force: bool) -> tuple[str, str]:
    terminate_process_tree(process.pid, force=force)
    try:
        output = process.communicate(timeout=PROCESS_TERMINATE_GRACE_S)
    except subprocess.TimeoutExpired:
        terminate_process_tree(process.pid, force=True)
        try:
            output = process.communicate(timeout=PROCESS_TERMINATE_GRACE_S)
        except subprocess.TimeoutExpired:
            raise CleanupFailedError(
                "Süreç çıkışı veya çıktı borularının kapanması doğrulanamadı."
            ) from None
    ensure_process_group_exit(process.pid)
    return output


def ensure_process_group_exit(pid: int, *, graceful: bool = False) -> None:
    """Confirm an owned POSIX group vanished, even after the leader was reaped."""
    # Reaping the shell does not prove that detached-output descendants exited.
    # The owned session ID remains the process group ID after its leader exits.
    if graceful and os.name != "nt":
        deadline = time.monotonic() + PROCESS_TERMINATE_GRACE_S
        while _group_exists(pid) and time.monotonic() < deadline:
            time.sleep(min(PROCESS_POLL_S, max(0, deadline - time.monotonic())))
    if os.name != "nt" and _group_exists(pid):
        terminate_process_tree(pid, force=True)
        deadline = time.monotonic() + PROCESS_TERMINATE_GRACE_S
        while _group_exists(pid):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CleanupFailedError("Süreç grubunun tamamen kapandığı doğrulanamadı.")
            time.sleep(min(PROCESS_POLL_S, remaining))


def run_foreground(
    command: str,
    *,
    cwd: Path,
    env: dict[str, str],
    cancelled: Event,
    timeout_s: float,
    clock: Clock | None = None,
) -> subprocess.CompletedProcess[str]:
    """İptal/timeout sonucunu ancak sahipli grup drain edildikten sonra döndür."""
    if cancelled.is_set():
        raise ProcessCancelledError("Komut başlamadan iptal edildi.")
    timing = clock or SystemClock()
    deadline = timing.monotonic() + timeout_s
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        **process_group_options(),
    )
    cleanup_started = False
    try:
        while True:
            if cancelled.is_set():
                cleanup_started = True
                _drain(process, force=False)
                raise ProcessCancelledError("Komut ve sahip olunan çocuk süreçler durduruldu.")
            remaining = deadline - timing.monotonic()
            if remaining <= 0:
                cleanup_started = True
                stdout, stderr = _drain(process, force=True)
                raise subprocess.TimeoutExpired(command, timeout_s, output=stdout, stderr=stderr)
            try:
                stdout, stderr = process.communicate(timeout=min(PROCESS_POLL_S, remaining))
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        if not cleanup_started:
            _drain(process, force=True)
        raise
