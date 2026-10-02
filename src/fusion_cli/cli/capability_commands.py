"""`fusion yetenek` — GitHub repolarını yetenek (skill/ajan) olarak kur ve yönet."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from ..config.paths import capabilities_dir, trash_dir
from ..tools.capability_install import CapabilityInstallError, install, installed, summary
from ..tools.safe_delete import DeleteRefusedError, move_to_trash

app = typer.Typer(no_args_is_help=True, help="GitHub repolarını yetenek olarak kur ve yönet.")
console = Console()


@app.command("kur")
def add(url: str = typer.Argument(..., help="https://github.com/sahip/repo")) -> None:
    """Repoyu sığ klonla, commit'e sabitle; betik çalıştırmaz."""
    try:
        console.print(summary(install(url, capabilities_dir())))
    except CapabilityInstallError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error


@app.command("liste")
def show() -> None:
    """Kurulu yetenek repoları."""
    items = installed(capabilities_dir())
    if not items:
        console.print("Kurulu yetenek yok. Örnek: fusion yetenek kur https://github.com/sahip/repo")
    for item in items:
        console.print(summary(item))


@app.command("kaldir")
def remove(name: str = typer.Argument(..., help="`fusion yetenek liste` adı")) -> None:
    """Yeteneği kaldır (Fusion çöpüne taşınır, `fusion cop geri-al` ile döner)."""
    root = capabilities_dir()
    if not (root / name).is_dir():
        console.print(f"[red]Kurulu değil: {name}[/red]")
        raise typer.Exit(1)
    try:
        move_to_trash((name,), cwd=root, root=root, home=Path.home(), trash_root=trash_dir())
    except DeleteRefusedError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"Kaldırıldı (çöpte): {name}")
