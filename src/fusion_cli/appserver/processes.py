"""Oturuma bağlı terminal/geliştirme süreçleri ve sınırlı çıktı tamponları."""

from __future__ import annotations

import asyncio
import os
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.constants import PROCESS_TERMINATE_GRACE_S
from ..core.errors import CleanupFailedError
from ..core.owned_thread import await_owned_thread
from ..core.process_control import ensure_process_group_exit
from ..core.process_control import process_group_options as _process_group_kwargs
from ..core.process_control import terminate_process_tree as terminate_process_tree
from .bridges import Writer
from .protocol import encode_event
from .workspace import WorkspacePathError, resolve_workspace_path


def shell_command(system: str, shell: str | None, command: str) -> tuple[str, ...]:
    """Kullanıcının yazdığı komutu, platformun kabuğuyla çalıştıracak argv üretir.

    Windows'ta `/bin/zsh` ve `/bin/sh` yoktur; `SHELL` değişkeni de genelde
    tanımsızdır. Orada `cmd.exe /c` kullanılır — kullanıcı Komut İstemi'nde ne
    yazıyorsa Fusion'ın terminalinde de aynısını yazabilsin diye.
    """
    if system.casefold() == "windows":
        return (os.environ.get("COMSPEC", "cmd.exe"), "/c", command)
    return (shell or "/bin/sh", "-lc", command)


_MAX_BUFFER = 256 * 1024


@dataclass
class ManagedProcess:
    process_id: str
    command: str
    cwd: Path
    process: asyncio.subprocess.Process
    started_at: float
    status: str = "calisiyor"
    output: str = ""
    exit_code: int | None = None
    pump: asyncio.Task[None] | None = None

    def snapshot(self, root: Path) -> dict[str, Any]:
        try:
            cwd = self.cwd.relative_to(root.resolve()).as_posix() or "."
        except ValueError:
            cwd = "."
        return {
            "surec_id": self.process_id,
            "komut": self.command,
            "cwd": cwd,
            "pid": self.process.pid,
            "durum": self.status,
            "cikis_kodu": self.exit_code,
            "cikti": self.output,
            "baslangic": self.started_at,
        }


class ProcessManager:
    """Bir `AppSession`ın çocuk süreçlerini birbirinden yalıtır."""

    def __init__(self, root: Path, writer: Writer, *, max_buffer: int = _MAX_BUFFER) -> None:
        self.root = root.resolve()
        self._writer = writer
        self._max_buffer = max_buffer
        self._records: dict[str, ManagedProcess] = {}
        self._counter = 0

    def update_root(self, root: Path) -> None:
        self.root = root.resolve()

    async def start(self, data: dict[str, Any]) -> dict[str, Any]:
        command = data.get("komut")
        if not isinstance(command, str) or not command.strip():
            return {"ok": False, "metin": "Çalıştırılacak komut boş olamaz."}
        if len(command) > 8192:
            return {"ok": False, "metin": "Komut çok uzun."}
        try:
            cwd = resolve_workspace_path(self.root, data.get("cwd", ""))
        except WorkspacePathError as error:
            return {"ok": False, "metin": str(error)}
        if not cwd.is_dir():
            return {"ok": False, "metin": "Çalışma klasörü bulunamadı."}

        shell = os.environ.get("SHELL")
        if shell and not await asyncio.to_thread(Path(shell).is_file):
            shell = None
        argv = shell_command(platform.system(), shell, command)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                **_process_group_kwargs(),
            )
        except OSError:
            return {"ok": False, "metin": "Süreç başlatılamadı."}
        self._counter += 1
        process_id = f"surec-{self._counter}"
        record = ManagedProcess(process_id, command, cwd, process, time.time())
        self._records[process_id] = record
        record.pump = asyncio.create_task(self._pump(record))
        self._event("ProcessStatus", record, durum="calisiyor")
        return {"ok": True, **record.snapshot(self.root)}

    async def write(self, data: dict[str, Any]) -> dict[str, Any]:
        record = self._record(data)
        if record is None or record.status != "calisiyor" or record.process.stdin is None:
            return {"ok": False, "metin": "Çalışan süreç bulunamadı."}
        text = data.get("metin")
        if not isinstance(text, str):
            return {"ok": False, "metin": "Terminal girdisi metin olmalıdır."}
        try:
            record.process.stdin.write(text.encode("utf-8"))
            await record.process.stdin.drain()
        except (BrokenPipeError, ConnectionError):
            return {"ok": False, "metin": "Süreç artık girdi kabul etmiyor."}
        return {"ok": True}

    def list(self) -> dict[str, Any]:
        records = sorted(self._records.values(), key=lambda item: item.started_at)
        return {"ok": True, "surecler": [record.snapshot(self.root) for record in records]}

    async def stop(self, data: dict[str, Any]) -> dict[str, Any]:
        record = self._record(data)
        if record is None:
            return {"ok": False, "metin": "Süreç bulunamadı."}
        await self._stop_record(record)
        return {"ok": True, **record.snapshot(self.root)}

    async def close(self) -> None:
        results = await asyncio.gather(
            *(self._stop_record(record) for record in tuple(self._records.values())),
            return_exceptions=True,
        )
        if any(isinstance(result, BaseException) for result in results):
            raise CleanupFailedError(
                "Bir veya daha fazla terminal sürecinin kapanışı doğrulanamadı."
            )

    def _record(self, data: dict[str, Any]) -> ManagedProcess | None:
        process_id = data.get("surec_id")
        return self._records.get(process_id) if isinstance(process_id, str) else None

    async def _pump(self, record: ManagedProcess) -> None:
        stdout = record.process.stdout
        if stdout is not None:
            while chunk := await stdout.read(4096):
                text = chunk.decode("utf-8", errors="replace")
                record.output = (record.output + text)[-self._max_buffer :]
                self._event("ProcessOutput", record, metin=text)
        code = await record.process.wait()
        # Observe owned group cleanup immediately, before releasing the live
        # process identity. A later stop must never target a recycled old PID.
        try:
            await await_owned_thread(ensure_process_group_exit, record.process.pid)
        except CleanupFailedError:
            record.status = "temizlik_dogrulanamadi"
            self._event("ProcessStatus", record, durum=record.status, cikis_kodu=code)
            raise
        record.exit_code = code
        if record.status == "calisiyor":
            record.status = "bitti" if code == 0 else "hata"
        self._event("ProcessStatus", record, durum=record.status, cikis_kodu=code)

    async def _stop_record(self, record: ManagedProcess) -> None:
        if record.process.returncode is not None and (record.pump is None or record.pump.done()):
            if record.pump is not None:
                await record.pump
            return
        record.status = "durduruluyor"
        self._event("ProcessStatus", record, durum=record.status)
        try:
            await await_owned_thread(terminate_process_tree, record.process.pid, force=False)
            try:
                await asyncio.wait_for(record.process.wait(), timeout=PROCESS_TERMINATE_GRACE_S)
            except TimeoutError:
                await await_owned_thread(terminate_process_tree, record.process.pid, force=True)
                await asyncio.wait_for(record.process.wait(), timeout=PROCESS_TERMINATE_GRACE_S)
            await await_owned_thread(ensure_process_group_exit, record.process.pid)
            if record.pump is not None and record.pump is not asyncio.current_task():
                try:
                    await asyncio.wait_for(asyncio.shield(record.pump), PROCESS_TERMINATE_GRACE_S)
                except TimeoutError:
                    await await_owned_thread(terminate_process_tree, record.process.pid, force=True)
                    await asyncio.wait_for(asyncio.shield(record.pump), PROCESS_TERMINATE_GRACE_S)
        except (TimeoutError, CleanupFailedError):
            record.status = "temizlik_dogrulanamadi"
            self._event("ProcessStatus", record, durum=record.status)
            raise CleanupFailedError("Terminal süreci veya çıktı akışı kapanmadı.") from None
        record.exit_code = record.process.returncode
        record.status = "durduruldu"
        self._event("ProcessStatus", record, durum=record.status, cikis_kodu=record.exit_code)

    def _event(self, event: str, record: ManagedProcess, **extra: object) -> None:
        self._writer(
            encode_event(
                {
                    "olay": event,
                    "surec_id": record.process_id,
                    "pid": record.process.pid,
                    **extra,
                }
            )
        )
