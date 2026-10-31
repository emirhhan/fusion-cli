"""Özelleştirilebilir durum satırı (P-069): `/statusline` ve `runtime.status_line_command`.

Claude Code `statusLine.command` sözleşmesi örnek alınmıştır: komut her tur sonunda
çalıştırılır, stdin'den tek bir JSON nesnesi alır ve bastığı İLK satır durum çubuğunda
gösterilir. JSON alanları `/status` ve `/context` verisinden gelir:

    {"model": {"id": ..., "name": ..., "tier": ...},
     "workspace": {"current_dir": ..., "project_dir": ..., "extra_dirs": [...]},
     "cost": {"total_cost_usd": ..., "total_tokens": ..., "calls": ...},
     "context_window": {"percent": ..., "used_tokens": ..., "limit_tokens": ...,
                        "window_tokens": ...},
     "session": {"id": ..., "engine": ..., "approval_mode": ..., "output_style": ...},
     "version": ...}

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
from .status_view import context_report

_LOG = logging.getLogger(__name__)

#: Komuta tanınan süre (saniye); durum çubuğu kullanıcıyı bekletemez.
STATUS_LINE_TIMEOUT_S = 1.0
#: Durum satırının en fazla uzunluğu; uzunu kırpılır (tek satır kalmalı).
STATUS_LINE_MAX_CHARS = 160
#: Kalıcı ayar yolu.
SETTING_PATH = "runtime.status_line_command"


def status_payload(state: ReplState) -> dict[str, Any]:
    """Betiğe stdin'den verilecek JSON; `/status` ve `/context` ile aynı kaynaklar."""
    from ... import __version__

    report = context_report(state)
    tier = next(
        (item.name for item in state.config.tiers if item.agent.model == state.config.agent.model),
        "",
    )
    total = state.cost.total
    return {
        "model": {"id": state.config.agent.model, "name": state.config.agent.name, "tier": tier},
        "workspace": {
            "current_dir": str(state.root),
            "project_dir": str(state.root),
            "extra_dirs": [str(path) for path in state.extra_roots],
        },
        "cost": {
            "total_cost_usd": round(total.cost_usd, 6),
            "total_tokens": total.prompt_tokens + total.completion_tokens,
            "calls": state.cost.calls,
        },
        "context_window": {
            "percent": report.percent,
            "used_tokens": report.estimated_tokens,
            "limit_tokens": report.threshold_chars // 3,
            "window_tokens": report.window_tokens,
        },
        "session": {
            "id": state.conversation_id,
            "engine": state.engine.value,
            "approval_mode": state.approval.value,
            "output_style": getattr(state.config.runtime, "output_style", "varsayilan"),
        },
        "version": __version__,
    }


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
    """Yapılandırılmış betik varsa çıktısı; yoksa boş (yerleşik çubuk kullanılır)."""
    command = str(getattr(state.config.runtime, "status_line_command", "") or "").strip()
    if not command:
        return ""
    return await asyncio.to_thread(
        run_status_line, command, status_payload(state), cwd=str(state.root)
    )


def statusline_command(state: ReplState, argument: str) -> str:
    """`/statusline [komut|kapat]` — betiği göster, ayarla ya da kaldır (kalıcı)."""
    from dataclasses import replace

    from ...config.settings_access import write_setting
    from ...core.errors import ConfigError

    wanted = argument.strip()
    current = str(getattr(state.config.runtime, "status_line_command", "") or "")
    if not wanted:
        fields = ", ".join(status_payload(state))
        return messages.STATUSLINE_CURRENT.format(command=current or "(yok)", fields=fields)
    value = "" if wanted.lower() in ("kapat", "off", "sil", "yok") else wanted
    try:
        state.config, _ = write_setting(state.config, SETTING_PATH, value)
    except ConfigError as error:
        state.config = replace(
            state.config, runtime=replace(state.config.runtime, status_line_command=value)
        )
        return messages.STATUSLINE_SET_UNSAVED.format(error=error)
    if not value:
        return messages.STATUSLINE_CLEARED
    return messages.STATUSLINE_SET.format(command=value)
