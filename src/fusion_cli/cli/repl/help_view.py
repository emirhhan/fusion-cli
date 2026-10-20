"""Kendi çıktısını basan komutlar: yardım, tablolar, ekran temizleme.

Bunlar tek satırlık bir sonuç döndürmez; tablo ya da panel basar. Bu yüzden komut
işleyicilerinden ayrı tutulur — işleyiciler saf kalır, basma işi buradadır.
"""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ...core.types import ModelSpec
from ...ui import banner, messages, theme
from ...ui.tables import cost_summary, cost_table
from ..memory_commands import lessons_table, stats_table
from .commands import CommandRegistry
from .state import ReplState

#: `/help` komut sütununun hizalama tavanı; uzun bir takma ad tabloyu şişirmesin.
HELP_COMMAND_MAX_WIDTH = 18


async def render(name: str, state: ReplState, registry: CommandRegistry, console: Console) -> None:
    """Kendi çıktısını basan komutu çalıştır."""
    if name == "help":
        _help(registry, console)
    elif name == "tips":
        _tips(console)
    elif name == "clear":
        from .loop import session_info

        banner.print_welcome(console, session_info(state))
    elif name == "stats":
        _stats(state, console)
    elif name == "lessons":
        _lessons(state, console)
    elif name == "models":
        _models(state, console)
    elif name == "cost":
        _cost(state, console)
    elif name == "compact":
        from .loop import compact_history

        console.print(f"[{theme.DIM}]{await compact_history(state)}[/{theme.DIM}]")


def _tips(console: Console) -> None:
    """`/tips` — komutları GÖREV EKSENİNDE anlat.

    `/help` komutları listeler; bu ekran ne zaman hangisine uzanılacağını söyler.
    İkisi farklı sorulardır ve tek tabloda birleştirilmeleri ikisini de bozardı:
    liste referanstır, bu rehberdir.
    """
    console.print()
    console.print(
        f"[bold {theme.ACCENT}]{messages.TIPS_TITLE}[/bold {theme.ACCENT}]", highlight=False
    )
    console.print(f"[{theme.DIM}]{messages.TIPS_INTRO}[/{theme.DIM}]", highlight=False)

    for baslik, satirlar in messages.TIPS_SECTIONS:
        console.print()
        console.print(f"[bold]{baslik}[/bold]", highlight=False)
        for komut, aciklama in satirlar:
            if not komut:
                # Bölümün kapanış cümlesi: komut değil, karar kuralı.
                console.print(f"    [{theme.DIM}]→ {aciklama}[/{theme.DIM}]", highlight=False)
                continue
            pad = " " * max(0, 16 - len(komut))
            console.print(
                f"  [bold {theme.ACCENT}]{komut}[/bold {theme.ACCENT}]{pad}  {aciklama}",
                highlight=False,
            )
    console.print()


def _help(registry: CommandRegistry, console: Console) -> None:
    """`/help` — komutları GRUP GRUP, hizalı ve sade bir dizilimde göster.

    Eskiden tek geniş tabloydu; grup adı her satırda tekrarlanıyor ya da boş kalıyordu.
    Artık her grup kendi başlığı altında toplanır (welcome/tips ile aynı estetik):
    başlık aksan renginde, komutlar hizalı, açıklamalar sönük.
    """
    console.print()
    console.print(f"[bold {theme.ACCENT}]{messages.REPL_HELP_TITLE}[/bold {theme.ACCENT}]")

    grouped: dict[str, list[tuple[str, str]]] = {}
    order: list[str] = []
    for command in registry.all():
        group = command.group or messages.HELP_GROUP_OTHER
        if group not in grouped:
            grouped[group] = []
            order.append(group)
        grouped[group].append((command.display, command.summary))

    width = _command_width(grouped)
    for group in order:
        console.print()
        console.print(f"[bold]{group}[/bold]", highlight=False)
        for display, summary in grouped[group]:
            # Dolgu markup DIŞINDA: hizalama boşlukları aksan rengine boyanmasın.
            # highlight=False: açıklamadaki parantezleri Rich repr sanıp boyamasın.
            # escape: `[alt-komut]`, `[arama]`, `[incompatible]` kullanıcıya
            # gösterilecek METİNDİR; kaçırılmazsa Rich onları stil etiketi sanıp
            # sessizce yutar ve komut argümansızmış gibi görünür.
            pad = " " * max(0, width - len(display))
            console.print(
                f"  [bold {theme.ACCENT}]{escape(display)}[/bold {theme.ACCENT}]{pad}  "
                f"[{theme.DIM}]{escape(summary)}[/{theme.DIM}]",
                highlight=False,
            )
    console.print()
    console.print(f"[{theme.DIM}]{messages.REPL_ON_OFF_HINT}[/{theme.DIM}]", highlight=False)


def _command_width(grouped: dict[str, list[tuple[str, str]]]) -> int:
    """En uzun komut adına göre hizalama genişliği (dar ekranı taşırmayacak bir tavanla)."""
    longest = max((len(display) for rows in grouped.values() for display, _ in rows), default=0)
    return min(longest, HELP_COMMAND_MAX_WIDTH)


def _stats(state: ReplState, console: Console) -> None:
    rows = state.memory.performance.stats()
    if not rows:
        console.print(f"[{theme.DIM}]{messages.MEMORY_EMPTY_STATS}[/{theme.DIM}]")
        return
    console.print(stats_table(rows))


def _lessons(state: ReplState, console: Console) -> None:
    lessons = state.memory.lessons.all()
    if not lessons:
        console.print(f"[{theme.DIM}]{messages.MEMORY_EMPTY_LESSONS}[/{theme.DIM}]")
        return
    console.print(lessons_table(lessons))


def _cost(state: ReplState, console: Console) -> None:
    if not state.cost.calls:
        console.print(f"[{theme.DIM}]{messages.COST_EMPTY}[/{theme.DIM}]")
        return
    console.print(cost_table(state.cost))
    console.print(f"[{theme.DIM}]{cost_summary(state.cost)}[/{theme.DIM}]")
    if state.cost.total.cost_usd == 0:
        console.print(f"[{theme.DIM}]{messages.COST_FREE_NOTE}[/{theme.DIM}]")


def _models(state: ReplState, console: Console) -> None:
    table = Table(title=messages.CONFIG_HEADING_CANDIDATES)
    table.add_column("Rol", style="bold")
    table.add_column("Ad", style=theme.ACCENT)
    table.add_column("Model", style=theme.DIM)

    for candidate in state.config.candidates:
        table.add_row("aday", candidate.name, _model_line(candidate))
    table.add_row("hakem", state.config.judge.name, _model_line(state.config.judge))
    table.add_row("agent", state.config.agent.name, _model_line(state.config.agent))
    console.print(table)


def _model_line(spec: ModelSpec) -> str:
    if not spec.fallback:
        return spec.model
    return f"{spec.model}  (+{len(spec.fallback)} yedek)"
