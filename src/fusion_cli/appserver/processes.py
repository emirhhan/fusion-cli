"""Oturuma bağlı terminal/geliştirme süreçleri ve sınırlı çıktı tamponları."""

from __future__ import annotations

import asyncio
import contextlib
import os
import platform
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def _process_group_kwargs() -> dict[str, Any]:
    """Alt süreci kendi grubunda başlatan platforma özgü argümanlar.

    Grup şart: `npm run dev` gibi komutlar kendi çocuklarını doğurur ve yalnız
    kabuğu öldürmek onları öksüz bırakır. POSIX'te yeni oturum, Windows'ta yeni
    süreç grubu bayrağı kullanılır.
    """
    if platform.system().casefold() == "windows":
        # Sabit yalnız Windows'ta tanımlıdır; macOS'ta mypy/çalışma zamanı
        # görmez. Değeri Windows API'sinden gelir ve değişmez.
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)}
    return {"start_new_session": True}


def terminate_process_tree(pid: int, *, force: bool) -> None:
    """Süreci ve doğurduğu çocukları sonlandır.

    POSIX'te süreç grubuna sinyal gönderilir. Windows'ta `os.killpg` YOKTUR;
    orada ağacı `taskkill /T` sonlandırır. Eskiden bu ayrım yoktu ve Windows'ta
    `AttributeError` `close()` içindeki `return_exceptions=True` tarafından
    yutuluyordu: süreçler öksüz kalıyor, kimseye söylenmiyordu.
    """
    if platform.system().casefold() == "windows":
        flags = ["/F"] if force else []
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", *flags],
                capture_output=True,
                check=False,
                timeout=10,
            )
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)


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
        await asyncio.gather(
            *(self._stop_record(record) for record in tuple(self._records.values())),
            return_exceptions=True,
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
        record.exit_code = code
        if record.status == "calisiyor":
            record.status = "bitti" if code == 0 else "hata"
        self._event("ProcessStatus", record, durum=record.status, cikis_kodu=code)

    async def _stop_record(self, record: ManagedProcess) -> None:
        if record.process.returncode is None:
            record.status = "durduruldu"
            terminate_process_tree(record.process.pid, force=False)
            try:
                await asyncio.wait_for(record.process.wait(), timeout=1.5)
            except TimeoutError:
                terminate_process_tree(record.process.pid, force=True)
                await record.process.wait()
        record.exit_code = record.process.returncode
        if record.pump is not None and record.pump is not asyncio.current_task():
            await asyncio.gather(record.pump, return_exceptions=True)

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
