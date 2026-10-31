"""Kanca komutunu çalıştırma (P-009): stdin'e olay JSON'u, zaman aşımı, çıktı sınırı.

Komut kullanıcının kendi ayarından gelir (model üretmez); bu yüzden onay akışından geçmez —
Claude Code ile aynı güven düzeyi. Proje dosyasından gelen kanca yalnız `fusion trust`
sonrası yüklenir (bkz. `config/hooks.py`).

Süreç kendi süreç grubunda açılır: zaman aşımında ya da tur iptalinde kabukla birlikte
altındaki çocuklar da öldürülür (`edit_hooks._run` ile aynı ders, A1-40b).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
from collections.abc import Mapping
from pathlib import Path

from ...core.hooks.events import HookCommand, HookRun

#: stdout/stderr'den okunan en fazla karakter (karar ve bağlam bundan çıkar).
HOOK_STREAM_CHARS = 64_000


async def run_hook(
    command: HookCommand,
    payload: Mapping[str, object],
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> HookRun:
    """Komutu kabukta çalıştır; sonucu hiçbir zaman istisna olarak fırlatmaz (iptal hariç)."""
    posix = os.name == "posix"
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    try:
        process = await asyncio.create_subprocess_shell(
            command.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env=dict(environment),
            start_new_session=posix,
        )
    except OSError as error:
        return HookRun(command, None, error=str(error))
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(body), timeout=command.timeout_s
        )
    except TimeoutError:
        await _kill(process, posix)
        return HookRun(command, None, timed_out=True)
    except asyncio.CancelledError:
        await _kill(process, posix)
        raise
    return HookRun(
        command,
        process.returncode,
        _decode(stdout),
        _decode(stderr),
    )


async def _kill(process: asyncio.subprocess.Process, posix: bool) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        if posix:
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    with contextlib.suppress(ProcessLookupError):
        await process.wait()


def _decode(raw: bytes | None) -> str:
    return (raw or b"").decode("utf-8", errors="replace")[:HOOK_STREAM_CHARS]
