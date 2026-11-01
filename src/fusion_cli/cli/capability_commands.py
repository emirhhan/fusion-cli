"""`fusion yetenek` — GitHub repolarını yetenek (skill/ajan) olarak kur ve yönet."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from ..config.paths import capabilities_dir, trash_dir
from ..core.errors import FusionError
from ..engines.capability_proposals import CapabilityProposals, proposal_service
from ..tools.capability_install import CapabilityInstallError, install, installed, summary
from ..tools.safe_delete import DeleteRefusedError, move_to_trash

app = typer.Typer(no_args_is_help=True, help="GitHub repolarını yetenek olarak kur ve yönet.")
console = Console()


@app.command("kur")
def add(url: str = typer.Argument(..., help="https://github.com/sahip/repo")) -> None:
    """Repoyu sığ klonla, commit'e sabitle; betik çalıştırmaz."""
    try:
        console.print(escape(summary(install(url, capabilities_dir()))))
    except CapabilityInstallError as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(1) from error


@app.command("liste")
def show() -> None:
    """Kurulu yetenek repoları."""
    items = installed(capabilities_dir())
    if not items:
        console.print("Kurulu yetenek yok. Örnek: fusion yetenek kur https://github.com/sahip/repo")
    for item in items:
        console.print(escape(summary(item)))


@app.command("kaldir")
def remove(name: str = typer.Argument(..., help="`fusion yetenek liste` adı")) -> None:
    """Yeteneği kaldır (Fusion çöpüne taşınır, `fusion cop geri-al` ile döner)."""
    root = capabilities_dir()
    # `name` düz bir dizin adıdır: `../..` gibi değerler `is_dir()` denetimini geçip
    # yetenek kökünün dışını çöpe taşımayı denerdi (L1-33).
    if name in {"", ".", ".."} or "/" in name or "\\" in name or not (root / name).is_dir():
        console.print(f"[red]Kurulu değil: {escape(name)}[/red]")
        raise typer.Exit(1)
    try:
        move_to_trash((name,), cwd=root, root=root, home=Path.home(), trash_root=trash_dir())
    except DeleteRefusedError as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        raise typer.Exit(1) from error
    console.print(f"Kaldırıldı (çöpte): {escape(name)}")


def _proposal_service() -> CapabilityProposals:
    return proposal_service(Path.home(), Path.cwd())


def _present_proposal(operation: Coroutine[None, None, str]) -> None:
    try:
        console.print(escape(asyncio.run(operation)), soft_wrap=True)
    except FusionError as error:
        console.print(escape(str(error)), soft_wrap=True)
        raise typer.Exit(1) from error


@app.command("oneri-liste")
def list_proposals(split: str | None = typer.Option(None, help="Kaynak split süzgeci.")) -> None:
    """Üç bağımsız doğrulanmış koşumu olan beceri önerilerini listele."""
    _present_proposal(_proposal_service().list(source_split=split))


@app.command("oneri-goster")
def show_proposal(
    proposal_id: str = typer.Argument(..., help="Listelenen önerinin kimliği."),
    split: str | None = typer.Option(None, help="Kaynak split süzgeci."),
) -> None:
    """Öneriyi göster; beceri kurmaz veya çalıştırmaz."""
    _present_proposal(_proposal_service().show(proposal_id, source_split=split))


@app.command("oneri-uygula")
def apply_proposal(
    proposal_id: str = typer.Argument(..., help="Açıkça kurulacak önerinin kimliği."),
    parametreler: str = typer.Option("{}", help="Girdi şemasına uygun JSON nesnesi."),
    split: str | None = typer.Option(None, help="Kaynak split süzgeci."),
) -> None:
    """Öneriyi mevcut beceri keşfine kur; model veya komut çalıştırmaz."""
    _present_proposal(_proposal_service().apply(proposal_id, parametreler, source_split=split))
