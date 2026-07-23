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
from pathlib import Path

import typer
from rich.console import Console

from .. import __version__
from ..config.loader import load_config
from ..config.models import Config
from ..core.errors import FusionError
from ..core.tools import ToolContext
from ..core.types import ModelSpec, VerdictSource
from ..engines.agent.approval import ApprovalMode
from ..ui import messages, theme
from ..ui.renderer import ConsoleRenderer
from .prompter import ConsolePrompter
from .session import run_agent_task, run_task

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Ücretsiz LLM'lerle çalışan agentic CLI.",
)
config_app = typer.Typer(no_args_is_help=True, help="Yapılandırmayı görüntüle.")
app.add_typer(config_app, name="config")

console = Console()


#: Yapılandırmadaki `task_model_map` ile aynı anahtarlar.
TASK_TYPES = ("general", "code", "reasoning", "agent")


@app.command()
def run(
    task: str = typer.Argument(..., help="Modellere verilecek görev ya da soru."),
    task_type: str = typer.Option(
        "general", "--type", "-t", help=f"Görev tipi: {' | '.join(TASK_TYPES)}"
    ),
    show_all: bool = typer.Option(False, "--all", help="Tüm aday cevaplarını göster."),
    no_synthesis: bool = typer.Option(
        False, "--no-synthesis", help="Sentezi kapat; hakemin seçtiği cevabı göster."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="İlerleme satırlarını gizle."),
) -> None:
    """Görevi tüm adaylara paralel sor, hakem ve sentezle en iyi cevabı üret."""
    if not task.strip():
        raise typer.BadParameter(messages.RUN_EMPTY_TASK)
    if task_type not in TASK_TYPES:
        raise typer.BadParameter(
            messages.RUN_UNKNOWN_TASK_TYPE.format(given=task_type, valid=", ".join(TASK_TYPES))
        )

    config = load_config()
    renderer = ConsoleRenderer(console, show_progress=not quiet, show_all_answers=show_all)
    result = asyncio.run(
        run_task(
            task,
            config,
            sinks=(renderer,),
            task_type=task_type,
            synthesis=False if no_synthesis else None,
        )
    )
    if result.source is VerdictSource.NONE:
        raise typer.Exit(1)


@app.command()
def agent(
    task: str = typer.Argument(..., help="Agent'a verilecek görev."),
    mode: str = typer.Option(
        "auto",
        "--mode",
        "-m",
        help="Onay modu: auto (otomatik, yıkıcı komutta sorar) | "
        "plan (yalnız planla) | security (her değişikliği sor)",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="İlerleme satırlarını gizle."),
) -> None:
    """Görevi araçlarla çalıştır: dosya oku/yaz, komut çalıştır, web'de ara."""
    if not task.strip():
        raise typer.BadParameter(messages.RUN_EMPTY_TASK)
    approval = _parse_mode(mode)

    config = load_config()
    root = Path.cwd()
    renderer = ConsoleRenderer(console, show_progress=not quiet)

    outcome = asyncio.run(
        run_agent_task(
            task,
            config,
            sinks=(renderer,),
            prompter_factory=lambda flush: ConsolePrompter(
                console, ToolContext(root=root), flush=flush
            ),
            mode=approval,
            root=root,
        )
    )
    if not outcome.final_text.strip():
        raise typer.Exit(1)


def _parse_mode(raw: str) -> ApprovalMode:
    try:
        return ApprovalMode(raw.strip().lower())
    except ValueError:
        valid = ", ".join(item.value for item in ApprovalMode)
        raise typer.BadParameter(messages.RUN_UNKNOWN_MODE.format(given=raw, valid=valid)) from None


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

    console.print(f"[bold]{messages.CONFIG_HEADING_CANDIDATES}[/bold]")
    for candidate in config.candidates:
        _print_spec(candidate)
    console.print(f"\n[bold]{messages.CONFIG_HEADING_JUDGE}[/bold]")
    _print_spec(config.judge)
    console.print(f"\n[bold]{messages.CONFIG_HEADING_AGENT}[/bold]")
    _print_spec(config.agent)

    console.print(f"\n[bold]{messages.CONFIG_HEADING_RUNTIME}[/bold]")
    for field in fields(config.runtime):
        value = getattr(config.runtime, field.name)
        console.print(f"  [{theme.DIM}]{field.name}:[/{theme.DIM}] {value}")


def _print_spec(spec: ModelSpec) -> None:
    tags = f" [{theme.DIM}]({', '.join(spec.tags)})[/{theme.DIM}]" if spec.tags else ""
    console.print(f"  {spec.name}: [{theme.ACCENT}]{spec.model}[/{theme.ACCENT}]{tags}")
    if spec.fallback:
        for fallback in spec.fallback:
            console.print(f"    [{theme.DIM}]yedek: {fallback}[/{theme.DIM}]")
    else:
        console.print(f"    [{theme.DIM}]{messages.CONFIG_FALLBACK_NONE}[/{theme.DIM}]")


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
