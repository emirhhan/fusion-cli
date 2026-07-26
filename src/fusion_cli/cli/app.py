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
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .. import __version__
from ..config.keys import detect
from ..config.loader import load_config
from ..config.models import Config
from ..core.errors import FusionError
from ..core.tools import ToolContext
from ..core.types import ModelSpec, VerdictSource
from ..engines.agent.approval import ApprovalMode
from ..ui import messages, theme
from ..ui.renderer import ConsoleRenderer
from ..ui.tables import cost_summary
from . import knowledge_commands, memory_commands
from .prompter import ConsolePrompter
from .repl import run_repl
from .session import Observers, build_observers, open_memory, run_agent_task, run_task
from .setup_command import run_setup

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    help="Ücretsiz LLM'lerle çalışan agentic CLI. Argümansız çalıştırılırsa REPL açılır.",
)
config_app = typer.Typer(no_args_is_help=True, help="Yapılandırmayı görüntüle.")
app.add_typer(config_app, name="config")
app.add_typer(memory_commands.app, name="memory")
app.add_typer(knowledge_commands.app, name="knowledge")

console = Console()


#: Yapılandırmadaki `task_model_map` ile aynı anahtarlar.
TASK_TYPES = ("general", "code", "reasoning", "agent")


@app.callback()
def main_callback(ctx: typer.Context) -> None:
    """Argümansız çağrıldığında interaktif oturumu başlat."""
    if ctx.invoked_subcommand is not None:
        return
    config = load_config()
    if not detect().any_configured:
        # Anahtarsız açılışta REPL'i başlatmak, kullanıcıyı her turda "hiçbir model
        # yanıt veremedi" hatasına sürüklerdi. Eksik olan şey söylenir.
        console.print(f"[{theme.WARN}]{messages.SETUP_NO_KEYS}[/{theme.WARN}]")
        raise typer.Exit(1)
    root = Path.cwd()
    raise typer.Exit(
        asyncio.run(
            run_repl(
                config,
                memory=open_memory(config, root=root),
                root=root,
                console=console,
            )
        )
    )


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
    no_memory: bool = typer.Option(
        False, "--no-memory", help="Belleği kullanma ve yazma (öğrenme kapalı)."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Olayları satır satır JSON olarak yaz (betikler için)."
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
    renderer = ConsoleRenderer(
        console, show_progress=not quiet, show_all_answers=show_all, show_call_details=True
    )
    observers = build_observers(task, renderer=renderer, as_json=as_json)
    result = asyncio.run(
        run_task(
            task,
            config,
            sinks=observers.sinks,
            task_type=task_type,
            synthesis=False if no_synthesis else None,
            memory=open_memory(config, root=Path.cwd(), enabled=not no_memory),
        )
    )
    observers.finish()
    _print_usage(observers, quiet=quiet or as_json)
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
    no_memory: bool = typer.Option(
        False, "--no-memory", help="Belleği kullanma ve yazma (ders çıkarımı kapalı)."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Olayları satır satır JSON olarak yaz (betikler için)."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="İlerleme satırlarını gizle."),
    add_dir: Annotated[
        list[Path] | None,
        typer.Option(
            "--add-dir",
            help="Proje kökünün YANINDA erişime açılacak dizin. Birden çok kez verilebilir.",
        ),
    ] = None,
) -> None:
    """Görevi araçlarla çalıştır: dosya oku/yaz, komut çalıştır, web'de ara."""
    if not task.strip():
        raise typer.BadParameter(messages.RUN_EMPTY_TASK)
    approval = _parse_mode(mode)

    config = load_config()
    root = Path.cwd()
    renderer = ConsoleRenderer(console, show_progress=not quiet)
    observers = build_observers(task, renderer=renderer, as_json=as_json)

    outcome = asyncio.run(
        run_agent_task(
            task,
            config,
            sinks=observers.sinks,
            prompter_factory=lambda flush: ConsolePrompter(
                console, ToolContext(root=root, extra_roots=tuple(add_dir or ())), flush=flush
            ),
            mode=approval,
            root=root,
            memory=open_memory(config, root=root, enabled=not no_memory),
            extra_roots=tuple(add_dir or ()),
        )
    )
    observers.finish()
    _print_usage(observers, quiet=quiet or as_json)
    if not outcome.final_text.strip():
        raise typer.Exit(1)


def _parse_mode(raw: str) -> ApprovalMode:
    try:
        return ApprovalMode(raw.strip().lower())
    except ValueError:
        valid = ", ".join(item.value for item in ApprovalMode)
        raise typer.BadParameter(messages.RUN_UNKNOWN_MODE.format(given=raw, valid=valid)) from None


@app.command()
def models(
    fetch: bool = typer.Option(
        False, "--fetch", help="Sağlayıcıların CANLI kataloğundan kullanılabilir modelleri listele."
    ),
) -> None:
    """Yapılandırılmış modelleri, `--fetch` ile canlı katalogları göster."""
    if not fetch:
        _print_configured_models(load_config())
        return
    load_config()  # .env yüklenir; NIM anahtarı katalog için gerekir
    _print_catalog()


@app.command()
def feedback(
    task_type: str = typer.Argument(..., help="Görev tipi (general | code | reasoning | agent)."),
    model: str = typer.Argument(..., help="Geri bildirim verilecek aday adı."),
    verdict: str = typer.Argument(..., help="good | bad | revise"),
) -> None:
    """Bir modelin son sonucuna geri bildirim ver; bellek buna göre öğrenir."""
    memory_commands.feedback(task_type, model, verdict)


@app.command()
def setup() -> None:
    """İlk kurulum: kullanıcı dizinine config.yaml ve .env şablonu bırak."""
    run_setup(console)


@app.command()
def stats() -> None:
    """Model performans tablosu (`fusion memory stats` ile aynı)."""
    memory_commands.show_stats()


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


def _print_usage(observers: Observers, *, quiet: bool) -> None:
    """Tur sonunda token/maliyet özetini ve izleme durumunu göster."""
    if quiet or not observers.cost.calls:
        return
    console.print(f"[{theme.DIM}]{cost_summary(observers.cost)}[/{theme.DIM}]")


def _print_configured_models(config: Config) -> None:
    table = Table(title=messages.CONFIG_HEADING_CANDIDATES)
    table.add_column("Rol", style="bold")
    table.add_column("Ad", style=theme.ACCENT)
    table.add_column("Model", style=theme.DIM)
    for candidate in config.candidates:
        table.add_row("aday", candidate.name, candidate.model)
    table.add_row("hakem", config.judge.name, config.judge.model)
    table.add_row("agent", config.agent.name, config.agent.model)
    console.print(table)


def _print_catalog() -> None:
    """Canlı katalogları listele. Ağ yoksa boş liste döner, komut çökmez."""
    from ..providers.catalog import fetch_nim, fetch_openrouter_free

    for title, entries in (
        (messages.CATALOG_OPENROUTER, fetch_openrouter_free()),
        (messages.CATALOG_NIM, fetch_nim()),
    ):
        if not entries:
            console.print(f"[{theme.DIM}]{title}: {messages.CATALOG_EMPTY}[/{theme.DIM}]")
            continue
        console.print(f"\n[bold]{title}[/bold] [{theme.DIM}]({len(entries)})[/{theme.DIM}]")
        for entry in entries:
            suffix = (
                f"  [{theme.DIM}]{entry.context_length:,} token[/{theme.DIM}]"
                if entry.context_length
                else ""
            )
            console.print(f"  [{theme.ACCENT}]{entry.model_id}[/{theme.ACCENT}]{suffix}")


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
