"""`fusion memory` komut ailesi ve geri bildirim.

Belleğin içini görünür kılar: hangi model iyi çalışıyor, agent ne öğrendi, kod
indeksi güncel mi. Görünmeyen bir öğrenme katmanına güvenilmez.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ..config.loader import load_config
from ..core.memory import Feedback, Lesson, LessonKind, LessonSource, ModelStats
from ..memory.factory import Memory, build_memory
from ..memory.seed import SEED_LESSONS, seed
from ..ui import messages, theme

app = typer.Typer(no_args_is_help=True, help="Öğrenilen bilgiyi görüntüle ve yönet.")
console = Console()

_KIND_LABELS = {
    LessonKind.MISTAKE: (messages.LESSON_KIND_MISTAKE, theme.WARN),
    LessonKind.SUCCESS: (messages.LESSON_KIND_SUCCESS, theme.OK),
}
_SOURCE_LABELS = {
    LessonSource.SEED: messages.LESSON_SOURCE_SEED,
    LessonSource.LEARNED: messages.LESSON_SOURCE_LEARNED,
    LessonSource.MANUAL: messages.LESSON_SOURCE_MANUAL,
}


@app.command("stats")
def show_stats() -> None:
    """Model performans istatistikleri (fusion öz-öğrenmesi)."""
    memory = _open()
    rows = memory.performance.stats()
    if not rows:
        console.print(f"[{theme.DIM}]{messages.MEMORY_EMPTY_STATS}[/{theme.DIM}]")
        return
    console.print(_stats_table(rows))


@app.command("lessons")
def show_lessons() -> None:
    """Agent'ın öğrendiği dersler."""
    memory = _open()
    lessons = memory.lessons.all()
    if not lessons:
        console.print(f"[{theme.DIM}]{messages.MEMORY_EMPTY_LESSONS}[/{theme.DIM}]")
        return
    console.print(_lessons_table(lessons))


@app.command("seed")
def seed_lessons() -> None:
    """Küratörlü başlangıç derslerini yükle (tekrar çalıştırmak güvenlidir)."""
    memory = _open()
    added = seed(memory.lessons)
    console.print(messages.MEMORY_SEEDED.format(count=added, total=len(SEED_LESSONS)))


@app.command("reindex")
def reindex() -> None:
    """Kod tabanını anlamsal olarak indeksle (artımlı)."""
    memory = _open()
    stats = memory.code_index.reindex()
    console.print(
        messages.MEMORY_REINDEXED.format(
            total=stats.total,
            added=stats.added,
            removed=stats.removed,
            unchanged=stats.unchanged,
        )
    )


@app.command("where")
def where() -> None:
    """Belleğin diskte nerede tutulduğunu göster."""
    console.print(messages.MEMORY_LOCATION.format(path=load_config().memory_dir))


def feedback(task_type: str, model: str, verdict: str) -> None:
    """Bir modelin son sonucuna geri bildirim uygula."""
    try:
        parsed = Feedback(verdict.strip().lower())
    except ValueError:
        valid = ", ".join(item.value for item in Feedback)
        raise typer.BadParameter(
            messages.RUN_UNKNOWN_FEEDBACK.format(given=verdict, valid=valid)
        ) from None

    memory = _open()
    applied = memory.performance.apply_feedback(task_type, model, parsed)
    if not applied:
        console.print(f"[{theme.WARN}]{messages.MEMORY_FEEDBACK_MISSING}[/{theme.WARN}]")
        raise typer.Exit(1)
    console.print(
        messages.MEMORY_FEEDBACK_APPLIED.format(
            model=model, verdict=parsed.value, task_type=task_type
        )
    )


# --------------------------------------------------------------------------- #


def _open() -> Memory:
    config = load_config()
    memory = build_memory(config, root=Path.cwd())
    if not memory.enabled:
        console.print(
            f"[{theme.ERROR}]"
            f"{messages.MEMORY_UNAVAILABLE.format(reason=memory.unavailable_reason)}"
            f"[/{theme.ERROR}]"
        )
        raise typer.Exit(1)
    return memory


def _stats_table(rows: tuple[ModelStats, ...]) -> Table:
    table = Table(title=messages.MEMORY_TABLE_TITLE)
    table.add_column(messages.MEMORY_TABLE_MODEL, style="bold")
    table.add_column(messages.MEMORY_TABLE_SAMPLES, justify="right")
    table.add_column(messages.MEMORY_TABLE_SCORE, justify="right")
    table.add_column(messages.MEMORY_TABLE_WINS, justify="right")
    table.add_column(messages.MEMORY_TABLE_LATENCY, justify="right", style=theme.DIM)
    for row in rows:
        table.add_row(
            row.model,
            str(row.samples),
            f"[{_score_color(row.avg_score)}]{row.avg_score:.3f}[/{_score_color(row.avg_score)}]",
            str(row.wins),
            f"{row.avg_latency_ms} ms",
        )
    return table


def _lessons_table(lessons: tuple[Lesson, ...]) -> Table:
    mistakes = sum(1 for lesson in lessons if lesson.kind is LessonKind.MISTAKE)
    table = Table(
        title=messages.LESSON_TABLE_TITLE.format(
            mistakes=mistakes, successes=len(lessons) - mistakes
        )
    )
    table.add_column(messages.LESSON_TABLE_KIND, style="bold")
    table.add_column(messages.LESSON_TABLE_SOURCE, style=theme.DIM)
    table.add_column(messages.LESSON_TABLE_TEXT)
    for lesson in lessons:
        label, color = _KIND_LABELS[lesson.kind]
        table.add_row(
            f"[{color}]{label}[/{color}]",
            _SOURCE_LABELS[lesson.source],
            lesson.text,
        )
    return table


def _score_color(score: float) -> str:
    if score >= 0.8:
        return theme.OK
    return theme.WARN if score >= 0.6 else theme.ERROR
