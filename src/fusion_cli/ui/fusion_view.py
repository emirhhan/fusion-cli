"""Fusion sonucunun terminal sunumu.

`ConsoleRenderer`'dan ayrıldı: fusion turu bittiğinde kazanan başlığı, nihai cevap,
aday özeti, (istenirse) tüm cevaplar ve puan tablosu buradan basılır. Yalnızca
`Console`'a ve `FusionResult`'a bağlıdır; render'ın geri kalanının akan-metin/kanal
durumunu paylaşmaz, bu yüzden temiz biçimde modül fonksiyonlarına taşınabildi.
"""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.table import Table

from ..core.types import FusionResult, VerdictSource
from . import messages, theme
from .text import format_duration

#: Kazananın nasıl belirlendiğine göre başlık metni.
_SOURCE_LABELS: dict[VerdictSource, str] = {
    VerdictSource.SINGLE: messages.FUSION_SINGLE,
    VerdictSource.FALLBACK: messages.FUSION_JUDGE_FALLBACK,
}


def render_fusion_result(
    console: Console, result: FusionResult, *, show_all_answers: bool
) -> None:
    """Fusion turunun sonucunu bas. Cevapsız tur (`NONE`) sessizce atlanır."""
    if result.source is VerdictSource.NONE:
        return  # cevapsız tur: hatayı `ErrorOccurred` zaten bildirdi

    console.print()
    console.print(f"[bold {theme.ACCENT}]{_headline(result)}[/bold {theme.ACCENT}]")
    # Hakemin gerekçesi KAZANAN adayı anlatır. Sentez gösterildiğinde ekrandaki
    # metin kazananın metni değildir; gerekçeyi orada göstermek yanıltıcı olur.
    if result.reason and not result.synthesized:
        console.print(f"[{theme.DIM}]{escape(result.reason)}[/{theme.DIM}]")
    console.print()
    # Nihai cevap markdown olarak basılır; kod blokları ve listeler okunur kalır.
    console.print(Markdown(result.final_answer))
    console.print()

    _candidate_summary(console, result)
    if show_all_answers:
        _all_answers(console, result)
    _score_table(console, result)


def _headline(result: FusionResult) -> str:
    if result.synthesized:
        return messages.FUSION_SYNTHESIZED
    label = _SOURCE_LABELS.get(result.source)
    if label is not None:
        return label
    return messages.FUSION_WINNER.format(winner=result.winner)


def _candidate_summary(console: Console, result: FusionResult) -> None:
    parts = []
    for candidate in result.candidates:
        if candidate.ok and candidate.text:
            mark = "★" if candidate.name == result.winner else theme.ICON_OK
            duration = format_duration(candidate.latency_ms)
            parts.append(
                f"[{theme.OK}]{mark} {escape(candidate.name)}[/{theme.OK}]"
                f" [{theme.DIM}]{duration}[/{theme.DIM}]"
            )
        else:
            parts.append(
                f"[{theme.ERROR}]{theme.ICON_ERROR} {escape(candidate.name)}[/{theme.ERROR}]"
            )
    separator = f" [{theme.DIM}]·[/{theme.DIM}] "
    console.print(
        f"[{theme.DIM}]{messages.FUSION_CANDIDATE_SUMMARY}[/{theme.DIM}] " + separator.join(parts)
    )


def _all_answers(console: Console, result: FusionResult) -> None:
    for candidate in result.successful:
        title = messages.FUSION_ALL_ANSWERS.format(
            name=candidate.name, duration=format_duration(candidate.latency_ms)
        )
        style = theme.OK if candidate.name == result.winner else theme.INFO
        console.print()
        console.print(f"[{style}]{escape(title)}[/{style}]")
        console.print(Markdown(candidate.text))


def _score_table(console: Console, result: FusionResult) -> None:
    if not result.scores:
        return
    table = Table(show_edge=False, pad_edge=False, box=None)
    table.add_column(messages.FUSION_SCORE_TABLE_MODEL, style="bold")
    table.add_column(messages.FUSION_SCORE_TABLE_SCORE, justify="right")
    for name, score in sorted(result.scores.items(), key=lambda item: item[1], reverse=True):
        mark = " ★" if name == result.winner else ""
        color = _score_color(score)
        table.add_row(escape(name) + mark, f"[{color}]{score:.2f}[/{color}]")
    console.print(table)


def _score_color(score: float) -> str:
    if score >= 0.8:
        return theme.OK
    if score >= 0.6:
        return theme.WARN
    return theme.ERROR
