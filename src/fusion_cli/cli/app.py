"""Typer giriş noktası.

Komut fonksiyonları ince tutulur: girdiyi çözer, oturumu çağırır, sonucu sunar.
İş mantığı burada bulunmaz (RULES.md "UI ve CLI").

Beklenen hatalar (`FusionError`) tek bir sınırda yakalanır ve kullanıcıya Türkçe,
anlaşılır bir mesajla gösterilir; stack trace kullanıcıya basılmaz.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import fields

import typer
from rich.console import Console

from .. import __version__
from ..config.loader import load_config
from ..config.models import Config
from ..core.errors import FusionError
from ..ui import messages, theme
from ..ui.renderer import ConsoleRenderer
from .session import run_task

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Ücretsiz LLM'lerle çalışan agentic CLI.",
)
config_app = typer.Typer(no_args_is_help=True, help="Yapılandırmayı görüntüle.")
app.add_typer(config_app, name="config")

console = Console()


@app.command()
def run(
    task: str = typer.Argument(..., help="Modele verilecek görev ya da soru."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="İlerleme satırlarını gizle."),
) -> None:
    """Bir görevi tek modelle çalıştır ve cevabı akıtarak göster."""
    if not task.strip():
        raise typer.BadParameter(messages.RUN_EMPTY_TASK)

    config = load_config()
    renderer = ConsoleRenderer(console, show_progress=not quiet)
    result = asyncio.run(run_task(task, config, sinks=(renderer,)))
    if not result.ok:
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Sürümü yazdır."""
    console.print(messages.VERSION.format(version=__version__))


@config_app.command("show")
def config_show() -> None:
    """Birleştirilmiş yapılandırmayı göster (varsayılanlar + kullanıcı dosyası)."""
    config = load_config()
    _print_config(config)


def _print_config(config: Config) -> None:
    source = (
        messages.CONFIG_SOURCE_FILE.format(path=config.source)
        if config.source is not None
        else messages.CONFIG_SOURCE_DEFAULTS
    )
    console.print(f"[{theme.DIM}]{source}[/{theme.DIM}]\n")

    console.print(f"[bold]{messages.CONFIG_HEADING_AGENT}[/bold]")
    console.print(f"  {config.agent.name}: [{theme.ACCENT}]{config.agent.model}[/{theme.ACCENT}]")
    if config.agent.fallback:
        for fallback in config.agent.fallback:
            console.print(f"  [{theme.DIM}]yedek: {fallback}[/{theme.DIM}]")
    else:
        console.print(f"  [{theme.DIM}]{messages.CONFIG_FALLBACK_NONE}[/{theme.DIM}]")

    console.print(f"\n[bold]{messages.CONFIG_HEADING_RUNTIME}[/bold]")
    for field in fields(config.runtime):
        value = getattr(config.runtime, field.name)
        console.print(f"  [{theme.DIM}]{field.name}:[/{theme.DIM}] {value}")


def main() -> None:
    """Konsol giriş noktası. Beklenen hataları kullanıcıya anlaşılır biçimde gösterir."""
    try:
        app()
    except FusionError as exc:
        console.print(
            f"[{theme.ERROR}]{theme.ICON_ERROR} {messages.ERROR_PREFIX}[/{theme.ERROR}] {exc}"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        console.print(f"[{theme.WARN}]{messages.ERROR_INTERRUPTED}[/{theme.WARN}]")
        sys.exit(130)
