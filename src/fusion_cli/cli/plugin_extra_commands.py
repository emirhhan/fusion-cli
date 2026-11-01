"""`fusion plugin details` ve `prune` (takma ad `autoremove`): Claude Code birebir (#380)."""

from __future__ import annotations

import typer

from ..tools.plugin_listing import details_text
from .plugin_commands import _run, app


@app.command("details")
def details(name: str = typer.Argument(..., help="Eklenti adı ya da ad@pazar")) -> None:
    """Eklentinin bileşen envanteri ve öngörülen token maliyeti."""
    _run(lambda: details_text(name))


def prune(
    scope: str = typer.Option(
        "", "--scope", "-s", help="Kapsam: user (varsayılan), project, local."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Kaldırılacakları yalnız listele."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Onay sorma (TTY yoksa gerekli)."),
) -> None:
    """Artık hiçbir eklentinin gerekmediği otomatik kurulmuş bağımlılıkları kaldır."""
    from ..core.plugins import PluginError
    from ..tools.plugin_dependencies import prune as prune_dependencies

    del scope, yes  # Fusion bağımlılıkları tek (user) depoda tutar
    try:
        typer.echo(prune_dependencies(dry_run=dry_run))
    except PluginError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


app.command("prune")(prune)
app.command("autoremove", hidden=True)(prune)
