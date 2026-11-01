"""Ajanın süren ön plan kabuk komutunu Ctrl+B ile kesmeden arka plana alma kanalı (#218).

Claude Code (interactive-mode, "Background Bash commands"): Ctrl+B çalışan Bash komutunu
durdurmadan arka plana taşır ve Claude çalışmaya devam eder. Fusion'da `run_shell` ön plan
komutu `process_control.run_foreground` içinde bekler; bu kanal kurulduğunda bekleme biter,
süreç yaşamaya devam eder, araç sonucu modele "arka planda sürüyor, çıktı şu dosyada" der
ve tur kesilmez. Kanal oturum başınadır (TUI `ReplState.shell_handoff`), yalnız stdlib.
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from pathlib import Path

_IDS = itertools.count(1)


@dataclass(slots=True)
class HandedOffShell:
    """Arka plana devredilmiş ajan kabuk komutu."""

    id: str
    command: str
    pid: int
    #: Çıktı günlüğü; proje ve geçici dizinde açılamadıysa None (çıktı kaydedilmez).
    log_path: Path | None
    returncode: int | None = None
    stopped: bool = False

    @property
    def running(self) -> bool:
        return self.returncode is None and not self.stopped


@dataclass(slots=True)
class ShellHandoff:
    """Süren ön plan komutlarının devir isteği ve devredilen komutların kaydı."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _active: int = 0
    _event: threading.Event = field(default_factory=threading.Event, repr=False)
    jobs: list[HandedOffShell] = field(default_factory=list)

    def begin(self) -> threading.Event:
        """Ön plan komutu başladı; devir isteği bu olayla gelir."""
        with self._lock:
            if self._active == 0:
                self._event = threading.Event()
            self._active += 1
            return self._event

    def end(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)

    def request(self) -> bool:
        """Ctrl+B: süren ön plan komutu varsa devret; varsa True."""
        with self._lock:
            if self._active == 0:
                return False
            self._event.set()
            return True

    def add(self, command: str, pid: int, log_path: Path | None = None) -> HandedOffShell:
        job = HandedOffShell(f"a{next(_IDS)}", command, pid, log_path)
        with self._lock:
            self.jobs.append(job)
        return job

    def get(self, job_id: str) -> HandedOffShell | None:
        with self._lock:
            return next((job for job in self.jobs if job.id == job_id.strip()), None)
