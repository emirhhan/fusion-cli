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

import contextlib
from collections.abc import Iterator, Mapping
from typing import ClassVar

from rich.console import Console
from rich.markup import escape
from rich.text import Text

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
from ..core.types import FusionResult
from . import messages, theme
from .fusion_view import render_fusion_result
from .text import format_duration, strip_thinking, summarize_error
from .work import WorkIndicator

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
        show_call_details: bool = False,
        live_progress: bool = True,
    ) -> None:
        self._console = console or Console()
        self._show_progress = show_progress
        self._show_all_answers = show_all_answers
        # Fusion'da hangi adayın ne kadar sürdüğü bilgi verir; agent'ta her adım
        # için satır basmak tur özetiyle çakışır ve gürültü olur.
        self._show_call_details = show_call_details
        self._line_open = False
        self._active_channel: Channel | None = None
        # Kanal başına ham akış tamponu. Düşünme bloklarının kapanışını beklemek
        # için ham metni saklamak zorundayız; görünür kısmı ondan türetiriz.
        self._raw: dict[Channel, str] = {}
        self._shown: dict[Channel, int] = {}
        # Model çalışırken görünen canlı satır. Ekrana bir şey basılmadan önce
        # daima duraklatılır; akan metnin üstüne binmez. Tam-ekran köprüsünde
        # `live_progress=False` verilir: Live yerine layout çalışma satırı beslenir.
        self._work = WorkIndicator(self._console, enabled=live_progress)
        #: Basılmayı bekleyen durum satırı — bkz. `_status`.
        self._pending_status: str | None = None

    # -- EventSink ---------------------------------------------------------- #

    def handle(self, event: Event) -> None:
        if isinstance(event, TokenReceived):
            self._write_stream(event.channel, event.text)
        elif isinstance(event, StatusChanged):
            self._status(event.message)
        elif isinstance(event, ModelCallStarted):
            # Satır BASILMAZ: yedek zinciriyle birlikte model kimliği üç satıra
            # sarıp ekranı kaplıyordu. Bunun yerine canlı gösterge başlatılır.
            if not event.background:
                self._begin_work(messages.WORK_THINKING, model=event.role)
        elif isinstance(event, ModelCallFinished):
            self._work.update(tokens=event.result.usage.total_tokens)
            if not event.background and (self._show_call_details or not event.result.ok):
                self._model_finished(event)
        elif isinstance(event, CandidatesStarted):
            self._status(
                messages.FUSION_CANDIDATES.format(
                    count=len(event.names), names=", ".join(event.names)
                )
            )
            self._begin_work(messages.WORK_CANDIDATES.format(count=len(event.names)))
        elif isinstance(event, JudgingStarted):
            self._resume_work(
                messages.WORK_SYNTHESIZING if event.with_synthesis else messages.WORK_JUDGING
            )
        elif isinstance(event, FusionCompleted):
            self._fusion_result(event.result)
        elif isinstance(event, ToolExecuted):
            self._tool_executed(event)
            self._resume_work(messages.WORK_THINKING)
        elif isinstance(event, SubAgentStarted):
            self._status(messages.AGENT_SUBAGENT_STARTED.format(task=_shorten(event.task, 60)))
            self._resume_work(messages.WORK_SUBAGENT)
        elif isinstance(event, SubAgentFinished):
            self._status(messages.AGENT_SUBAGENT_FINISHED.format(count=event.tool_calls))
        elif isinstance(event, CouncilConsulted):
            self._status(messages.AGENT_COUNCIL)
            self._resume_work(messages.WORK_COUNCIL)
        elif isinstance(event, SelfReviewStarted):
            # Ayrı satır basılmaz; sonucu hemen ardından geliyor.
            self._resume_work(messages.WORK_REVIEW)
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
            self._finish_work()

    def print_user_message(self, text: str) -> None:
        """Kullanıcının mesajını tam genişlikte bir bant olarak bas.

        Konuşmanın kimin sözü olduğu tek bakışta görünmeli. prompt_toolkit'in
        bıraktığı satır silinir (`erase_when_done`) ve yerine bu bant çizilir.
        """
        self._end_block()
        band = Text(f" {theme.ICON_PROMPT} ", style=f"{theme.ACCENT} on {theme.SURFACE}")
        band.append(text, style=f"bold on {theme.SURFACE}")
        band.pad_right(max(0, self._console.width - band.cell_len))
        self._console.print()
        self._console.print(band)
        self._console.print()

    @contextlib.contextmanager
    def suspended(self) -> Iterator[None]:
        """Canlı çalışma göstergesini bir etkileşim boyunca duraklat.

        Prompter, kullanıcıya soru/onay sorarken terminali devralır. Live'ın
        yenileme iş parçacığı bu sırada durmazsa cevap istemini ve kullanıcının
        yazdığını sürekli siler. Bittiğinde gösterge kaldığı yerden sürer.
        """
        self._work.pause()
        try:
            yield
        finally:
            self._work.resume()

    # -- Akış --------------------------------------------------------------- #

    def _write_stream(self, channel: Channel, text: str) -> None:
        if not text:
            return
        # Bekleyen durum satırı cevabın ÖNÜNE basılmalı; sıra bozulmamalı.
        self._flush_status()
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
        """Akışın başına kimin konuştuğunu gösteren işaret koy."""
        label = _CHANNEL_LABELS.get(channel)
        if label is not None:
            self._console.print(f"[{theme.ACCENT_ALT}]┌ {label}[/{theme.ACCENT_ALT}]")
            return
        # Ana kanal: cevabın ilk satırının başına işaret — satır sonu YOK, metin
        # hemen ardından akacak.
        self._console.out(f"{theme.ICON_ANSWER} ", end="", highlight=False, style=theme.ACCENT)

    def _end_block(self) -> None:
        """Akış bloğunu kapat.

        Araya başka bir çıktı (durum, araç kartı, hata) girdiğinde cevap bloğu
        biter; sonraki metin YENİ bir blok olarak kendi işaretiyle başlar. Aksi
        halde düzeltici turun cevabı işaretsiz kalıp öncekinin devamı gibi görünür.
        """
        self._close_line()
        self._flush_status()
        self._active_channel = None

    def _close_line(self) -> None:
        """Yarım kalmış akış satırını kapat ve canlı göstergeyi duraklat.

        Ekrana bir şey basmadan önce çağrılan tek nokta burasıdır; gösterge de
        burada durdurulur ki hiçbir çıktı onun üstüne binmesin.
        """
        self._work.pause()
        if self._line_open:
            self._console.out("")
            self._line_open = False

    # -- Diğer olaylar ------------------------------------------------------- #

    def _status(self, message: str) -> None:
        """Durum satırını KUYRUĞA al; basmayı bir adım geciktir.

        Turun son durum satırı (çoğunlukla `öz-denetim · sorun yok`) ile süre/token
        özeti ayrı iki satıra bölününce ekran gereksiz yere uzuyordu. Bir adım
        geciktirince turun sonunda hangi satırın son olduğu bilinir ve özet onun
        sonuna parantez içinde yazılır. Bekleyen satır, ekrana başka bir şey
        basılmadan önce (`_close_line`) mutlaka boşaltılır; sıra bozulmaz.
        Canlı ilerleme hissi zaten çalışma göstergesinden geliyor.
        """
        if not self._show_progress:
            return
        self._end_block()
        self._pending_status = message

    def _flush_status(self, detail: str = "") -> None:
        """Bekleyen durum satırını bas. `detail` verilirse sonuna parantezle ekle."""
        message, self._pending_status = self._pending_status, None
        if message is None:
            return
        body = escape(message)
        if detail:
            body += f" ({escape(detail)})"
        self._console.print(f"[{theme.DIM}]{theme.ICON_STATUS} {body}[/{theme.DIM}]")

    def _model_finished(self, event: ModelCallFinished) -> None:
        result = event.result
        if result.ok:
            self._status(
                messages.MODEL_CALL_OK.format(
                    role=event.role,
                    duration=format_duration(result.latency_ms),
                    tokens=result.usage.total_tokens,
                )
            )
            return
        # Sağlayıcı hataları çok uzun olabiliyor; ekranı kaplamasın, özü görünsün.
        self._error(
            messages.MODEL_CALL_FAILED.format(
                role=event.role, error=summarize_error(result.error or "")
            )
        )

    def _error(self, message: str) -> None:
        self._end_block()
        label = f"[{theme.ERROR}]{theme.ICON_ERROR} {messages.ERROR_PREFIX}[/{theme.ERROR}]"
        self._console.print(f"{label} {escape(message)}")

    # -- Çalışma göstergesi -------------------------------------------------- #

    def _begin_work(self, label: str, *, model: str = "") -> None:
        """Bekleme başladı: göstergeyi kur ya da etiketini güncelle.

        Zaten çalışan bir tur varsa süre sıfırlanmaz — kullanıcı turun TAMAMININ
        ne kadar sürdüğünü görmek ister, tek bir model çağrısının değil.
        """
        if self._work.running:
            self._resume_work(label)
            return
        self._close_line()
        self._work.start(label, model=model)

    def _resume_work(self, label: str) -> None:
        """Göstergeyi güvenle yeniden göster.

        KRİTİK: gösterge asla YARIM SATIRIN üstünde başlatılmaz. Rich `Live`
        `transient` modda durduğunda çizdiği bölgeyi siler; satır ortasında
        başlatılırsa o satırı — yani modelin cevabını — silip götürür.
        `_close_line()` hem göstergeyi duraklatır hem satırı kapatır.
        """
        self._close_line()
        self._work.update(label=label)
        self._work.resume()

    def _finish_work(self) -> None:
        """Turu bitir ve özeti bas.

        Bekleyen bir durum satırı varsa özet ayrı satır açmaz, onun sonuna
        parantez içinde girer.
        """
        detail = self._work.finish()
        if self._pending_status is not None:
            self._flush_status(detail or "")
            return
        if detail is None:
            return
        summary = Text("  ")
        summary.append(f"{theme.ICON_DONE} ", style=theme.ACCENT)
        summary.append(detail, style=theme.DIM)
        self._console.print()
        self._console.print(summary)

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
        self._end_block()
        icon, color = self._OUTCOME_STYLES[event.outcome]
        cagri = _format_call(event.name, event.args)
        summary = _shorten(event.output.replace("\n", " "), 96)

        self._console.print(f"  [{color}]{icon}[/{color}] {escape(cagri)}")
        if summary:
            self._console.print(f"    [{theme.DIM}]{escape(summary)}[/{theme.DIM}]")

    # -- Fusion sonucu ------------------------------------------------------- #

    def _fusion_result(self, result: FusionResult) -> None:
        self._end_block()
        render_fusion_result(self._console, result, show_all_answers=self._show_all_answers)


#: Bu uzunluğu aşan argüman değeri ham gösterilmez, yerine boyutu yazılır.
_ARG_VALUE_LIMIT = 48


#: Araç → o araca ait BİRİNCİL argüman. Çağrı satırında yalnızca bu gösterilir;
#: "hangi dosya / hangi komut" sorusunun cevabı budur.
_PRIMARY_ARG: dict[str, str] = {
    "read_file": "path",
    "view_file": "path",
    "write_file": "path",
    "edit_file": "path",
    "multi_edit": "path",
    "list_dir": "path",
    "glob": "pattern",
    "search_code": "pattern",
    "grep_search": "pattern",
    "run_shell": "command",
    "git": "subcommand",
    "web_search": "query",
    "web_fetch": "url",
    "read_url_content": "url",
    "scaffold_web": "path",
    "find_skill": "query",
    "read_skill": "name",
    "find_agent": "query",
    "spawn_agent": "task",
}
#: Sonucu DEĞİŞTİREN ikincil alanlar; onay ekranında görünmeleri gerekir.
_FLAG_ARGS = ("replace_all",)
#: Çağrı satırının tamamı için üst sınır.
_CALL_LIMIT = 76


def _format_call(name: str, args: Mapping[str, object]) -> str:
    """Araç çağrısını `ad(birincil argüman)` biçiminde göster.

    Eskiden ham `anahtar=değer` listesi basılıyordu ve 15 KB'lık `content` satırı tek
    başına doldurup diğer alanları ekrandan siliyordu — hangi dosyaya yazıldığı bile
    görünmüyordu. Artık "hangi dosya / hangi komut" sorusunun cevabı öne alınır.
    """
    anahtar = _PRIMARY_ARG.get(name)
    deger = args.get(anahtar) if anahtar else None
    govde = _format_value(deger) if isinstance(deger, str) and deger.strip() else _fallback(args)

    bayraklar = [ad for ad in _FLAG_ARGS if args.get(ad) is True]
    if bayraklar:
        govde = f"{govde}, {', '.join(bayraklar)}" if govde else ", ".join(bayraklar)

    tek_satir = " ".join(f"{name}({govde})".split())
    if len(tek_satir) <= _CALL_LIMIT:
        return tek_satir
    # Kısaltırken kapanış parantezi KORUNUR: yarım kalan çağrı okunmuyor.
    return tek_satir[: _CALL_LIMIT - 2] + "…)"


def _fallback(args: Mapping[str, object]) -> str:
    """Birincil alan yoksa geriye kalanı özetle (eksik `path` hatası buna düşer)."""
    return ", ".join(f"{ad}={_format_value(deger)}" for ad, deger in args.items())


def _format_args(args: Mapping[str, object]) -> str:
    """Araç argümanlarını tek satırda özetle.

    Büyük değerler (dosya içeriği gibi) boyutuyla gösterilir. Ham basılırlarsa tek bir
    alan satırı doldurur ve geri kalanı kesilip kaybolur: `write_file` çağrısında model
    içeriği önce yazdığında sondaki hatalı `path` ekrana hiç ulaşmıyor, kullanıcı hangi
    alanın sorunlu olduğunu göremiyordu. Her alanın GÖRÜNMESİ, birinin tam görünmesinden
    daha değerlidir.
    """
    return ", ".join(f"{key}={_format_value(value)}" for key, value in args.items())


def _format_value(value: object) -> str:
    text = str(value)
    return text if len(text) <= _ARG_VALUE_LIMIT else f"<{len(text)} karakter>"


def _shorten(text: str, limit: int) -> str:
    """Uzun metni tek satıra sığdır. Araç kartı ekranı taşırmamalıdır."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
