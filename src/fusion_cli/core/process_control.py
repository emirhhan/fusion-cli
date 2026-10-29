"""Çağrıya ait süreç grubunu başlat, durdur ve gerçek çıkışı bekle."""

from __future__ import annotations

import asyncio
import contextlib
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
            # Kaçanlar ÖNCE ve hemen SIGKILL ile: kabuk ölünce init'e geçerler, ebeveyn
            # zinciri kopar ve ikinci (zorlayıcı) turda bir daha bulunamazlar.
            escaped = _escaped_descendants(pid) if _group_alive(pid) else []
            for child in escaped:
                _signal_quietly(child, signal.SIGKILL)
            os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
            _await_exit(escaped)
    except ProcessLookupError:
        return
    except PermissionError:
        # macOS, yalnız zombilerden oluşan grup için EPERM döndürür. Çıkış burada
        # varsayılmaz; `ensure_process_group_exit` grubu ayrıca doğrular.
        if os.name == "nt":
            raise CleanupFailedError("Süreç ağacı temizlenemedi (PermissionError).") from None
        return
    except (OSError, subprocess.SubprocessError) as error:
        raise CleanupFailedError(f"Süreç ağacı temizlenemedi ({type(error).__name__}).") from None


def _escaped_descendants(pid: int) -> list[int]:
    """`setsid` ile gruptan çıkmış torunlar: `killpg` onlara ulaşmaz.

    Ölçüldü (29 Ekim): gruptan kaçan torun stdout borusunu açık tuttuğu için iptal
    `CleanupFailedError` ile bitiyor, torun yaşamaya devam ediyordu. Ebeveyn zinciri
    yalnız kabuk yaşarken okunabilir; çift fork ile init'e geçmiş süreç bulunamaz.
    """
    try:
        listing = subprocess.run(
            ["ps", "-A", "-o", "pid=", "-o", "ppid=", "-o", "pgid="],
            capture_output=True,
            text=True,
            check=False,
            timeout=PROCESS_CONTROL_TIMEOUT_S,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    children: dict[int, list[tuple[int, int]]] = {}
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) == 3 and all(field.isdigit() for field in fields):
            child, parent, group = map(int, fields)
            children.setdefault(parent, []).append((child, group))
    escaped: list[int] = []
    stack = [pid]
    while stack:
        for child, group in children.get(stack.pop(), []):
            stack.append(child)
            if group != pid:
                escaped.append(child)
    return escaped


def _group_alive(pid: int) -> bool:
    """Grup hâlâ var mı? Yoksa `pid` geri dönüştürülmüş olabilir; çocukları bizim değildir."""
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # macOS: yalnız zombilerden oluşan grup
    return True


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
        timeout=PROCESS_CONTROL_TIMEOUT_S,
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


def _await_exit(pids: list[int]) -> None:
    """Kaçan torunların gerçekten çıktığını doğrula; çıkmadıysa başarı bildirme."""
    deadline = time.monotonic() + PROCESS_TERMINATE_GRACE_S
    remaining = [pid for pid in pids if _alive(pid)]
    while remaining:
        if time.monotonic() >= deadline:
            raise CleanupFailedError("Süreç grubundan ayrılmış bir alt süreç durdurulamadı.")
        time.sleep(PROCESS_POLL_S / 10)
        remaining = [pid for pid in remaining if _alive(pid)]


def _signal_quietly(pid: int, sig: signal.Signals) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        return


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


async def terminate_async_process_tree(process: asyncio.subprocess.Process) -> None:
    """`asyncio` kabuk sürecinin SAHİP OLUNAN grubunu ve kaçak torunları öldür.

    `process_group_options()` ile başlatılmış sürece uygulanır. `process.kill()` yalnız
    kabuğu öldürür; `npm → node → tsc` zinciri ve açık port/dosya kilidi yetim kalırdı.
    Engelleyici `ps`/`killpg` çağrıları iş parçacığında koşar (olay döngüsünü dondurmaz)
    ve `shield` altındadır: temizlik sırasında gelen iptal temizliği yarıda bırakmaz.
    """
    pid = process.pid

    def _temizle() -> None:
        try:
            terminate_process_tree(pid, force=True)
        finally:
            ensure_process_group_exit(pid)

    await asyncio.shield(asyncio.to_thread(_temizle))
    if process.returncode is None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=PROCESS_TERMINATE_GRACE_S)


async def wait_for_shell_exit(process: asyncio.subprocess.Process) -> int:
    """Kabuğun ÇIKIŞINI bekle; çıktı borularının kapanmasını beklemez.

    `Process.wait()` boru uçları kapanana dek döner: arka plana süreç doğuran komut
    (`dev server &`) boruyu açık tutunca kabuk çıksa da sonsuza dek takılır (ölçüldü,
    29 Ekim). `returncode` ise kabuk çıkar çıkmaz dolar; bu yüzden yoklanır.
    """
    while process.returncode is None:  # noqa: ASYNC110 - Process.wait() boru kapanmasına bağlı
        await asyncio.sleep(PROCESS_POLL_S / 10)
    return process.returncode
