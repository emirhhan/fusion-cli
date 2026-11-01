"""Etkileşimli açılışta `.mcp.json` sunucu onayı istemi (Claude Code gibi, #246)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from ..config import mcp_project_approval as approval
from ..config.models import McpServerConfig
from ..core.errors import ConfigError
from ..core.redaction import redact
from ..ui import mcp_messages, theme

_CHOICES = {"1": approval.CHOICE_ALL, "2": approval.CHOICE_ONE, "3": approval.CHOICE_NO}


def ask_with_console(console: Console, read: Callable[[str], str] = input) -> Callable[..., str]:
    """Sunucuyu gösterip 1/2/3 seçimini soran işlev; boş ya da geçersiz yanıt yeniden sorulur."""
    from .mcp_manage import target_text

    def _ask(server: McpServerConfig) -> str:
        console.print(f"[bold]{escape(mcp_messages.APPROVAL_TITLE.format(name=server.name))}[/bold]")
        target = redact(target_text(server))
        console.print(f"[{theme.DIM}]{escape(mcp_messages.APPROVAL_TARGET.format(target=target))}")
        console.print(f"[{theme.WARN}]{escape(mcp_messages.APPROVAL_NOTE)}[/{theme.WARN}]")
        console.print(escape(mcp_messages.APPROVAL_OPTIONS))
        while True:
            try:
                answer = read(f"{mcp_messages.APPROVAL_ASK}: ").strip()
            except EOFError:
                return approval.CHOICE_NO
            if answer in _CHOICES:
                return _CHOICES[answer]

    return _ask


def prompt_project_mcp_approvals(console: Console, root: Path | None = None) -> None:
    """Terminal etkileşimliyse bekleyen proje sunucularını sor; değilse dokunma."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return
    try:
        approval.prompt_pending(root or Path.cwd(), ask_with_console(console))
    except (ConfigError, KeyboardInterrupt) as error:
        console.print(f"[{theme.WARN}]{escape(str(error) or 'MCP onayı yarıda kaldı')}")
