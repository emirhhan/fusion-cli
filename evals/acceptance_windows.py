"""Windows'ta kabul planını CMD ayrıştırmasına göndermeden yürüt."""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import sys
from pathlib import Path
from subprocess import CompletedProcess

from evals.acceptance_command import CommandChain
from fusion_cli.core.constants import PROCESS_TERMINATE_GRACE_S
from fusion_cli.core.errors import CleanupFailedError
from fusion_cli.core.process_control import process_group_options, terminate_process_tree


async def run_windows_acceptance(
    chain: CommandChain, workspace: Path, env: dict[str, str], timeout_s: float
) -> CompletedProcess[bytes]:
    """Onaylı argv listesini, köke bağlı çalışma diziniyle sırayla çalıştır."""
    root = await asyncio.to_thread(workspace.resolve)
    cwd = root
    status = 0
    stdout, stderr = bytearray(), bytearray()
    async with asyncio.timeout(timeout_s):
        for index, arguments in enumerate(chain.commands):
            operator = chain.operators[index - 1] if index else ";"
            if (operator == "&&" and status != 0) or (operator == "||" and status == 0):
                continue
            if arguments[0] == "cd":
                destination = (cwd / arguments[1]).resolve()
                if not destination.is_relative_to(root) or not destination.is_dir():
                    status = 1
                    continue
                cwd, status = destination, 0
                continue
            result = await _run(arguments, cwd, env)
            status = result.returncode
            stdout.extend(result.stdout)
            stderr.extend(result.stderr)
    return CompletedProcess(chain.commands[-1], status, bytes(stdout), bytes(stderr))


async def _run(
    arguments: tuple[str, ...], cwd: Path, env: dict[str, str]
) -> CompletedProcess[bytes]:
    command, *args = arguments
    if command in {"true", "false"} and not args:
        return CompletedProcess(arguments, int(command == "false"), b"", b"")
    if command == "sleep" and len(args) == 1:
        try:
            delay = float(args[0])
        except ValueError:
            delay = -1.0
        if not math.isfinite(delay) or delay < 0:
            return CompletedProcess(arguments, 1, b"", b"Invalid duration\n")
        await asyncio.sleep(delay)
        return CompletedProcess(arguments, 0, b"", b"")
    if command == "test" and len(args) == 2 and args[0] in {"-e", "-f", "-d"}:
        path = cwd / args[1]
        test = {"-e": path.exists, "-f": path.is_file, "-d": path.is_dir}[args[0]]
        return CompletedProcess(arguments, int(not test()), b"", b"")
    if command == "pwd" and not args:
        return CompletedProcess(arguments, 0, f"{cwd}\n".encode(), b"")
    if command == "echo" and not any(arg.startswith("-") for arg in args):
        return CompletedProcess(arguments, 0, (" ".join(args) + "\n").encode(), b"")

    executable = Path(sys.executable) if command == sys.executable else _executable(command, env)
    process = await asyncio.create_subprocess_exec(
        str(executable),
        *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **process_group_options(),
    )
    try:
        stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        if process.returncode is None:
            with contextlib.suppress(CleanupFailedError):
                await asyncio.to_thread(terminate_process_tree, process.pid, force=True)
            with contextlib.suppress(ProcessLookupError):
                process.kill()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(process.communicate(), PROCESS_TERMINATE_GRACE_S)
        raise
    assert process.returncode is not None
    return CompletedProcess(arguments, process.returncode, stdout, stderr)


def _executable(command: str, env: dict[str, str]) -> Path:
    # Windows CreateProcess çalışma dizinini ve script uzantılarını aramasın.
    # Planlayıcının izin verdiği adları yalnız mutlak PATH girdilerinde ara.
    for item in env.get("PATH", "").split(os.pathsep):
        directory = Path(item.strip('"'))
        if directory.is_absolute():
            candidate = directory / f"{command}.exe"
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(f"Kabul aracı PATH'te bulunamadı: {command}")
