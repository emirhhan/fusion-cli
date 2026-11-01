"""`!` kabuk komutu: canlı çıktı, Ctrl+B ile kesmeden arka plan görevi (#218, #219).

Claude Code (interactive-mode, "Shell mode with ! prefix" / "Background Bash commands"):
`!` komutunun ilerlemesi gerçek zamanlı akar; Ctrl+B komutu durdurmadan arka plana taşır,
çıktı bir dosyaya yazılmayı sürdürür, görev `/tasks` içinde görünür ve oturum kapanınca
temizlenir. Önceden Fusion komutu `subprocess.run` ile koşturup bitince basıyordu ve arka
plana alınan komut 120 sn sınırına bağlı, durdurulamaz ve listelenemezdi.

Burada süreç `asyncio` ile kendi süreç grubunda başlar; stdout+stderr tek akışta okunur,
her parça `on_chunk` geri çağrısına ve görev günlüğüne (`memory_dir/kabuk-gorevleri/`)
gider. Ön planda `SHELL_TIMEOUT_S` geçerlidir; arka plana alınan komutun süre sınırı yoktur.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from ...core.constants import MAX_OUTPUT_CHARS, PROCESS_POLL_S, PROCESS_TERMINATE_GRACE_S
from ...core.process_control import (
    process_group_options,
    terminate_async_process_tree,
    terminate_process_tree,
)

_LOG = logging.getLogger(__name__)
#: Okuma parçası (bayt).
_CHUNK = 4096
#: Bellekte tutulan çıktı (baş); fazlası günlükte kalır.
_KEEP_CHARS = MAX_OUTPUT_CHARS
_IDS = itertools.count(1)
JOBS_DIRNAME = "kabuk-gorevleri"


@dataclass(slots=True)
class ShellJob:
    """Süren ya da biten bir `!` komutu."""

    id: str
    command: str
    log_path: Path
    pid: int
    started_at: float = field(default_factory=time.time)
    detached: bool = False
    returncode: int | None = None
    stopped: bool = False
    #: Ctrl+B isteği; kurulduğu anda görev arka plandadır (yoklama beklenmez).
    detach: asyncio.Event | None = field(default=None, repr=False)

    @property
    def in_background(self) -> bool:
        return self.detached or (self.detach is not None and self.detach.is_set())

    @property
    def running(self) -> bool:
        return self.returncode is None and not self.stopped


class ShellJobs:
    """Oturumun `!` görevleri: `/tasks` listeler, durdurur; kapanışta hepsi öldürülür."""

    def __init__(self) -> None:
        self._jobs: dict[str, ShellJob] = {}

    def add(self, job: ShellJob) -> None:
        self._jobs[job.id] = job

    def get(self, job_id: str) -> ShellJob | None:
        return self._jobs.get(job_id.strip())

    def background(self) -> tuple[ShellJob, ...]:
        """Arka plana alınmış görevler (ön planda koşan `!` listelenmez)."""
        return tuple(job for job in self._jobs.values() if job.in_background)

    def stop(self, job_id: str) -> ShellJob | None:
        job = self.get(job_id)
        if job is None or not job.running:
            return job
        job.stopped = True
        with contextlib.suppress(Exception):
            terminate_process_tree(job.pid, force=True)
        return job

    def kill_all(self) -> int:
        """Oturum kapanışı: süren bütün `!` görevlerini öldür; kaç tane öldüğünü döndür."""
        alive = [job.id for job in self._jobs.values() if job.running]
        for job_id in alive:
            self.stop(job_id)
        return len(alive)


@dataclass(frozen=True, slots=True)
class LiveRun:
    """Biten komutun sonucu (çıktı baştan `_KEEP_CHARS` kadar; tamamı günlükte)."""

    returncode: int | None
    output: str
    timed_out: bool = False
    log_path: Path | None = None
    truncated: bool = False


@dataclass(slots=True)
class _Capture:
    parts: list[str] = field(default_factory=list)
    size: int = 0
    dropped: bool = False

    def add(self, text: str) -> None:
        room = _KEEP_CHARS - self.size
        if room <= 0:
            self.dropped = True
            return
        piece = text[:room]
        self.dropped = self.dropped or len(piece) < len(text)
        self.parts.append(piece)
        self.size += len(piece)


def new_job_id() -> str:
    return f"b{next(_IDS)}"


async def _pump(
    stream: asyncio.StreamReader,
    log: IO[str],
    capture: _Capture,
    on_chunk: Callable[[str], None] | None,
    job: ShellJob,
) -> None:
    decoder_errors = "replace"
    while chunk := await stream.read(_CHUNK):
        text = chunk.decode("utf-8", errors=decoder_errors).replace("\r\n", "\n")
        log.write(text)
        log.flush()
        capture.add(text)
        if on_chunk is not None and not job.in_background:
            try:
                on_chunk(text)
            except Exception:  # ekrana basma hatası komutu düşürmesin
                _LOG.exception("! çıktısı basılamadı")


async def run_live(
    command: str,
    *,
    cwd: Path,
    env: dict[str, str],
    log_dir: Path,
    timeout_s: float,
    jobs: ShellJobs | None = None,
    detach: asyncio.Event | None = None,
    on_chunk: Callable[[str], None] | None = None,
) -> LiveRun:
    """Komutu çalıştır, çıktıyı canlı akıt; `detach` kurulunca süre sınırı kalkar.

    Tur iptal edilirse (Esc) süreç grubu öldürülür. Arka plana alınmış komutta iptal
    çağıranın beklemesidir: komut sürer (`run_detachable` sonucu kendisi alır).
    """
    await asyncio.to_thread(log_dir.mkdir, parents=True, exist_ok=True)
    job_id = new_job_id()
    log_path = log_dir / f"{job_id}-{int(time.time())}.log"
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
        cwd=cwd,
        env=env,
        **process_group_options(),
    )
    job = ShellJob(job_id, command, log_path, process.pid, detach=detach)
    if jobs is not None:
        jobs.add(job)
    capture = _Capture()
    assert process.stdout is not None
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"$ {command}\n")
        reader = asyncio.ensure_future(_pump(process.stdout, log, capture, on_chunk, job))
        try:
            timed_out = await _wait_exit(process, job, detach, timeout_s)
            await asyncio.wait({reader}, timeout=PROCESS_TERMINATE_GRACE_S)
        except asyncio.CancelledError:
            if not job.in_background:
                await terminate_async_process_tree(process)
            raise
        finally:
            reader.cancel()
            job.returncode = process.returncode
    return LiveRun(
        process.returncode,
        "".join(capture.parts),
        timed_out=timed_out,
        log_path=log_path,
        truncated=capture.dropped,
    )


async def _wait_exit(
    process: asyncio.subprocess.Process,
    job: ShellJob,
    detach: asyncio.Event | None,
    timeout_s: float,
) -> bool:
    """Kabuk çıkana dek bekle (boruyu tutan `cmd &` çocuğu beklenmez); zaman aşımı True."""
    deadline = time.monotonic() + timeout_s
    while process.returncode is None:
        if detach is not None and detach.is_set():
            job.detached = True
        if not job.detached and time.monotonic() >= deadline:
            await terminate_async_process_tree(process)
            return True
        await asyncio.sleep(PROCESS_POLL_S / 10)
    if detach is not None and detach.is_set():
        job.detached = True
    return False
