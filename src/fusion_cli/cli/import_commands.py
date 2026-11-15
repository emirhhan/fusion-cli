"""`fusion import <kaynak>` ve `fusion release-notes` (P-071)."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from .. import __version__
from ..config.importers import apply_plan, build_plan, default_secrets, source_names
from ..config.loader import load_config
from ..config.release_notes import release_notes_text
from ..core.errors import ConfigError
from .import_view import format_plan, format_report

console = Console()

CONFIRM = "Önizlenen öğeler Fusion'a eklensin mi?"
NEEDS_YES = "Terminal etkileşimli değil; uygulamak için --yes ekle."
CANCELLED = "Vazgeçildi; hiçbir şey yazılmadı."
INSTALLED_VERSION = "Kurulu sürüm: {version}"


def import_config(
    source: str = typer.Argument(..., help=f"Kaynak: {' | '.join(source_names())}"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Yalnız önizle, hiçbir şey yazma."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Sormadan uygula."),
) -> None:
    """Claude Code / Codex / Gemini CLI / Cursor yapılandırmasını (MCP, izin, komut, kural) taşı.

    Örnek: fusion import codex --dry-run · fusion import cursor --yes
    """
    config = load_config()
    root = Path.cwd()
    try:
        plan = build_plan(source, home=Path.home(), root=root, config=config)
    except ConfigError as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(1) from error
    console.print(escape(format_plan(plan)))
    if dry_run or not plan.pending:
        return
    if not yes:
        if not sys.stdin.isatty():
            console.print(NEEDS_YES)
            return
        if not typer.confirm(CONFIRM, default=False):
            console.print(CANCELLED)
            return
    _config, report = apply_plan(plan, config=config, root=root, secrets=default_secrets())
    console.print(escape(format_report(report)))
    if report.failed:
        raise typer.Exit(1)


def release_notes(
    version: str = typer.Argument("", help="Sürüm (ör. 0.7.18), 'liste' ya da boş (en yeni)."),
) -> None:
    """CHANGELOG'dan sürüm notlarını göster (Claude Code `/release-notes`)."""
    console.print(INSTALLED_VERSION.format(version=__version__))
    console.print(escape(release_notes_text(version)))
