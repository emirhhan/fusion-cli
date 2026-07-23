"""Terminal render'ı — olayları ekrana basan tek yer.

Rich importu YALNIZCA bu dosyadadır; motor katmanı terminal kütüphanesi tanımaz.

Eski projedeki "anlamsız görüntü" hatasının çözümü buradaki iki değişmezdir:

1. **Satır bütünlüğü.** Akan metin yarım satır bırakmışken durum/hata satırı
   basılmaz; önce satır kapatılır. Eski kodda bu bayrağı set eden fonksiyon hiç
   çağrılmadığı için cümlenin ortası araç kartının altına düşüyordu.
2. **Kanal ayrımı.** Farklı kanaldan (alt-ajan, council) metin geldiğinde önce
   mevcut satır kapatılır ve kanal başlığı basılır; iki akış aynı satıra binemez.

Veriyolu olayları zaten sırayla verdiği için burada eşzamanlılık kaygısı yoktur.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.table import Table

from ..core.events import (
    CandidatesStarted,
    Channel,
    ContextCompressed,
    CouncilConsulted,
    ErrorOccurred,
    Event,
    FusionCompleted,
    JudgingStarted,
    LessonsLearned,
    LessonsRecalled,
    ModelCallFinished,
    ModelCallStarted,
    SelfReviewFinished,
    SelfReviewStarted,
    StatusChanged,
    StepLimitReached,
    SubAgentFinished,
    SubAgentStarted,
    TokenReceived,
    ToolExecuted,
    ToolOutcome,
    TurnFinished,
)
from ..core.types import FusionResult, VerdictSource
from . import messages, theme
from .text import strip_thinking

_CHANNEL_LABELS = {
    Channel.SUBAGENT: "alt-ajan",
    Channel.COUNCIL: "council",
}


class ConsoleRenderer:
    """Olayları Rich konsoluna basan dinleyici."""

    def __init__(
        self,
        console: Console | None = None,
        *,
        show_progress: bool = True,
        show_all_answers: bool = False,
    ) -> None:
        self._console = console or Console()
        self._show_progress = show_progress
        self._show_all_answers = show_all_answers
        self._line_open = False
        self._active_channel: Channel | None = None
        # Kanal başına ham akış tamponu. Düşünme bloklarının kapanışını beklemek
        # için ham metni saklamak zorundayız; görünür kısmı ondan türetiriz.
        self._raw: dict[Channel, str] = {}
        self._shown: dict[Channel, int] = {}

    # -- EventSink ---------------------------------------------------------- #

    def handle(self, event: Event) -> None:
        if isinstance(event, TokenReceived):
            self._write_stream(event.channel, event.text)
        elif isinstance(event, StatusChanged):
            self._status(event.message)
        elif isinstance(event, ModelCallStarted):
            if not event.background:
                self._status(messages.MODEL_CALL_STARTED.format(role=event.role, model=event.model))
        elif isinstance(event, ModelCallFinished):
            if not event.background:
                self._model_finished(event)
        elif isinstance(event, CandidatesStarted):
            self._status(
                messages.FUSION_CANDIDATES.format(
                    count=len(event.names), names=", ".join(event.names)
                )
            )
        elif isinstance(event, JudgingStarted):
            self._status(
                messages.FUSION_JUDGING_AND_SYNTHESIZING
                if event.with_synthesis
                else messages.FUSION_JUDGING
            )
        elif isinstance(event, FusionCompleted):
            self._fusion_result(event.result)
        elif isinstance(event, ToolExecuted):
            self._tool_executed(event)
        elif isinstance(event, SubAgentStarted):
            self._status(messages.AGENT_SUBAGENT_STARTED.format(task=_shorten(event.task, 60)))
        elif isinstance(event, SubAgentFinished):
            self._status(messages.AGENT_SUBAGENT_FINISHED.format(count=event.tool_calls))
        elif isinstance(event, CouncilConsulted):
            self._status(messages.AGENT_COUNCIL)
        elif isinstance(event, SelfReviewStarted):
            self._status(messages.AGENT_SELF_REVIEW_STARTED)
        elif isinstance(event, SelfReviewFinished):
            self._status(
                messages.AGENT_SELF_REVIEW_ISSUE
                if event.issue_found
                else messages.AGENT_SELF_REVIEW_CLEAN
            )
        elif isinstance(event, LessonsRecalled):
            self._status(messages.AGENT_LESSONS_RECALLED.format(count=event.count))
        elif isinstance(event, LessonsLearned):
            self._status(messages.AGENT_LESSONS_LEARNED.format(count=event.count))
        elif isinstance(event, ContextCompressed):
            self._status(
                messages.AGENT_CONTEXT_COMPRESSED.format(before=event.before, after=event.after)
            )
        elif isinstance(event, StepLimitReached):
            self._error(messages.AGENT_STEP_LIMIT.format(limit=event.limit))
        elif isinstance(event, ErrorOccurred):
            self._error(event.message)
        elif isinstance(event, TurnFinished):
            self._flush_streams()
            self._close_line()
            self._active_channel = None

    # -- Akış --------------------------------------------------------------- #

    def _write_stream(self, channel: Channel, text: str) -> None:
        if not text:
            return
        self._raw[channel] = self._raw.get(channel, "") + text
        visible = strip_thinking(self._raw[channel], streaming=True)
        shown = self._shown.get(channel, 0)
        if len(visible) <= shown:
            return  # gelen parça tamamen düşünme metniydi; basılacak bir şey yok

        if channel is not self._active_channel:
            self._close_line()
            self._channel_header(channel)
            self._active_channel = channel

        fresh = visible[shown:]
        # `out` ham yazar: model çıktısındaki köşeli parantezler Rich markup'ı
        # sanılıp yorumlanmaz, çıktı bozulmaz.
        self._console.out(fresh, end="", highlight=False)
        self._shown[channel] = len(visible)
        self._line_open = not fresh.endswith("\n")

    def _flush_streams(self) -> None:
        """Akış bitti: geri tutulan son parçaları bas ve tamponları boşalt.

        Akış sırasında `<think>` etiketinin başlangıcı olabilecek parça geri
        tutulur; tur bitince bu belirsizlik ortadan kalkar.
        """
        for channel, raw in self._raw.items():
            visible = strip_thinking(raw)
            shown = self._shown.get(channel, 0)
            if len(visible) > shown:
                self._console.out(visible[shown:], end="", highlight=False)
                self._line_open = not visible.endswith("\n")
        self._raw.clear()
        self._shown.clear()

    def _channel_header(self, channel: Channel) -> None:
        label = _CHANNEL_LABELS.get(channel)
        if label is not None:
            self._console.print(f"[{theme.ACCENT_ALT}]┌ {label}[/{theme.ACCENT_ALT}]")

    def _close_line(self) -> None:
        """Yarım kalmış akış satırını kapat. Panel/durum satırı asla metnin üstüne binmez."""
        if self._line_open:
            self._console.out("")
            self._line_open = False

    # -- Diğer olaylar ------------------------------------------------------- #

    def _status(self, message: str) -> None:
        if not self._show_progress:
            return
        self._close_line()
        body = escape(message)
        self._console.print(f"[{theme.DIM}]{theme.ICON_STATUS} {body}[/{theme.DIM}]")

    def _model_finished(self, event: ModelCallFinished) -> None:
        result = event.result
        if result.ok:
            self._status(
                messages.MODEL_CALL_OK.format(
                    role=event.role,
                    latency=result.latency_ms,
                    tokens=result.usage.total_tokens,
                )
            )
            return
        self._error(messages.MODEL_CALL_FAILED.format(role=event.role, error=result.error or ""))

    def _error(self, message: str) -> None:
        self._close_line()
        label = f"[{theme.ERROR}]{theme.ICON_ERROR} {messages.ERROR_PREFIX}[/{theme.ERROR}]"
        self._console.print(f"{label} {escape(message)}")

    # -- Agent araç kartı ---------------------------------------------------- #

    #: Araç sonucuna göre simge ve renk. Reddedilme ne ✓ ne ✗ ile gösterilir.
    _OUTCOME_STYLES: ClassVar[dict[ToolOutcome, tuple[str, str]]] = {
        ToolOutcome.OK: (theme.ICON_OK, theme.OK),
        ToolOutcome.FAILED: (theme.ICON_ERROR, theme.ERROR),
        ToolOutcome.DENIED: (theme.ICON_DENIED, theme.WARN),
        ToolOutcome.BLOCKED: (theme.ICON_DENIED, theme.DIM),
    }

    def _tool_executed(self, event: ToolExecuted) -> None:
        """Araç çağrısını iki satırlık kompakt kart olarak bas."""
        self._close_line()
        icon, color = self._OUTCOME_STYLES[event.outcome]
        args = _shorten(_format_args(event.args), 78)
        summary = _shorten(event.output.replace("\n", " "), 96)

        self._console.print(
            f"  [{color}]{icon} {escape(event.name)}[/{color}] "
            f"[{theme.DIM}]{escape(args)}[/{theme.DIM}]"
        )
        if summary:
            self._console.print(f"    [{theme.DIM}]{escape(summary)}[/{theme.DIM}]")

    # -- Fusion sonucu ------------------------------------------------------- #

    #: Kazananın nasıl belirlendiğine göre başlık metni.
    _SOURCE_LABELS: ClassVar[dict[VerdictSource, str]] = {
        VerdictSource.SINGLE: messages.FUSION_SINGLE,
        VerdictSource.FALLBACK: messages.FUSION_JUDGE_FALLBACK,
    }

    def _fusion_result(self, result: FusionResult) -> None:
        self._close_line()
        if result.source is VerdictSource.NONE:
            return  # cevapsız tur: hatayı `ErrorOccurred` zaten bildirdi

        self._console.print()
        self._console.print(f"[bold {theme.ACCENT}]{self._headline(result)}[/bold {theme.ACCENT}]")
        # Hakemin gerekçesi KAZANAN adayı anlatır. Sentez gösterildiğinde ekrandaki
        # metin kazananın metni değildir; gerekçeyi orada göstermek yanıltıcı olur.
        if result.reason and not result.synthesized:
            self._console.print(f"[{theme.DIM}]{escape(result.reason)}[/{theme.DIM}]")
        self._console.print()
        # Nihai cevap markdown olarak basılır; kod blokları ve listeler okunur kalır.
        self._console.print(Markdown(result.final_answer))
        self._console.print()

        self._candidate_summary(result)
        if self._show_all_answers:
            self._all_answers(result)
        self._score_table(result)

    def _headline(self, result: FusionResult) -> str:
        if result.synthesized:
            return messages.FUSION_SYNTHESIZED
        label = self._SOURCE_LABELS.get(result.source)
        if label is not None:
            return label
        return messages.FUSION_WINNER.format(winner=result.winner)

    def _candidate_summary(self, result: FusionResult) -> None:
        parts = []
        for candidate in result.candidates:
            if candidate.ok and candidate.text:
                mark = "★" if candidate.name == result.winner else theme.ICON_OK
                parts.append(
                    f"[{theme.OK}]{mark} {escape(candidate.name)} "
                    f"{candidate.latency_ms}ms[/{theme.OK}]"
                )
            else:
                parts.append(
                    f"[{theme.ERROR}]{theme.ICON_ERROR} {escape(candidate.name)}[/{theme.ERROR}]"
                )
        self._console.print(
            f"[{theme.DIM}]{messages.FUSION_CANDIDATE_SUMMARY}[/{theme.DIM}] " + " ".join(parts)
        )

    def _all_answers(self, result: FusionResult) -> None:
        for candidate in result.successful:
            title = messages.FUSION_ALL_ANSWERS.format(
                name=candidate.name, latency=candidate.latency_ms
            )
            style = theme.OK if candidate.name == result.winner else theme.INFO
            self._console.print()
            self._console.print(f"[{style}]{escape(title)}[/{style}]")
            self._console.print(Markdown(candidate.text))

    def _score_table(self, result: FusionResult) -> None:
        if not result.scores:
            return
        table = Table(show_edge=False, pad_edge=False, box=None)
        table.add_column(messages.FUSION_SCORE_TABLE_MODEL, style="bold")
        table.add_column(messages.FUSION_SCORE_TABLE_SCORE, justify="right")
        for name, score in sorted(result.scores.items(), key=lambda item: item[1], reverse=True):
            mark = " ★" if name == result.winner else ""
            table.add_row(
                escape(name) + mark, f"[{_score_color(score)}]{score:.2f}[/{_score_color(score)}]"
            )
        self._console.print(table)


def _score_color(score: float) -> str:
    if score >= 0.8:
        return theme.OK
    if score >= 0.6:
        return theme.WARN
    return theme.ERROR


def _format_args(args: Mapping[str, object]) -> str:
    return ", ".join(f"{key}={value}" for key, value in args.items())


def _shorten(text: str, limit: int) -> str:
    """Uzun metni tek satıra sığdır. Araç kartı ekranı taşırmamalıdır."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
