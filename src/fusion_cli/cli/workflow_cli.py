"""`fusion workflows` — kayıtlı iş akışlarını ve koşularını terminalden yönet (P-062).

REPL'deki `/workflows` ile aynı depo ve aynı metin biçimleri kullanılır. Koşturma ajan
turu gerektirdiği için burada yok: REPL'de ya da masaüstünde `/workflows <ad>`. İptal
işareti dosya olduğundan koşu başka bir terminaldeyken de verilebilir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from ..engines.agent.workflow_tools import workflow_store
from .repl.workflow_commands import overview, show

app = typer.Typer(no_args_is_help=False, help="Kayıtlı iş akışları ve koşuları (P-062).")
console = Console()

RootOption = Annotated[
    Path, typer.Option("--kok", help="Proje kökü (varsayılan: bulunulan dizin).")
]


@app.callback(invoke_without_command=True)
def _default(context: typer.Context, kok: RootOption = Path()) -> None:
    if context.invoked_subcommand is None:
        console.print(overview(workflow_store(kok.resolve())), markup=False)


@app.command("liste")
def list_workflows(kok: RootOption = Path()) -> None:
    """Kayıtlı tanımları ve son koşuları listele."""
    console.print(overview(workflow_store(kok.resolve())), markup=False)


@app.command("goster")
def show_workflow(hedef: str, kok: RootOption = Path()) -> None:
    """Bir tanımın JSON'unu ya da bir koşunun düğümlerini göster."""
    console.print(show(workflow_store(kok.resolve()), hedef), markup=False)


@app.command("iptal")
def cancel_run(kosu: str, kok: RootOption = Path()) -> None:
    """Koşan iş akışına iptal işareti bırak."""
    if not workflow_store(kok.resolve()).request_cancel(kosu):
        console.print(f"Koşan bir '{kosu}' koşusu yok.", markup=False)
        raise typer.Exit(1)
    console.print(f"İptal işareti bırakıldı: {kosu}", markup=False)


@app.command("sil")
def delete_workflow(ad: str, kok: RootOption = Path()) -> None:
    """Kayıtlı bir iş akışı tanımını sil."""
    removed = workflow_store(kok.resolve()).delete(ad)
    if removed is None:
        console.print(f"'{ad}' adlı kayıtlı iş akışı yok.", markup=False)
        raise typer.Exit(1)
    console.print(f"Silindi: {removed}", markup=False)
