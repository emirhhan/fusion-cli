"""`monitor`: arka planda komut çalıştır, her çıktı satırını tura olay olarak ver (#336).

Claude Code Monitor (code.claude.com/docs/en/tools-reference): `description` ve `timeout_ms`
(varsayılan 5 dk, 1 saate kadar kabul, etkin tavan 30 dk) alır; `command` her stdout satırını
olaya çevirir. Süre dolunca Claude bir kez haber alır ve gerekirse yeni izleme başlatır.
Komut Bash ile aynı izin kurallarından geçer: araç kabuk ailesindedir (`ToolFamily.SHELL`),
onay ve sandbox `run_shell` ile aynı yoldan işler (`start_background`). Kimlik `task_stop`
ile erken durdurulur.

Satırlar oturumun olay kuyruğuna (`BackgroundEvents`) girer: tur sürerken sıradaki model
isteğine, oturum boştayken yeni bir tura. Olay metni komut çıktısıdır, kullanıcı talimatı
sayılmaz (harness notu etiketi).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from ..core.background_events import BackgroundEvents
from ..core.tools import Tool, ToolArgs, ToolContext, ToolResult
from .bash_settings import background_disabled
from .job_notify import events_of

__all__ = ["DEFAULT_TIMEOUT_MS", "EFFECTIVE_MAX_TIMEOUT_MS", "MONITOR_TOOL", "monitor"]

DEFAULT_TIMEOUT_MS = 300_000
#: Şemanın kabul ettiği en büyük değer (1 sa); etkin süre 30 dk'ya kısaltılır.
ACCEPTED_MAX_TIMEOUT_MS = 3_600_000
EFFECTIVE_MAX_TIMEOUT_MS = 1_800_000
#: Günlük dosyasının yoklanma aralığı (saniye).
_POLL_S = 0.2


def _timeout_ms(args: ToolArgs) -> int | ToolResult:
    raw = args.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if raw is None:
        return DEFAULT_TIMEOUT_MS
    if isinstance(raw, bool) or not isinstance(raw, int | float) or raw <= 0:
        return ToolResult.failure("'timeout_ms' pozitif bir sayı (ms) olmalı.")
    if raw > ACCEPTED_MAX_TIMEOUT_MS:
        return ToolResult.failure("'timeout_ms' en çok 3600000 (1 saat) olabilir.")
    return min(int(raw), EFFECTIVE_MAX_TIMEOUT_MS)


def monitor(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Komutu arka planda başlat; satırları olay kuyruğuna akıt."""
    from .shell import start_background

    if background_disabled():
        return ToolResult.failure(
            "Arka plan görevleri kapalı (CLAUDE_CODE_DISABLE_BACKGROUND_TASKS); monitor çalışmaz."
        )
    events = events_of(context)
    if events is None:
        return ToolResult.failure(
            "Bu oturumda olay kanalı yok (tek atışlık koşu); run_shell run_in_background kullan."
        )
    command = args.get("command")
    if args.get("ws"):
        return ToolResult.failure("WebSocket (ws) kaynağı henüz desteklenmiyor; command ver.")
    if not isinstance(command, str) or not command.strip():
        return ToolResult.failure("'command' alanı gerekli (her stdout satırı bir olaydır).")
    timeout = _timeout_ms(args)
    if isinstance(timeout, ToolResult):
        return timeout
    description = args.get("description")
    label = description.strip() if isinstance(description, str) and description.strip() else ""
    started = start_background(command, {"command": command}, context, notify=False)
    data = started.structured or {}
    job_id, log = data.get("task_id"), data.get("output_file")
    if not started.ok or not isinstance(job_id, str) or not isinstance(log, str):
        return started
    _Watch(events, context, job_id, Path(log), label or command, timeout).start()
    return ToolResult(
        f"İzleme başladı: {job_id} (süre {timeout // 1000} sn). Her çıktı satırı bildirim olarak "
        f"gelir; beklemek için turu bitirebilirsin. Erken bitirmek için task_stop(task_id="
        f"'{job_id}').",
        structured={"taskId": job_id, "timeoutMs": timeout, "persistent": False},
        is_observation=True,
    )


class _Watch(threading.Thread):
    """Günlüğün yeni satırlarını olaya çevirir; iş biter ya da süre dolarsa durur."""

    def __init__(
        self,
        events: BackgroundEvents,
        context: ToolContext,
        job_id: str,
        log: Path,
        label: str,
        timeout_ms: int,
    ) -> None:
        super().__init__(name=f"fusion-monitor-{job_id}", daemon=True)
        self._events, self._context, self._job_id = events, context, job_id
        self._log, self._label = log, " ".join(label.split())[:80]
        self._deadline = time.monotonic() + timeout_ms / 1000

    def _exit_path(self) -> Path:
        return self._log.with_suffix(".exit")

    def run(self) -> None:
        offset, buffer = 0, b""
        while True:
            finished = self._exit_path().exists()
            offset, buffer = self._pump(offset, buffer)
            if finished:
                self._flush(buffer)
                self._events.push(f"[monitor {self._job_id} · {self._label}] izleme bitti.")
                return
            if time.monotonic() >= self._deadline:
                self._flush(buffer)
                self._expire()
                return
            time.sleep(_POLL_S)

    def _pump(self, offset: int, buffer: bytes) -> tuple[int, bytes]:
        try:
            with self._log.open("rb") as stream:
                stream.seek(offset)
                chunk = stream.read()
        except OSError:
            return offset, buffer
        if not chunk:
            return offset, buffer
        data = buffer + chunk
        *lines, rest = data.split(b"\n")
        for line in lines:
            self._emit(line)
        return offset + len(chunk), rest

    def _flush(self, buffer: bytes) -> None:
        if buffer.strip():
            self._emit(buffer)

    def _emit(self, raw: bytes) -> None:
        text = raw.decode("utf-8", errors="replace").rstrip("\r")
        if text.strip():
            self._events.push(f"[monitor {self._job_id} · {self._label}] {text}")

    def _expire(self) -> None:
        from .task_stop import task_stop

        task_stop({"task_id": self._job_id}, self._context)
        self._events.push(
            f"[monitor {self._job_id} · {self._label}] süre doldu, izleme durduruldu; "
            "gerekirse yeni bir izleme başlat."
        )


MONITOR_TOOL = Tool(
    name="monitor",
    description="Komutu arka planda çalıştır; her çıktı satırı sana bildirim olarak gelir.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "description": {"type": "string"},
            "timeout_ms": {"type": "integer"},
        },
        "required": ["command", "description"],
    },
    run=monitor,
    mutating=True,
)
