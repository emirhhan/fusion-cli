"""Arka plan süreç başlangıcını owner kapsamında doğrulayan disk sözleşmesi."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.constants import PROCESS_CONTROL_TIMEOUT_S
from ..core.tools import ToolContext


def process_identity(pid: int, token: str) -> str:
    """POSIX start time + group + nonce; PID tek başına öldürme yetkisi değildir."""
    if os.name == "nt":
        raise ValueError("Bu platformda arka plan süreç kimliği doğrulaması desteklenmiyor.")
    result = subprocess.run(
        ["ps", "-ww", "-p", str(pid), "-o", "lstart=", "-o", "pgid=", "-o", "args="],
        capture_output=True,
        text=True,
        check=False,
        timeout=PROCESS_CONTROL_TIMEOUT_S,
    )
    identity = result.stdout.strip()
    if result.returncode or not identity or token not in identity:
        raise ValueError("İşin canlı süreç başlangıç kimliği doğrulanamadı.")
    return hashlib.sha256(identity.encode()).hexdigest()


def save_owner(
    folder: Path,
    job_id: str,
    pid: int,
    token: str,
    context: ToolContext,
    is_finished: Callable[[], bool],
) -> None:
    try:
        identity = process_identity(pid, token)
    except (OSError, ValueError, subprocess.SubprocessError):
        # Fast jobs may already have exited. Such a record allows observation,
        # never a speculative kill of a subsequently recycled PID.
        if not is_finished():
            raise ValueError("Canlı işin başlangıç kimliği kaydedilemedi.") from None
        identity = None
    atomic_replace_text(
        folder / f"{job_id}.owner.json",
        json.dumps(
            {
                "version": 1,
                "root": str(context.root.resolve()),
                "scope": context.job_scope,
                "pid": pid,
                "token": token,
                "identity": identity,
                "lifetime": "independent",
            }
        ),
    )


def verified_owner(folder: Path, job_id: str, context: ToolContext) -> int:
    try:
        value = json.loads((folder / f"{job_id}.owner.json").read_text())
        pid = int((folder / f"{job_id}.pid").read_text())
    except (OSError, ValueError):
        raise ValueError(
            "Eski veya bozuk işin süreç sahipliği doğrulanamadı; durdurulmadı."
        ) from None
    if (
        not isinstance(value, dict)
        or value.get("version") != 1
        or value.get("root") != str(context.root.resolve())
        or value.get("scope") != context.job_scope
        or value.get("pid") != pid
        or not isinstance(value.get("token"), str)
        or not value["token"]
        or not isinstance(value.get("identity"), str)
    ):
        raise ValueError("İş başka oturuma ait veya başlangıç kimliği belirsiz; durdurulmadı.")
    if process_identity(pid, value["token"]) != value["identity"]:
        raise ValueError("İşin süreç başlangıcı değişmiş; eski PID durdurulmadı.")
    return pid
