"""Zaman aşımına uğrayan ön plan komutunu arka plan işine devret (Claude Code, #319).

Claude Code (tools-reference, "Foreground commands that move to the background"): ön
plandaki komut zaman aşımına uğrarsa durdurulmaz, arka plana taşınır; `sleep` ile başlayan
komutlar hariç. Sonuç görev kimliğini ve çıktı dosyasının yolunu verir.

Süreç yeniden başlatılmaz: aynı süreç ve boruları `.fusion/is/<kimlik>` kaydına geçer,
böylece `job_status` (durum, son çıktı, durdurma) eski arka plan işleriyle aynı yoldan çalışır.
Sahiplik doğrulaması için `run_foreground(ownership_marker=…)` komut başına
`: fusion-job-<nonce>` işareti ekler (bkz. `core.process_control`).
"""

from __future__ import annotations

import logging
import re
import shlex
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.constants import PROCESS_TERMINATE_GRACE_S
from ..core.process_control import MovedToBackgroundError
from ..core.tools import ToolContext, ToolResult
from .bash_settings import background_disabled
from .job_delivery import save_completion, save_delivery
from .job_lifetime import own, time_limit_s
from .job_owner import save_owner
from .jobs import JOBS_DIR, _reserve_job_id

_LOG = logging.getLogger(__name__)


def new_token() -> str:
    return "fusion-job-" + uuid.uuid4().hex


def can_adopt(command: str) -> bool:
    """Bu komut zaman aşımında arka plana taşınabilir mi?"""
    if background_disabled():
        return False
    try:
        words = shlex.split(command, comments=True)
    except ValueError:
        words = command.split()
    return bool(words) and words[0] != "sleep"


def adopt(
    moved: MovedToBackgroundError,
    command: str,
    token: str,
    context: ToolContext,
    on_exit: Callable[[], str],
) -> ToolResult:
    """Süren süreci iş klasörüne kaydet; çıktısı artık günlüğe akar."""
    folder = context.root / JOBS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    job_id = _reserve_job_id(folder, command)
    log = folder / f"{job_id}.log"
    delivery = save_delivery(folder, job_id, command, None, ())
    sink = _LogSink(log)
    so_far = [capture.text() for capture in moved.captures]
    sink.write("".join(so_far).encode("utf-8"))
    for capture in moved.captures:
        capture.redirect(sink.write)
    process = moved.process
    save_owner(folder, job_id, process.pid, token, context, lambda: process.poll() is not None)
    atomic_replace_text(folder / f"{job_id}.pid", str(process.pid))
    own(job_id, process.pid, folder, log=log, command=command, limit_s=time_limit_s(moved=True))
    threading.Thread(
        target=_watch,
        args=(moved, folder, context.root, job_id, sink, on_exit),
        name=f"fusion-job-{job_id}",
        daemon=True,
    ).start()
    partial = "".join(so_far).strip()
    lead = (
        "Komut kullanıcı isteğiyle (Ctrl+B) arka plana taşındı"
        if moved.by_user
        else f"Komut {moved.timeout_s:.0f} sn zaman aşımında bitmedi ve arka plana taşındı"
    )
    text = (
        f"{lead} (iş kimliği: {job_id}).\nÇıktı dosyası: {log}\n"
        f"Durum ve son çıktı için job_status(id='{job_id}', wait_s=...) çağır; "
        "gerekirse job_status(id, stop=true) ile durdur."
    )
    if _changes_directory(command):
        text += (
            f"\nOturum dizini {context.root} olarak kalır; arka plana taşınan komuttaki dizin "
            "değişiklikleri sonraki komutlara uygulanmaz."
        )
    if partial:
        text += f"\n\n[şimdiye kadarki çıktı]\n{partial[-2000:]}"
    return ToolResult(text, job_completion=delivery)


_CD_WORDS = re.compile(r"(?:^|[;&|(]\s*|\s)(?:cd|pushd|popd|chdir)(?:\s|$|;)")


def _changes_directory(command: str) -> bool:
    """Komutta `cd`/`pushd`/`popd`/`chdir` var mı (Claude: taşınan komutta kalıcı olmaz, #374)?"""
    return bool(_CD_WORDS.search(command))


class _LogSink:
    """İki borunun (stdout/stderr) baytlarını aynı günlüğe sırayla ekler."""

    def __init__(self, path: Path) -> None:
        self._stream = path.open("ab")
        self._lock = threading.Lock()

    def write(self, chunk: bytes) -> None:
        with self._lock:
            if not self._stream.closed:
                self._stream.write(chunk)
                self._stream.flush()

    def close(self) -> None:
        with self._lock:
            self._stream.close()


def _watch(
    moved: MovedToBackgroundError,
    folder: Path,
    root: Path,
    job_id: str,
    sink: _LogSink,
    on_exit: Callable[[], str],
) -> None:
    code = moved.process.wait()
    for capture in moved.captures:
        capture.wait_eof(PROCESS_TERMINATE_GRACE_S)
    try:
        note = on_exit()
        if note:
            sink.write(note.encode("utf-8"))
    except (OSError, ValueError):
        _LOG.exception("Taşınan işin kaynakları kapatılamadı", extra={"is": job_id})
    sink.close()
    exit_path = folder / f"{job_id}.exit"
    if exit_path.exists():  # job_status(stop=true) önce yazdıysa korunur
        return
    atomic_replace_text(exit_path, str(code))
    try:
        save_completion(folder, root, job_id, code)
    except (OSError, ValueError):
        _LOG.exception("Taşınan işin tamamlanma makbuzu yazılamadı", extra={"is": job_id})
