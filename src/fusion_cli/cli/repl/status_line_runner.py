"""Durum satırı betiğini Claude Code gibi tetikle (#192).

Claude Code: betik oturum başında, her asistan mesajında, `/compact` sonrasında, izin kipi
ya da vim kipi değişince ve `refreshInterval` ile çalışır; güncellemeler 300 ms debounce
edilir, yeni tetik süren betiği iptal eder, `command` değişince debounce atlanır. Çıktının
bütün satırları (ANSI renk ve OSC 8 bağlantı dahil) gösterilir; betiğe `COLUMNS`/`LINES`
verilir. Ölçüldü (1 Kasım): Fusion betiği yalnız tur sonunda, 1 sn sınırla çalıştırıp
yalnız ilk satırı (HTML kaçışlı) gösteriyordu.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
from collections.abc import Callable
from typing import Any

from .status_line_settings import StatusLineSpec

_LOG = logging.getLogger(__name__)

#: Claude Code'un debounce süresi (saniye).
DEBOUNCE_S = 0.3
#: Asılı kalan betiğin üst sınırı; yeni tetik zaten öncekini iptal eder.
HARD_TIMEOUT_S = 30.0
#: Gösterilecek çıktının üst sınırı (karakter); durum alanı ekranı kaplamasın.
MAX_OUTPUT_CHARS = 4_000


#: OSC 8 bağlantı dizisi (`ESC ] 8 ; params ; url ST`), ST = BEL ya da `ESC \\`.
_OSC8 = re.compile(r"\x1b\]8;[^\x07\x1b]*(?:\x07|\x1b\\)")


def ansi_for_tui(text: str) -> str:
    """OSC 8 dizilerini prompt_toolkit'in sıfır genişlikli kaçış işaretleriyle (`\\001…\\002`)
    sar; aksi halde `ANSI` ayrıştırıcısı bağlantıyı düz metin olarak basıyordu (ölçüldü)."""
    return _OSC8.sub(lambda match: f"\x01{match.group(0)}\x02", text)


def script_env(columns: int | None = None, lines: int | None = None) -> dict[str, str]:
    """Betik ortamı: terminal boyutu `COLUMNS`/`LINES` (betik `tput` ile okuyamaz)."""
    size = shutil.get_terminal_size()
    env = dict(os.environ)
    env["COLUMNS"] = str(columns or size.columns)
    env["LINES"] = str(lines or size.lines)
    return env


def format_output(raw: str, padding: int = 0) -> str:
    """Bütün satırlar korunur (ANSI/OSC 8 dokunulmaz); `padding` her satırın başına boşluk."""
    text = raw.rstrip("\n")[:MAX_OUTPUT_CHARS]
    if not text.strip():
        return ""
    pad = " " * max(0, padding)
    return "\n".join(f"{pad}{line}" for line in text.splitlines())


async def run_script(spec: StatusLineSpec, payload: dict[str, Any], *, cwd: str) -> str:
    """Betiği stdin JSON ile çalıştır; iptal edilirse süreç öldürülür."""
    process = await asyncio.create_subprocess_shell(
        spec.command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=cwd,
        env=script_env(),
    )
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        async with asyncio.timeout(HARD_TIMEOUT_S):
            stdout, _ = await process.communicate(data)
    except BaseException:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        with contextlib.suppress(Exception):
            await process.wait()
        raise
    if process.returncode != 0:
        _LOG.warning("durum satırı betiği hata verdi (kod %s)", process.returncode)
        return ""
    return format_output(stdout.decode("utf-8", errors="replace"), spec.padding)


class StatusLineRunner:
    """Tetikleri birleştirir (debounce), süren betiği iptal eder, sonucu geri çağırır."""

    def __init__(
        self,
        spec_source: Callable[[], StatusLineSpec | None],
        payload_source: Callable[[], dict[str, Any]],
        on_output: Callable[[str], None],
        *,
        cwd_source: Callable[[], str],
        debounce_s: float = DEBOUNCE_S,
    ) -> None:
        self._spec_source = spec_source
        self._payload_source = payload_source
        self._on_output = on_output
        self._cwd_source = cwd_source
        self._debounce_s = debounce_s
        self._task: asyncio.Task[None] | None = None
        self._timer: asyncio.Task[None] | None = None
        self._last_command = ""

    def request(self) -> None:
        """Bir güncelleme iste; süren betik iptal edilir, 300 ms sonra yenisi çalışır."""
        spec = self._spec_source()
        if spec is None:
            self._cancel()
            if self._last_command:
                self._last_command = ""
                self._on_output("")
            return
        immediate = spec.command != self._last_command
        self._last_command = spec.command
        self._cancel()
        self._task = asyncio.get_running_loop().create_task(self._run(spec, immediate))
        self._ensure_timer(spec)

    async def _run(self, spec: StatusLineSpec, immediate: bool) -> None:
        if not immediate:
            await asyncio.sleep(self._debounce_s)
        try:
            output = await run_script(spec, self._payload_source(), cwd=self._cwd_source())
        except (OSError, TimeoutError) as error:
            _LOG.warning("durum satırı betiği çalışmadı: %s", error)
            output = ""
        self._on_output(output)

    def _ensure_timer(self, spec: StatusLineSpec) -> None:
        if spec.refresh_interval_s is None or (self._timer and not self._timer.done()):
            return
        self._timer = asyncio.get_running_loop().create_task(
            self._tick(float(spec.refresh_interval_s))
        )

    async def _tick(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            spec = self._spec_source()
            if spec is None or spec.refresh_interval_s is None:
                return
            if self._task is None or self._task.done():
                self.request()

    def _cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def close(self) -> None:
        """Süren betiği ve zamanlayıcıyı durdur."""
        for task in (self._task, self._timer):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
