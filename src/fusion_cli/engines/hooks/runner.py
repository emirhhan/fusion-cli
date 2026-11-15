"""Kanca komutunu çalıştırma (P-009): stdin'e olay JSON'u, zaman aşımı, çıktı sınırı.

Komut kullanıcının kendi ayarından gelir (model üretmez); bu yüzden onay akışından geçmez —
Claude Code ile aynı güven düzeyi. Proje dosyasından gelen kanca yalnız `fusion trust`
sonrası yüklenir (bkz. `config/hooks.py`).

`args` verilirse komut kabuksuz çalışır (exec biçimi): `command` PATH'te aranan
programdır, her `args` öğesi tek argümandır. Süreç kendi süreç grubunda açılır: zaman
aşımında ya da tur iptalinde kabukla birlikte
altındaki çocuklar da öldürülür (`edit_hooks._run` ile aynı ders, A1-40b).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import signal
from collections.abc import Mapping
from pathlib import Path

from ...core.env_scrub import scrubbed_env
from ...core.hooks.events import (
    HTTP_HANDLER,
    MCP_TOOL_HANDLER,
    MODEL_HANDLERS,
    HookCommand,
    HookEvent,
    HookRun,
)
from .handlers import HookServices, run_mcp_hook, run_model_hook

#: stdout/stderr'den okunan en fazla karakter (karar ve bağlam bundan çıkar).
HOOK_STREAM_CHARS = 64_000
#: Exec biçiminde yerleştirilen yol değişkenleri (Claude: `${CLAUDE_PROJECT_DIR}` vb.).
_PLACEHOLDER = re.compile(r"\$\{((?:CLAUDE|FUSION)_[A-Z_]+)\}")


async def run_hook(
    command: HookCommand,
    payload: Mapping[str, object],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    allow_private: bool = True,
    event: HookEvent | None = None,
    services: HookServices | None = None,
) -> HookRun:
    """Komutu kabukta çalıştır; sonucu hiçbir zaman istisna olarak fırlatmaz (iptal hariç).

    `http` türü `http_runner`'a gider (`allow_private`: iç ağ adresine izin);
    `mcp_tool`/`prompt`/`agent` `handlers`'a (oturumun `services` erişimiyle).
    """
    if command.handler == MCP_TOOL_HANDLER:
        return await run_mcp_hook(command, payload, services)
    if command.handler in MODEL_HANDLERS:
        return await run_model_hook(command, event, payload, services)
    if command.handler == HTTP_HANDLER:
        from .http_runner import run_http_hook

        return await run_http_hook(
            command, payload, environment=environment, allow_private=allow_private
        )
    if command.env:
        # Eklenti kancası: `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`, `CLAUDE_PLUGIN_OPTION_*`.
        environment = {**environment, **dict(command.env)}
    posix = os.name == "posix"
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    try:
        # CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1: kanca süreci kimlik bilgilerini görmez (#368).
        process = await _spawn(command, cwd=cwd, environment=scrubbed_env(environment), posix=posix)
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


async def _spawn(
    command: HookCommand, *, cwd: Path, environment: Mapping[str, str], posix: bool
) -> asyncio.subprocess.Process:
    """Exec biçimi (`args` varsa kabuksuz) ya da kabuk biçimi (`shell`: bash|powershell)."""
    streams = {
        "stdin": asyncio.subprocess.PIPE,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "cwd": str(cwd),
        "env": dict(environment),
        "start_new_session": posix,
    }
    if command.args is not None:
        argv = [substitute_placeholders(part, environment) for part in command.args]
        executable = substitute_placeholders(command.command, environment)
        return await asyncio.create_subprocess_exec(executable, *argv, **streams)  # type: ignore[arg-type]
    shell = _shell_program(command.shell)
    if shell is None:
        return await asyncio.create_subprocess_shell(command.command, **streams)  # type: ignore[arg-type]
    return await asyncio.create_subprocess_exec(*shell, command.command, **streams)  # type: ignore[arg-type]


def _shell_program(name: str) -> tuple[str, ...] | None:
    """`shell` alanı: `bash` (varsayılan; POSIX'te `sh -c` ile aynı yol) ya da `powershell`."""
    if name == "powershell":
        program = shutil.which("pwsh") or shutil.which("powershell") or "pwsh"
        return (program, "-NoProfile", "-Command")
    if name == "bash" and shutil.which("bash"):
        return ("bash", "-c")
    return None


def substitute_placeholders(text: str, environment: Mapping[str, str]) -> str:
    """Exec biçiminde `${CLAUDE_PROJECT_DIR}`/`${CLAUDE_PLUGIN_ROOT}`… düz metin olarak dolar."""
    return _PLACEHOLDER.sub(lambda match: environment.get(match.group(1), match.group(0)), text)


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
