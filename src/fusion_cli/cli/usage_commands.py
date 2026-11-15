"""`fusion usage` ve `fusion insights` (P-056): kalıcı kullanım günlüğünden tablo ve HTML rapor."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ..config.loader import load_config
from ..core.errors import FusionError
from ..observability.insights_html import render_insights
from ..observability.usage_log import WINDOWS, UsageLog, summarize, usage_log_path
from ..ui import messages
from ..ui.usage_view import print_usage

console = Console()

_DAYS_TO_WINDOW = {1: WINDOWS[0], 7: WINDOWS[1], 30: WINDOWS[2]}


def _window(days: int) -> tuple[str, float]:
    label, seconds = _DAYS_TO_WINDOW.get(days, (f"son {days} gün", days * 86400.0))
    return label, seconds


def usage(
    days: int = typer.Option(7, "--days", "-d", min=1, help="Kırılım penceresi (gün)."),
) -> None:
    """Kullanım: 24 saat / 7 gün / 30 gün pencereleri; model, alt ajan, MCP ve beceri kırılımı."""
    config = load_config()
    if not config.runtime.usage_log:
        console.print(messages.USAGE_LOG_DISABLED)
        return
    log = UsageLog(usage_log_path(config))
    label, seconds = _window(days)
    summary = summarize(
        log.read(), now=time.time(), session_id="", window_s=seconds, window_label=label
    )
    print_usage(console, summary, log_path=str(log.path))


def insights(
    output: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="HTML dosyasının yolu (varsayılan: bellek dizini)."),
    ] = None,
    days: int = typer.Option(30, "--days", "-d", min=1, help="Rapor penceresi (gün)."),
) -> None:
    """Tek dosya HTML kullanım raporu üret (Claude Code `/insights` karşılığı)."""
    config = load_config()
    if not config.runtime.usage_log:
        raise FusionError(messages.USAGE_INSIGHTS_DISABLED)
    log = UsageLog(usage_log_path(config))
    now = time.time()
    label, seconds = _window(days)
    records = log.read()
    summary = summarize(records, now=now, session_id="", window_s=seconds, window_label=label)
    html = render_insights(summary, records, now=now, days=days)
    target = output or (
        config.memory_dir / f"insights-{datetime.fromtimestamp(now).strftime('%Y%m%d-%H%M')}.html"
    )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
    except OSError as error:
        raise FusionError(f"Rapor yazılamadı ({target}): {error}") from error
    console.print(messages.USAGE_INSIGHTS_WRITTEN.format(path=target))
