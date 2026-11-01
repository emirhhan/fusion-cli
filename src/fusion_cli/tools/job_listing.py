"""`/tasks` için kabuk arka plan işlerini listele ve kullanıcı isteğiyle durdur (#333).

Claude Code (tools-reference, "Background commands"): `/tasks` arka plan görevlerini listeler
ve durdurur; kabuk işleri de bu listededir. Fusion'da kabuk işleri `.fusion/is/<kimlik>`
kaydındadır. Kullanıcı durdurması oturum kapsamına bakmaz (işi başlatan tur bağlamı çoktan
kapanmış olabilir) ama süreç başlangıç kimliğini doğrular: PID başka sürece geçtiyse durdurmaz.
"""

from __future__ import annotations

import json
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.errors import CleanupFailedError
from ..core.process_control import ensure_process_group_exit, terminate_process_tree
from .job_owner import process_identity
from .jobs import _JOB_ID, JOBS_DIR, _read_exit, _wrapper_gone

_TERMINATED_EXIT = 128 + signal.SIGTERM


@dataclass(frozen=True, slots=True)
class ShellJob:
    job_id: str
    command: str
    #: Çıkış kodu; `None` = sürüyor (ya da sarmalayıcısı kayıp, `lost`).
    exit_code: int | None
    lost: bool = False


def list_shell_jobs(root: Path) -> tuple[ShellJob, ...]:
    """Kökteki kabuk işleri, en yeniden eskiye."""
    folder = root / JOBS_DIR
    if not folder.is_dir():
        return ()
    commands = sorted(folder.glob("*.cmd"), key=lambda path: path.stat().st_mtime, reverse=True)
    jobs: list[ShellJob] = []
    for path in commands:
        job_id = path.stem
        if not _JOB_ID.match(job_id):
            continue
        try:
            command = path.read_text(encoding="utf-8").strip()
        except OSError:
            command = ""
        code = _read_exit(folder, job_id)
        lost = code is None and _wrapper_gone(folder, job_id)
        jobs.append(ShellJob(job_id, command, code, lost=lost))
    return tuple(jobs)


def stop_shell_job(root: Path, job_id: str) -> str:
    """Kullanıcı isteğiyle işi durdur; sonuç metnini döndür. Bulunamazsa `KeyError`."""
    folder = root / JOBS_DIR
    if not _JOB_ID.match(job_id) or not (folder / f"{job_id}.cmd").is_file():
        raise KeyError(job_id)
    if _read_exit(folder, job_id) is not None:
        return f"İş {job_id} zaten bitmiş."
    try:
        owner = json.loads((folder / f"{job_id}.owner.json").read_text(encoding="utf-8"))
        pid = int((folder / f"{job_id}.pid").read_text(encoding="utf-8"))
        if process_identity(pid, owner["token"]) != owner["identity"]:
            return f"İş {job_id} durdurulmadı: süreç başlangıcı değişmiş (PID başka sürece geçmiş)."
        terminate_process_tree(pid, force=False)
        ensure_process_group_exit(pid, graceful=True)
    except (OSError, ValueError, KeyError, TypeError, CleanupFailedError, subprocess.SubprocessError) as error:
        return f"İş {job_id} durdurulamadı: {error}"
    atomic_replace_text(folder / f"{job_id}.exit", str(_TERMINATED_EXIT))
    return f"İş {job_id} durduruldu."


def shell_job_lines(root: Path) -> list[str]:
    """`/tasks` listesinin kabuk işleri bölümü (boşsa boş liste)."""
    lines = []
    for job in list_shell_jobs(root):
        if job.exit_code is not None:
            status = f"bitti (çıkış {job.exit_code})"
        else:
            status = "sonlandı (çıkış kodu bilinmiyor)" if job.lost else "sürüyor"
        first = job.command.splitlines()[0] if job.command else ""
        lines.append(f"  kabuk {job.job_id} · {status} · {first[:70]}")
    return ["Kabuk işleri:", *lines] if lines else []
