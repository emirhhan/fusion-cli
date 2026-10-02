"""`fusion cop` — ajanın sildiklerini gör ve geri al.

Fusion hiçbir klasörü kalıcı silmez; `rm` komutları Fusion çöpüne taşınır
(bkz. `tools/safe_delete.py`). Bu komutlar o çöpü kullanıcıya açar.
"""

from __future__ import annotations

import datetime

import typer
from rich.console import Console
from rich.table import Table

from ..config.paths import trash_dir
from ..tools.safe_delete import TRASH_RETENTION_DAYS, DeleteRefusedError, list_trash, restore

app = typer.Typer(no_args_is_help=True, help="Fusion'ın sildiklerini listele ve geri al.")
console = Console()


@app.command("liste")
def show() -> None:
    """Çöpteki girdiler (en yeni önce)."""
    entries = list_trash(trash_dir())
    if not entries:
        console.print("Fusion çöpü boş.")
        return
    table = Table(title=f"Fusion çöpü ({TRASH_RETENTION_DAYS} gün saklanır)")
    for column in ("kimlik", "silinme", "asıl yer"):
        table.add_column(column)
    for entry in entries:
        zaman = datetime.datetime.fromtimestamp(entry.deleted_at).strftime("%d.%m.%Y %H:%M")
        table.add_row(entry.id, zaman, str(entry.original))
    console.print(table)


@app.command("geri-al")
def undo(entry_id: str = typer.Argument(..., help="`fusion cop liste` kimliği")) -> None:
    """Bir girdiyi asıl yerine geri koy (orada bir şey varsa ezmez)."""
    try:
        yer = restore(trash_dir(), entry_id)
    except DeleteRefusedError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"Geri alındı: {yer}")
