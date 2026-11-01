"""Özelleştirilebilir durum satırı (P-069): `/statusline` ve `runtime.status_line_command`.

Claude Code `statusLine.command` sözleşmesi örnek alınmıştır: komut her tur sonunda
çalıştırılır, stdin'den tek bir JSON nesnesi alır ve bastığı İLK satır durum çubuğunda
gösterilir. JSON şeması Claude Code'unkiyle aynıdır (`status_payload.py`, #191): `cwd`,
`session_id`, `model.{id,display_name}`, `workspace.*`, `cost.*`, `context_window.*` …;
Fusion'a özgü alanlar `fusion` anahtarı altındadır.

Komut 1 sn içinde bitmezse ya da hata verirse yerleşik çubuk gösterilir; hata loglanır.
Sır yok: JSON yalnız model adı, yollar ve sayaçlar taşır.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from typing import Any

from ...ui import messages
from .state import ReplState

_LOG = logging.getLogger(__name__)

#: Komuta tanınan süre (saniye); durum çubuğu kullanıcıyı bekletemez.
STATUS_LINE_TIMEOUT_S = 1.0
#: Durum satırının en fazla uzunluğu; uzunu kırpılır (tek satır kalmalı).
STATUS_LINE_MAX_CHARS = 160
#: Kalıcı ayar yolu.
SETTING_PATH = "runtime.status_line_command"


def status_payload(state: ReplState) -> dict[str, Any]:
    """Betiğe stdin'den verilecek JSON: Claude Code şeması (`status_payload.py`, #191)."""
    from ... import __version__
    from .status_payload import claude_status_payload

    return claude_status_payload(state, version=__version__)


def run_status_line(command: str, payload: dict[str, Any], *, cwd: str | None = None) -> str:
    """Komutu stdin JSON ile çalıştır; ilk satırı döndür, hata/zaman aşımında boş metin."""
    try:
        completed = subprocess.run(
            command,
            shell=True,
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            timeout=STATUS_LINE_TIMEOUT_S,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError) as error:
        _LOG.warning("durum satırı betiği çalışmadı: %s", error)
        return ""
    if completed.returncode != 0:
        _LOG.warning("durum satırı betiği hata verdi (kod %s)", completed.returncode)
        return ""
    first = completed.stdout.decode("utf-8", errors="replace").strip().splitlines()
    line = first[0].strip() if first else ""
    return line[:STATUS_LINE_MAX_CHARS]


async def status_line_text(state: ReplState) -> str:
    """Yapılandırılmış betik varsa İLK satırı (düz REPL alt çubuğu); yoksa boş."""
    from .status_line_settings import resolve_status_line

    spec = resolve_status_line(state.config, state.root, state.home)
    if spec is None:
        return ""
    return await asyncio.to_thread(
        run_status_line, spec.command, status_payload(state), cwd=str(state.root)
    )


def statusline_command(state: ReplState, argument: str) -> str:
    """`/statusline [istek]` — Claude Code gibi betiği modele (statusline-setup) yazdırır.

    Argümansız hâli durum satırını kabuk isteminden (PS1) kurdurur. Ayar Claude Code
    `statusLine` nesnesidir (`.claude/settings.json`); Fusion'ın eski
    `runtime.status_line_command` dizesi kullanımdan kalkmış takma ad olarak okunur.
    """
    request = argument.strip() or messages.STATUSLINE_FROM_PROMPT
    state.pending_task = messages.STATUSLINE_TASK.format(
        request=request, fields=", ".join(status_payload(state))
    )
    return messages.STATUSLINE_DELEGATED
