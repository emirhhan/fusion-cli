"""`fusion ekip` — ajan ekiplerinin panolarını terminalden gör/sil (P-061).

REPL'deki `/team` ile aynı depo ve metin biçimleri. Ekibi kurmak/sürdürmek ajan turu
gerektirir: REPL'de ya da masaüstünde `/team <hedef>`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ..engines.agent.team_board import TeamStore
from .repl.team_commands import overview, show

app = typer.Typer(no_args_is_help=False, help="Ajan ekipleri: panolar ve gelen kutuları (P-061).")
console = Console()

RootOption = Annotated[
    Path, typer.Option("--kok", help="Proje kökü (varsayılan: bulunulan dizin).")
]


@app.callback(invoke_without_command=True)
def _default(context: typer.Context, kok: RootOption = Path()) -> None:
    if context.invoked_subcommand is None:
        console.print(overview(TeamStore(kok.resolve())), markup=False)


@app.command("liste")
def list_teams(kok: RootOption = Path()) -> None:
    """Ekipleri ve görev ilerlemesini listele."""
    console.print(overview(TeamStore(kok.resolve())), markup=False)


@app.command("goster")
def show_team(ad: str, kok: RootOption = Path()) -> None:
    """Bir ekibin panosunu ve lidere gelen son mesajları göster."""
    console.print(show(TeamStore(kok.resolve()), ad), markup=False)


@app.command("sil")
def delete_team(ad: str, kok: RootOption = Path()) -> None:
    """Bir ekibin panosunu ve gelen kutularını sil."""
    if not TeamStore(kok.resolve()).delete(ad):
        console.print(f"'{ad}' adlı ekip yok.", markup=False)
        raise typer.Exit(1)
    console.print(f"Silindi: {ad}", markup=False)
