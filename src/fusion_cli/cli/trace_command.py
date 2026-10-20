"""`fusion trace` — bir koşunun neden düştüğünü tek komutla söyler.

Teşhis, transkript okumakla değil sayılarla başlamalı: hangi kayıp sınıfı gözlendi,
kaç araç engellendi, kaç ayrıştırma onarımı yandı, plan nerede duraklatıldı.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from ..core.trace import RunSummary, summarize_run
from ..observability.trace_store import TraceStore
from ..ui import theme

console = Console()


def render_trace(store: TraceStore, run_id: str | None, *, limit: int = 6) -> None:
    """Bir koşunun (verilmezse sonuncunun) teşhis özetini bas."""
    hedef = run_id or store.latest()
    if hedef is None:
        console.print(
            f"[{theme.DIM}]Henüz koşu kaydı yok. Bir görev çalıştırdıktan sonra tekrar dene."
            f"[/{theme.DIM}]"
        )
        return
    ozet = summarize_run(store.read(hedef))
    console.print(f"[bold]{hedef}[/bold] · {ozet.headline()}\n")
    console.print(_table(ozet))
    if ozet.pause_reason:
        console.print(f"\n[{theme.WARN}]Duraklama:[/{theme.WARN}] {ozet.pause_reason}")
    for bulgu in ozet.findings[:limit]:
        console.print(f"[{theme.DIM}]- {bulgu}[/{theme.DIM}]")


def _rows(ozet: RunSummary) -> tuple[tuple[str, str], ...]:
    return (
        ("model çağrısı", str(ozet.model_calls)),
        ("araç çağrısı", str(ozet.tool_calls)),
        ("engellenen araç", str(ozet.blocked_tools)),
        ("başarısız araç", str(ozet.failed_tools)),
        ("ayrıştırma onarımı", str(ozet.parse_repairs)),
        ("plan adımı", f"{ozet.verified_steps}/{ozet.steps} doğrulandı"),
    )


def _table(ozet: RunSummary) -> Table:
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style=theme.DIM)
    table.add_column()
    for etiket, deger in _rows(ozet):
        table.add_row(etiket, deger)
    return table


def trace_text(store: TraceStore, run_id: str | None, *, limit: int = 6) -> str:
    """`render_trace`ın düz metin hâli (slash komutu ve masaüstü için).

    `run_id` "liste" ise kayıtlı koşuları sıralar.
    """
    if run_id == "liste":
        kayitlar = store.runs()[::-1][:20]
        if not kayitlar:
            return "Henüz koşu kaydı yok."
        return "\n".join(
            f"{kayit}  {summarize_run(store.read(kayit)).headline()}" for kayit in kayitlar
        )
    hedef = run_id or store.latest()
    if hedef is None:
        return "Henüz koşu kaydı yok. Bir görev çalıştırdıktan sonra tekrar dene."
    if hedef not in store.runs():
        return f"Böyle bir koşu yok: {hedef}  (kayıtlar için /trace liste)"
    ozet = summarize_run(store.read(hedef))
    satirlar = [f"{hedef} · {ozet.headline()}", ""]
    satirlar += [f"  {etiket}: {deger}" for etiket, deger in _rows(ozet)]
    if ozet.pause_reason:
        satirlar.append(f"Duraklama: {ozet.pause_reason}")
    satirlar += [f"- {bulgu}" for bulgu in ozet.findings[:limit]]
    return "\n".join(satirlar)


def list_runs(store: TraceStore, *, limit: int = 20) -> None:
    """Kayıtlı koşuları yeniden eskiye sırala."""
    kayitlar = store.runs()[::-1][:limit]
    if not kayitlar:
        console.print(f"[{theme.DIM}]Henüz koşu kaydı yok.[/{theme.DIM}]")
        return
    for kayit in kayitlar:
        ozet = summarize_run(store.read(kayit))
        console.print(f"{kayit}  [{theme.DIM}]{ozet.headline()}[/{theme.DIM}]")
