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
import textwrap
from collections.abc import Iterator, Mapping, Sequence
from typing import ClassVar

from rich.console import Console
from rich.markup import escape
from rich.padding import Padding
from rich.text import Text

from ..core.events import (
    ApprenticeHandoff,
    CandidatesStarted,
    ChangesDigested,
    Channel,
    ContextCompressed,
    CouncilConsulted,
    EffectWorkflowFinished,
    EffectWorkflowProgress,
    EffectWorkflowStarted,
    ErrorOccurred,
    Event,
    ExecutionCheckpointSaved,
    ExecutionCompleted,
    ExecutionPaused,
    ExecutionPlanCreated,
    ExecutionRetryScheduled,
    ExecutionRouteSelected,
    ExecutionStepStarted,
    ExecutionStepVerified,
    FilesChanged,
    FollowupsSuggested,
    FusionCompleted,
    JudgingStarted,
    LessonsLearned,
    LessonsRecalled,
    ModelCallFinished,
    ModelCallStarted,
    ModelFallbackActivated,
    MutationUnavailable,
    NarrationPublished,
    NoFileChanges,
    PlatformChecked,
    PreviewReady,
    SelfReviewFinished,
    SelfReviewStarted,
    StatusChanged,
    SubAgentFinished,
    SubAgentStarted,
    TeacherConsulted,
    TeacherLessonRecorded,
    TeacherLimitationFound,
    TeacherMemoryUsed,
    TeacherPlanPrepared,
    TeacherTaskClassified,
    TierDegraded,
    TokenReceived,
    ToolCallRepaired,
    ToolExecuted,
    ToolOutcome,
    TurnAnswered,
    TurnBudgetExhausted,
    TurnFinished,
    TurnOutcome,
    VerificationPassed,
)
from ..core.types import FusionResult
from . import messages, theme
from .diff import render_diff
from .fusion_view import render_fusion_result
from .text import (
    format_duration,
    format_model,
    format_served_model,
    segment,
    strip_thinking,
    summarize_error,
)
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
        show_thinking: bool = False,
        live_progress: bool = True,
    ) -> None:
        self._console = console or Console()
        self._show_progress = show_progress
        self._show_all_answers = show_all_answers
        # Açıkken model düşünmesi (`<think>…`) gizlenmez; Claude Code gibi sönük bir
        # blok olarak akıtılır. Varsayılan kapalı — kullanıcının alıştığı sade akış korunur.
        self._show_thinking = show_thinking
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
        #: Bu turda açılış beyanı basıldı mı? İLK öncü daha geniş yer alır.
        self._turn_opened = False
        #: Bu turda gösterilen yedek geçişleri (istenen, yedek). Ölçüldü (30 Ekim): açık
        #: devrede her model çağrısı aynı "yedek devrede" satırını basıyordu (turda 12 kez).
        self._fallbacks_shown: set[tuple[str, str]] = set()
        #: Koşan alt ajanların kimliği → kişilik ünvanı (bitiş satırında ad için).
        self._sub_titles: dict[str, str] = {}

    # -- EventSink ---------------------------------------------------------- #

    def handle(self, event: Event) -> None:
        if isinstance(event, TokenReceived):
            if event.provisional:
                self._preamble(event.channel, event.text)
            else:
                self._write_stream(event.channel, event.text)
        elif isinstance(event, TurnAnswered):
            # Tam, akışsız metin: kapanışı beklenen bir akış değildir. `streaming=False`
            # ile ayıklanır ki açılışı olmayan `</think>` (gemini_web) düşünme sayılsın
            # ve etiketiyle birlikte ekrana basılmasın (L1-02).
            self._write_stream(event.channel, event.text, complete=True)
        elif isinstance(event, StatusChanged):
            self._status(event.message)
        elif isinstance(event, ModelCallStarted):
            # Satır BASILMAZ: canlı gösterge başlatılır. Etiket artık yedek
            # zincirinin tamamı değil BİRİNCİL modeldir, dolayısıyla ekranı
            # kaplamaz (bkz. `FallbackProvider.label`).
            if not event.background:
                self._begin_work(messages.WORK_THINKING, model=format_model(event.model))
        elif isinstance(event, ModelCallFinished):
            self._work.update(tokens=event.result.usage.total_tokens)
            # Cevabı gerçekte hangi model verdiyse gösterge ona güncellenir:
            # yedek devraldığında kullanıcı seçtiği modeli görmeye devam etmemeli.
            if not event.background and event.result.model:
                self._work.update(
                    model=format_served_model(event.result.model, event.result.served_by)
                )
            # Bazı sağlayıcılar düşünmeyi metne gömülü `<think>` yerine YAPILI bir
            # alanda döner (`ModelResult.reasoning`, litellm'in `reasoning_content`
            # alanından — bkz. `providers/litellm_provider.py`). İKİ AYRI kanal
            # farklı ürettiği için birleştirilmedi; `--show-thinking` AÇIKKEN ikisi
            # de görünür olsun diye bu kanal da AYNI bayrağı ve AYNI sönük stili
            # kullanır (yeni bir bayrak İCAT EDİLMEDİ). `show_call_details`'tan
            # BAĞIMSIZDIR — düşünme bir ayrıntı seviyesi değil, ayrı bir bayrak.
            if not event.background and self._show_thinking and event.result.reasoning:
                self._print_structured_reasoning(event.result.reasoning)
            if not event.background and (self._show_call_details or not event.result.ok):
                self._model_finished(event)
        elif isinstance(event, ModelFallbackActivated):
            gecis = (event.requested_model, event.fallback_model)
            if not event.background and gecis not in self._fallbacks_shown:
                self._fallbacks_shown.add(gecis)
                self._work.update(model=format_model(event.fallback_model))
                self._warn(
                    messages.MODEL_FALLBACK.format(
                        requested=format_model(event.requested_model),
                        fallback=format_model(event.fallback_model),
                        reason=summarize_error(event.reason),
                    )
                )
        elif isinstance(event, TierDegraded):
            # Yalnız BİLGİLENDİRİR — turu ASLA düşürmez (bkz. olayın docstring'i).
            self._warn(
                messages.TIER_DEGRADED.format(
                    expected=event.expected_tier,
                    served=event.served_by,
                    model=format_model(event.model),
                )
            )
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
        elif isinstance(event, EffectWorkflowStarted):
            self._status(f"{theme.ICON_STATUS} {event.title}")
            self._resume_work(event.title)
        elif isinstance(event, EffectWorkflowProgress):
            self._status(event.message)
        elif isinstance(event, EffectWorkflowFinished):
            self._effect_workflow_finished(event)
        elif isinstance(event, ExecutionRouteSelected):
            yol = "planlı" if event.route == "workflow" else "hızlı"
            self._status(f"Yürütme yolu: {yol} — {'; '.join(event.reasons)}")
        elif isinstance(event, ExecutionPlanCreated):
            self._status(f"Plan hazır: {event.total_steps} doğrulanabilir adım")
        elif isinstance(event, ExecutionStepStarted):
            self._status(f"Adım {event.index}/{event.total_steps}: {event.goal}")
        elif isinstance(event, ExecutionStepVerified):
            durum = "doğrulandı" if event.ok else "doğrulanamadı"
            ayrinti = event.evidence if event.ok else event.findings
            self._status(f"{event.step_id} {durum}: {'; '.join(ayrinti)}")
        elif isinstance(event, ExecutionRetryScheduled):
            self._status(f"Kurtarma {event.action} (deneme {event.attempt}): {event.reason}")
        elif isinstance(event, ExecutionCheckpointSaved):
            self._status(f"Checkpoint kaydedildi: {event.completed_steps} adım tamam")
        elif isinstance(event, ExecutionPaused):
            self._warn(f"Workflow duraklatıldı: {event.reason}")
        elif isinstance(event, ExecutionCompleted):
            self._status(f"Plan tamamlandı: {event.total_steps} adım doğrulandı")
            # Kanıtlanmayan şey SESSİZ kalmaz: "tamamlandı" satırı tek başına
            # kullanıcıya işin kanıtlandığını düşündürür.
            for uyari in event.warnings:
                self._warn(f"UYARI: {uyari}")
        elif isinstance(event, ToolExecuted):
            self._tool_executed(event)
            self._resume_work(messages.WORK_THINKING)
        elif isinstance(event, ToolCallRepaired):
            self._status(messages.AGENT_TOOL_CALL_REPAIRED)
        elif isinstance(event, PreviewReady):
            self._status(messages.AGENT_PREVIEW_READY.format(url=event.url))
        elif isinstance(event, SubAgentStarted):
            self._sub_titles[event.sub_id] = event.title or "alt-ajan"
            self._status(
                messages.AGENT_SUBAGENT_STARTED.format(
                    title=self._sub_titles[event.sub_id], task=_shorten(event.task, 60)
                )
            )
            self._resume_work(messages.WORK_SUBAGENT)
        elif isinstance(event, SubAgentFinished):
            self._status(
                messages.AGENT_SUBAGENT_FINISHED.format(
                    title=self._sub_titles.pop(event.sub_id, "alt-ajan"), count=event.tool_calls
                )
            )
        elif isinstance(event, CouncilConsulted):
            self._status(messages.AGENT_COUNCIL)
            self._resume_work(messages.WORK_COUNCIL)
        elif isinstance(event, TeacherConsulted):
            self._status(messages.AGENT_TEACHER)
            self._resume_work(messages.WORK_TEACHER)
        elif isinstance(event, TeacherTaskClassified):
            size = "orta-büyük" if event.size == "orta-buyuk" else "basit"
            self._status(messages.AGENT_TEACHER_TASK.format(size=size))
        elif isinstance(event, TeacherPlanPrepared):
            self._status(
                messages.AGENT_TEACHER_PLAN.format(steps=event.steps)
                if event.structured
                else messages.AGENT_TEACHER_PLAN_NOTE
            )
        elif isinstance(event, NarrationPublished):
            self._status(event.text)
        elif isinstance(event, ApprenticeHandoff):
            ogretmen = f", {event.teacher_model} öğretmen" if event.teacher_model else ""
            self._status(
                messages.AGENT_APPRENTICE_HANDOFF.format(
                    selected=event.selected_model,
                    apprentice=event.apprentice_model,
                    teacher=ogretmen,
                )
            )
        elif isinstance(event, PlatformChecked):
            template = (
                messages.AGENT_PLATFORM_VERIFIED
                if event.method == "resmi-kaynak"
                else messages.AGENT_PLATFORM_UNVERIFIED
            )
            self._status(
                template.format(platforms=", ".join(event.platforms), sources=event.sources)
            )
        elif isinstance(event, TeacherMemoryUsed):
            self._status(
                messages.AGENT_TEACHER_MEMORY.format(steps=event.steps, similarity=event.similarity)
            )
        elif isinstance(event, TeacherLessonRecorded):
            if not event.reused:
                self._status(messages.AGENT_TEACHER_LESSON_NEW)
            elif event.success:
                self._status(messages.AGENT_TEACHER_LESSON_REUSED_OK)
            else:
                self._status(messages.AGENT_TEACHER_LESSON_REUSED_FAIL)
        elif isinstance(event, TeacherLimitationFound):
            self._status(
                messages.AGENT_TEACHER_LIMITATION.format(
                    topic=event.topic, reason=event.reason, alternative=event.alternative
                )
            )
        elif isinstance(event, SelfReviewStarted):
            # Ayrı satır basılmaz; sonucu hemen ardından geliyor.
            self._resume_work(messages.WORK_REVIEW)
        elif isinstance(event, SelfReviewFinished):
            self._status(
                messages.AGENT_SELF_REVIEW_UNAVAILABLE
                if not event.completed
                else (
                    messages.AGENT_SELF_REVIEW_ISSUE
                    if event.issue_found
                    else messages.AGENT_SELF_REVIEW_CLEAN
                )
            )
        elif isinstance(event, LessonsRecalled):
            self._status(messages.AGENT_LESSONS_RECALLED.format(count=event.count))
        elif isinstance(event, LessonsLearned):
            self._status(messages.AGENT_LESSONS_LEARNED.format(count=event.count))
        elif isinstance(event, ContextCompressed):
            satir = _compression_line(event)
            if satir:
                self._warn(satir)
        elif isinstance(event, MutationUnavailable):
            self._warn(messages.AGENT_MUTATION_UNAVAILABLE.format(reason=event.reason))
        elif isinstance(event, TurnBudgetExhausted):
            self._error(_budget_reason(event))
        elif isinstance(event, ErrorOccurred):
            self._error(event.message)
        elif isinstance(event, FilesChanged):
            self._flush_streams()
            self._close_line()
            self._console.print(
                f"[{theme.DIM}]{theme.ICON_STATUS} "
                f"{escape(messages.FILES_CHANGED.format(paths=_join_capped(event.paths)))}"
                f"[/{theme.DIM}]"
            )
        elif isinstance(event, VerificationPassed):
            self._verification_lines(event)
        elif isinstance(event, ChangesDigested):
            self._flush_streams()
            self._close_line()
            self._console.print(
                f"[{theme.DIM}]{theme.ICON_STATUS} {escape(messages.CHANGES_DIGEST_TITLE)}"
                f"[/{theme.DIM}]"
            )
            for line in event.lines:
                self._console.print(f"[{theme.DIM}]  {escape(line)}[/{theme.DIM}]", highlight=False)
        elif isinstance(event, NoFileChanges):
            # Rozet cevabı BÖLMEZ: akan metin önce kapatılır, olgu ardına düşer.
            self._flush_streams()
            self._close_line()
            self._console.print(
                f"[{theme.DIM}]{theme.ICON_STATUS} {escape(messages.NO_FILE_CHANGES)}[/{theme.DIM}]"
            )
        elif isinstance(event, FollowupsSuggested):
            self._followups(event)
        elif isinstance(event, TurnFinished):
            self._flush_streams()
            self._close_line()
            self._active_channel = None
            self._turn_opened = False
            self._fallbacks_shown.clear()
            self._finish_work()
        elif isinstance(event, TurnOutcome):
            self._turn_outcome(event)

    def _followups(self, event: FollowupsSuggested) -> None:
        """Sıradaki adımları turun ardına, numaralı ve sönük bas.

        Numara kozmetik değil: kullanıcı `/devam 2` gibi bir şey yazmasa da
        öneriyi tarif ederken ona atıfta bulunabiliyor. Cevabı BÖLMEZ — akan
        metin önce kapatılır.
        """
        if not event.items:
            return
        self._flush_streams()
        self._close_line()
        self._console.print(f"[{theme.DIM}]{escape(messages.FOLLOWUPS_TITLE)}[/{theme.DIM}]")
        for sira, (etiket, _gorev) in enumerate(event.items, start=1):
            self._console.print(f"[{theme.DIM}]  {sira}. {escape(etiket)}[/{theme.DIM}]")

    def print_user_message(self, text: str) -> None:
        """Kullanıcının mesajını Claude Code diziliminde `> metin` olarak bas.

        Claude Code'da kullanıcı sözü kasıtlı olarak sönüktür: asistanın çıktısı öne
        çıksın diye geri plana alınır. prompt_toolkit'in bıraktığı satır silinir
        (`erase_when_done`) ve yerine bu sönük satır çizilir. Etrafında bir boş satır
        bırakılır ki konuşma blokları birbirine yapışmasın.
        """
        self._end_block()
        line = Text(f"{theme.ICON_USER} ", style=theme.DIM)
        line.append(text, style=theme.DIM)
        self._console.print()
        self._console.print(line)
        self._console.print()

    def _turn_outcome(self, event: TurnOutcome) -> None:
        duration = format_duration(int(event.elapsed_s * 1000))
        if event.status == "completed":
            self._status(f"{theme.ICON_OK} {messages.TURN_COMPLETED.format(duration=duration)}")
        elif event.status == "partial":
            self._status(f"⚠ {messages.TURN_PARTIAL.format(duration=duration)}")
        else:
            self._error(messages.TURN_FAILED.format(duration=duration))

    def abort(self) -> None:
        """Tur iptal/hata ile bitti: canlı göstergeyi ANINDA durdur, özet BASMA.

        `TurnFinished` yayınlanmadan (Ctrl-C/esc ile) tur kesilirse çalışma göstergesinin
        Rich `Live`'ı durdurulmadan kalıyor ve "hazırlanıyor…" satırı dönmeye devam
        ediyordu. Burada gösterge kesin durdurulur, geri tutulan son parça boşaltılır ve
        yarım satır kapatılır. Normal bitişte `TurnFinished` zaten temizlediği için bu
        çağrı etkisizdir (idempotent)."""
        self._flush_streams()
        self._close_line()
        # Live'ı durdurur; iptal edilmiş turda süre/token özeti anlamlı değil, yok sayılır.
        self._work.finish()
        self._active_channel = None
        # Tur durumu SIFIRLANIR (`TurnFinished` gelmedi): bekleyen durum satırı sonraki
        # turun ilk çıktısında yanlış bağlamda basılıyor, `_turn_opened` açık kalırsa o
        # turun açılış beyanı 4 yerine 1 satıra kırpılıyordu (L1-22).
        self._pending_status = None
        self._turn_opened = False
        self._fallbacks_shown.clear()

    @contextlib.contextmanager
    def suspended(self) -> Iterator[None]:
        """Canlı çalışma göstergesini bir etkileşim boyunca duraklat.

        Prompter, kullanıcıya soru/onay sorarken terminali devralır. Live'ın
        yenileme iş parçacığı bu sırada durmazsa cevap istemini ve kullanıcının
        yazdığını sürekli siler. Bittiğinde gösterge kaldığı yerden sürer.
        """
        # Yarım model satırı (`_line_open`) KAPATILIR: onay paneli aynı satıra basılıyor ve
        # `Live` yeniden başlarken satırı siliyordu (L1-22). `_close_line` göstergeyi de
        # duraklatır.
        self._close_line()
        try:
            yield
        finally:
            self._work.resume()

    # -- Akış --------------------------------------------------------------- #

    def _preamble(self, channel: Channel, text: str) -> None:
        """Araç çağrısına eşlik eden öncü beyanı TEK SATIR olarak bas.

        Burada bir SINIRLAMA vardır, bir sınıflandırma değil. "Bu metin öncü mü
        yoksa erken bir teslim raporu mu" sorusunu cevaplamaya çalışmak, uzunluk
        eşiğine ya da metin kalıbına bakmak demekti; ikisi de dilin kendisidir ve
        iki yönde birden kırılır (uzun ama meşru bir öncü susturulur, kısa ama
        sahte bir "tamamlandı" geçer).

        Gösterimi sınırlamak bu ikilemi ortadan kaldırır: model araç çağrısının
        yanına dört başlıklı bir rapor yazsa bile ekrana ilk satırından fazlası
        çıkamaz, meşru öncü ise hiç zarar görmez. Kötü durumda uzun bir öncü
        kırpılır — iyi huylu bir başarısızlık.
        """
        temiz = strip_thinking(text, streaming=False).strip()
        if not temiz:
            return
        self._flush_status()
        self._close_line()
        if channel is not self._active_channel and channel in _CHANNEL_LABELS:
            self._channel_header(channel)
        for index, satir in enumerate(self._preamble_lines(temiz)):
            # İşaret YALNIZCA ilk satırda; devam satırları onun altına hizalanır.
            # Her satıra işaret koymak, tek bir beyanı üç ayrı beyan gibi gösteriyordu.
            isaret = theme.ICON_ANSWER if index == 0 else " "
            self._console.print(f"[{theme.DIM}]{isaret} {escape(satir)}[/{theme.DIM}]")
        self._turn_opened = True
        # Öncü satırı KENDİ işaretini basar; ana kanal başlığı ayrıca çizilirse
        # satır çift işaretle başlar. Kanal "açık" sayılmaz ki ardından gelen
        # gerçek cevap kendi başlığını alsın.
        self._active_channel = None

    def _preamble_lines(self, text: str) -> list[str]:
        """Öncü metni kaç satırda göstereceğine karar ver.

        Turun İLK öncüsü açılış beyanıdır ve daha geniş yer alır: kullanıcı isteğini
        verdikten sonra ilk gördüğü şey odur ve "ne yapacağım" cevabını taşır. Tek
        satıra kırpmak o cevabı cümlenin ortasında kesiyordu.

        Sonraki öncüler tek satır kalır: onlar adım duyurusudur ("şu dosyaya
        bakıyorum") ve ekranı kaplamamalıdır. Sınır yine bir SINIRLAMADIR,
        sınıflandırma değil — model açılışa koca bir rapor yazarsa da üç satırdan
        fazlası basılmaz.
        """
        limit = max(16, self._console.width - _RESULT_PREFIX)
        budce = _OPENING_LINES if not self._turn_opened else 1
        satirlar: list[str] = []
        for parca in (p.strip() for p in text.split("\n")):
            if not parca:
                continue
            # Sarma KELİME sınırında yapılır; ortadan kesmek beyanı okunmaz kılıyordu.
            for satir in textwrap.wrap(parca, width=limit) or [parca[:limit]]:
                if len(satirlar) == budce:
                    satirlar[-1] = _with_mark(satirlar[-1], limit)
                    return satirlar
                satirlar.append(satir)
        return satirlar

    def _write_stream(self, channel: Channel, text: str, *, complete: bool = False) -> None:
        if not text:
            return
        # Bekleyen durum satırı cevabın ÖNÜNE basılmalı; sıra bozulmamalı.
        self._flush_status()
        self._raw[channel] = self._raw.get(channel, "") + text
        if self._show_thinking:
            self._pump_thinking(channel, streaming=not complete)
            return
        visible = strip_thinking(self._raw[channel], streaming=not complete)
        shown = self._shown.get(channel, 0)
        if len(visible) <= shown:
            return  # gelen parça tamamen düşünme metniydi; basılacak bir şey yok

        fresh = visible[shown:]
        if channel is not self._active_channel:
            # Blok başındaki boşluk basılmaz: yalnız "\n" gelen akış ekrana boş bir
            # `⏺ ` bırakıyordu (ölçüldü, 30 Ekim). Boşluk "gösterildi" sayılır; gerçek
            # metin gelince işaret onunla birlikte açılır.
            fresh = fresh.lstrip()
            if not fresh:
                self._shown[channel] = len(visible)
                return
            self._close_line()
            self._channel_header(channel)
            self._active_channel = channel
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
        if self._show_thinking:
            for channel in self._raw:
                self._pump_thinking(channel, streaming=False)
        else:
            for channel, raw in self._raw.items():
                visible = strip_thinking(raw)
                shown = self._shown.get(channel, 0)
                if len(visible) > shown:
                    self._console.out(visible[shown:], end="", highlight=False)
                    self._line_open = not visible.endswith("\n")
        self._raw.clear()
        self._shown.clear()

    # -- Görünür düşünme akışı (opsiyonel) ---------------------------------- #

    def _pump_thinking(self, channel: Channel, *, streaming: bool) -> None:
        """`<think>` bloklarını gizlemek yerine sönük, görünür bir akış olarak bas.

        Ham tampon her seferinde sıralı parçalara ayrılır; yalnızca daha önce
        basılmamış kuyruk yazılır. Böylece düşünme ve cevap, geliş sırasını koruyarak
        farklı stillerle akar: düşünme sönük italik, cevap normal madde işaretiyle.
        """
        parts = segment(self._raw.get(channel, ""), streaming=streaming)
        shown = self._shown.get(channel, 0)
        cursor = 0
        for part in parts:
            start = cursor
            cursor += len(part.text)
            if cursor <= shown:
                continue
            fresh = part.text[max(0, shown - start) :]
            if not fresh:
                continue
            if part.is_thinking:
                self._emit_thinking(channel, fresh, new_block=start >= shown)
            else:
                self._emit_visible(channel, fresh)
        self._shown[channel] = cursor

    def _print_structured_reasoning(self, reasoning: str) -> None:
        """`ModelResult.reasoning`i `<think>` bloğuyla AYNI stille bas (bkz. `_emit_thinking`).

        `console.out(..., highlight=False)` KULLANILIR, `print()` DEĞİL: model
        metni `[köşeli parantez]` içerebilir ve `print()` bunu Rich markup
        sanıp yorumlar/bozar — `_write_stream`'deki aynı gerekçe geçerli.
        """
        self._close_line()
        self._console.print(
            f"[{theme.DIM}]{theme.ICON_SPARKLE} {messages.THINKING_HEADER}[/{theme.DIM}]"
        )
        self._console.out(reasoning.strip(), highlight=False, style=f"{theme.DIM} italic")
        self._active_channel = None

    def _emit_thinking(self, channel: Channel, fresh: str, *, new_block: bool) -> None:
        """Düşünme metnini sönük italik olarak bas; blok başında başlık koy."""
        if new_block:
            self._close_line()
            self._console.print(
                f"[{theme.DIM}]{theme.ICON_SPARKLE} {messages.THINKING_HEADER}[/{theme.DIM}]"
            )
            # Blok bittikten sonra cevap YENİDEN kendi madde işaretiyle başlamalı.
            self._active_channel = None
        self._console.out(fresh, end="", highlight=False, style=f"{theme.DIM} italic")
        self._line_open = not fresh.endswith("\n")

    def _emit_visible(self, channel: Channel, fresh: str) -> None:
        """Görünür cevabı normal stille bas (madde işareti / kanal başlığıyla)."""
        if channel is not self._active_channel:
            fresh = fresh.lstrip()  # blok başındaki boşluk boş `⏺ ` basar (bkz. `_write_stream`)
            if not fresh:
                return
            self._close_line()
            self._channel_header(channel)
            self._active_channel = channel
        self._console.out(fresh, end="", highlight=False)
        self._line_open = not fresh.endswith("\n")

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

    def _verification_lines(self, event: VerificationPassed) -> None:
        """Tur sonu kanıtı: geçenler tek satır, ölçülemeyenler nedeniyle ayrı satır."""
        self._flush_streams()
        self._close_line()
        if event.checks:
            checks = messages.VERIFICATION_PASSED.format(checks=" · ".join(event.checks))
            self._console.print(f"[{theme.OK}]{theme.ICON_OK} {escape(checks)}[/{theme.OK}]")
        if event.unmeasured:
            reasons = messages.VERIFICATION_UNMEASURED.format(reasons=" · ".join(event.unmeasured))
            self._console.print(
                f"[{theme.WARN}]{theme.ICON_STATUS} {escape(reasons)}[/{theme.WARN}]"
            )

    def _warn(self, message: str) -> None:
        """Sonucun yorumunu değiştiren UYARI: `--quiet` bile bunu yutmaz.

        Ölçüldü (30 Ekim): `show_progress=False` iken `_status` hiçbir şey basmıyor;
        "model dosya değiştiremez", yedeğe düşüş, bağlam sıkıştırma ve "kanıtlanmadı"
        uyarıları kayboluyor, kullanıcı salt-okunur bir turu "başarılı" sanıyordu
        (L1-23). İlerleme gürültüsü sessizleşir, uyarı sessizleşmez.
        """
        if self._show_progress:
            self._status(message)
            return
        self._flush_streams()
        self._close_line()
        self._end_block()
        self._console.print(f"[{theme.WARN}]{theme.ICON_STATUS} {escape(message)}[/{theme.WARN}]")

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
        """Çağrı özetini bas. Kimlik olarak ROL değil, cevabı veren MODEL yazılır.

        Rol adı yapılandırmadaki addır; yedeğe düşülse bile değişmez. Ayrıntı satırı
        rolü yazdığı sürece, seçilenden başka bir modelin çalıştığı hiçbir yerde
        görünmüyordu — hatalarda da: "agent · 429" hangi modelin kısıtlandığını
        söylemez, oysa NIM'de hız sınırı model başınadır.
        """
        result = event.result
        etiket = format_served_model(result.model, result.served_by) if result.model else event.role
        if result.ok:
            self._status(
                messages.MODEL_CALL_OK.format(
                    model=etiket,
                    duration=format_duration(result.latency_ms),
                    tokens=result.usage.total_tokens,
                )
            )
            return
        # Sağlayıcı hataları çok uzun olabiliyor; ekranı kaplamasın, özü görünsün.
        self._error(
            messages.MODEL_CALL_FAILED.format(
                model=etiket, error=summarize_error(result.error or "")
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

    def _effect_workflow_finished(self, event: EffectWorkflowFinished) -> None:
        """Deterministik workflow sonucunu kalıcı ve okunur bir kart olarak bas."""
        self._end_block()
        color = theme.OK if event.ok else theme.ERROR
        icon = theme.ICON_DONE if event.ok else theme.ICON_ERROR
        self._console.print()
        self._console.print(f"[{color}]{icon} {escape(event.title)}[/{color}]", highlight=False)
        preferred = (
            ("Repository", "repository"),
            ("Branch", "branch"),
            ("Commit", "commit"),
            ("Push", "push"),
            ("Local HEAD", "local_head"),
            ("Remote HEAD", "remote_head"),
            ("Doğrulama", "verification"),
            ("Workflow", "workflow_id"),
        )
        shown: set[str] = set()
        for label, key in preferred:
            value = event.details.get(key)
            if value in (None, ""):
                continue
            shown.add(key)
            self._console.print(
                f"  [{theme.DIM}]{label:<11}[/{theme.DIM}] {escape(str(value))}",
                highlight=False,
            )
        for key, value in event.details.items():
            if key in shown or value in (None, ""):
                continue
            self._console.print(
                f"  [{theme.DIM}]{escape(str(key)):<11}[/{theme.DIM}] {escape(str(value))}",
                highlight=False,
            )
        if event.message.strip():
            self._console.print()
            self._console.print(escape(event.message), highlight=False)
        self._console.print()

    # -- Agent araç kartı ---------------------------------------------------- #

    #: Araç sonucuna göre madde işaretinin RENGİ. Claude Code diziliminde glyph her
    #: durumda aynıdır (`⏺`); durumu renk taşır — reddedilme sarı, engellenme sönük.
    _OUTCOME_COLORS: ClassVar[dict[ToolOutcome, str]] = {
        ToolOutcome.OK: theme.OK,
        ToolOutcome.FAILED: theme.ERROR,
        ToolOutcome.DENIED: theme.WARN,
        ToolOutcome.BLOCKED: theme.DIM,
    }

    def _tool_executed(self, event: ToolExecuted) -> None:
        """Araç çağrısını Claude Code diziliminde bas: `⏺ çağrı` + `⎿ sonuç`/diff."""
        self._end_block()
        # Bilinmeyen sonuç (yeni `ToolOutcome` üyesi) KeyError ile turu düşürmez (L1-37).
        color = self._OUTCOME_COLORS.get(event.outcome, theme.DIM)
        cagri = _format_call(event.name, event.args)
        # highlight=False: Rich'in `ad(arg)`'ı Python çağrısı sanıp magentaya boyaması
        # engellenir; Claude Code araç adını düz/kalın gösterir, repr rengiyle değil.
        self._console.print(
            f"[{color}]{theme.ICON_BULLET}[/{color}] {escape(cagri)}", highlight=False
        )

        if event.diff is not None:
            self._tool_diff(event.diff)
            return
        self._tool_output(event.output)

    def _tool_output(self, output: str) -> None:
        """Araç sonucunu bas: tek satırlıksa tek satır, çok satırlıysa YAPISIYLA.

        Çok satırlı çıktı eskiden `\\n` yerine boşluk konarak tek satıra
        eziliyordu. `read_file` sonucu böyle görünüyordu:

            ⎿  1 { 2 "name": "ornek-proje", 3 "private": true, 4 "scripts": { 5 …

        Satır numaraları içerikle aynı görsel ağırlıkta akınca "4"ün numara mı
        yoksa verinin parçası mı olduğu ayırt edilemiyor. Dosyanın yapısı
        bilginin kendisidir; onu düzleştirmek bilgiyi yok eder.
        """
        lines = [line for line in output.splitlines() if line.strip()]
        if not lines:
            return
        # Sınır terminal genişliğinden TÜRETİLİR. Sabit bir sayı, bağlayıcı ve
        # girintinin kapladığı beş karakteri saymıyordu: uzun bir satır sarınca
        # `⎿` tek başına kalıyor ve içerik girintisiz alt satıra düşüyordu.
        limit = max(16, min(_RESULT_LIMIT, self._console.width - _RESULT_PREFIX))
        self._result_line(escape(_shorten(lines[0], limit)))
        if len(lines) == 1:
            return
        for line in lines[1:_RESULT_LINES]:
            self._console.print(
                f"     [{theme.DIM}]{escape(_shorten(line, limit))}[/{theme.DIM}]",
                highlight=False,
            )
        kalan = len(lines) - _RESULT_LINES
        if kalan > 0:
            self._console.print(
                f"     [{theme.DIM}]{escape(messages.RESULT_TRUNCATED.format(count=kalan))}"
                f"[/{theme.DIM}]",
                highlight=False,
            )

    def _result_line(self, body: str) -> None:
        """Araç sonucunu çağrıya `⎿` bağlayıcısıyla bağla (sönük tek satır)."""
        self._console.print(
            f"  [{theme.DIM}]{theme.ICON_RESULT}[/{theme.DIM}]  [{theme.DIM}]{body}[/{theme.DIM}]",
            highlight=False,
        )

    def _tool_diff(self, diff_text: str) -> None:
        """Diff'i `⎿ N ekleme, M silme` özeti + altında renkli blok olarak bas."""
        # Diff satırları da genişliğe kırpılır: sarma, sol oluğu (satır numarası ve
        # +/- işareti) kaybettiriyor ve devam satırı hizasız düşüyordu.
        rendered = render_diff(diff_text, width=max(20, self._console.width - 6))
        self._result_line(
            escape(messages.DIFF_SUMMARY.format(added=rendered.added, removed=rendered.removed))
        )
        # Diff gövdesi çağrının altına, bağlayıcının hizasına girintili oturur.
        self._console.print(Padding(rendered.body, (0, 0, 0, 5)))

    # -- Fusion sonucu ------------------------------------------------------- #

    def _fusion_result(self, result: FusionResult) -> None:
        self._end_block()
        render_fusion_result(self._console, result, show_all_answers=self._show_all_answers)


#: Araç sonucunda bir satırın kaplayabileceği en fazla karakter (üst sınır).
#: Gerçek sınır terminal genişliğinden türetilir; bkz. `_tool_output`.
_RESULT_LIMIT = 96
#: `⎿` bağlayıcısının ve devam satırı girintisinin kapladığı görünür karakter.
_RESULT_PREFIX = 5
#: Araç sonucundan gösterilecek en fazla satır.
#
# Claude Code okuma sonucunu satır satır gösterir ama ekranı da kaplatmaz.
# Sekiz satır, bir dosyanın ne olduğunu anlamaya yeter; gerisi "N satır daha"
# ile sayılır — kırpıldığı SÖYLENİR, sessizce yutulmaz.
_RESULT_LINES = 8

#: `FilesChanged` satırında tek tek yazılacak en fazla dosya.
_FILES_LISTED = 8

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

#: Öncü beyanın ekranda kaplayabileceği en fazla karakter.
#
# Bu bir sınıflandırma eşiği DEĞİLDİR (bkz. `_preamble`): metin uzun diye "sahte
# rapor" sayılmaz, yalnızca gösterimi tek satıra sığdırılır. Araç kartı sınırıyla
# (`_CALL_LIMIT`) aynı ailedendir ve aynı gerekçeyle `ui` katmanında yaşar —
# "ne kadarı gösterilir" bir sunum kararıdır, sağlayıcı kararı değil.
#: Turun İLK öncüsünün (açılış beyanı) kaplayabileceği en fazla satır.
#
# Kullanıcı isteğini verdikten sonra ilk gördüğü şey budur ve "ne yapacağım"
# cevabını taşır; tek satıra kırpmak o cevabı cümlenin ortasında kesiyordu.
_OPENING_LINES = 4
#: Kırpılan öncünün sonuna konan işaret. Kesme SÖYLENİR: cümle ortasında biten
#: bir plan, kullanıcıya modelin yarım konuştuğunu düşündürüyordu.
_TRUNCATED_MARK = "…"


def _format_call(name: str, args: Mapping[str, object]) -> str:
    """Araç çağrısını `ad(birincil argüman)` biçiminde göster.

    Eskiden ham `anahtar=değer` listesi basılıyordu ve 15 KB'lık `content` satırı tek
    başına doldurup diğer alanları ekrandan siliyordu — hangi dosyaya yazıldığı bile
    görünmüyordu. Artık "hangi dosya / hangi komut" sorusunun cevabı öne alınır.
    """
    anahtar = _PRIMARY_ARG.get(name)
    deger = args.get(anahtar) if anahtar else None
    bayraklar = [ad for ad in _FLAG_ARGS if args.get(ad) is True]
    ek = ", ".join(bayraklar)
    if isinstance(deger, str) and deger.strip():
        # Birincil argüman (yol/komut/url) boyuta ÇEVRİLMEZ: Ölçüldü (30 Ekim) 49+
        # karakterli yol ve komut `<N karakter>` görünüyor, `auto` modda çalışan
        # komut ekranda hiç okunamıyordu. Sığmazsa ORTADAN kısalır: yolun dosya adı
        # ve komutun sonu (`| sh` gibi) da görünür kalır.
        govde = " ".join(deger.split())
        oda = _CALL_LIMIT - len(name) - len("()") - (len(ek) + 2 if ek else 0)
        govde = _middle_shorten(govde, oda)
    else:
        govde = _fallback(args)
    if ek:
        govde = f"{govde}, {ek}" if govde else ek

    tek_satir = " ".join(f"{name}({govde})".split())
    if len(tek_satir) <= _CALL_LIMIT:
        return tek_satir
    # Kısaltırken kapanış parantezi KORUNUR: yarım kalan çağrı okunmuyor.
    return tek_satir[: _CALL_LIMIT - 2] + "…)"


def _join_capped(paths: Sequence[str], limit: int = _FILES_LISTED) -> str:
    """Yolları virgülle birleştir; `limit`ten fazlası `+M dosya daha` olur (L1-38).

    Yüzlerce dosya değiştiren tur tek satırda ekranı taşırıyordu.
    """
    if len(paths) <= limit:
        return ", ".join(paths)
    return f"{', '.join(paths[:limit])} {messages.FILES_MORE.format(count=len(paths) - limit)}"


def _middle_shorten(text: str, limit: int) -> str:
    """Uzun metni ortadan kısalt: baş ve son görünür, ortaya `…` konur."""
    if len(text) <= limit or limit < 5:
        return text
    bas = (limit - 1) // 2 + (limit - 1) % 2
    son = limit - 1 - bas
    return f"{text[:bas]}…{text[len(text) - son :]}"


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


def _with_mark(line: str, limit: int) -> str:
    """Kırpılan son satırın sonuna kesme işareti koy."""
    if line.endswith(_TRUNCATED_MARK):
        return line
    govde = line if len(line) + len(_TRUNCATED_MARK) <= limit else line[: limit - 1]
    return f"{govde}{_TRUNCATED_MARK}"


def _shorten(text: str, limit: int) -> str:
    """Uzun metni tek satıra sığdır. Araç kartı ekranı taşırmamalıdır."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _compression_line(event: ContextCompressed) -> str:
    """Bağlam kısaltma satırı; ekrana taşınacak bir kazanç yoksa boş.

    Ölçüldü (30 Ekim): "bağlam sıkıştırıldı (18 → 18 mesaj)" mesaj sayısı aynıyken
    anlamsızdı ve her model çağrısında basılıyordu. Kazanılan karakter varsa o, yoksa
    yalnız mesaj sayısı gerçekten düştüyse eski satır gösterilir.
    """
    if event.saved_chars > 0:
        bin_esigi = 1000
        miktar = (
            f"{round(event.saved_chars / bin_esigi)} bin"
            if event.saved_chars >= bin_esigi
            else str(event.saved_chars)
        )
        return messages.AGENT_CONTEXT_TRIMMED.format(amount=miktar)
    if event.after < event.before:
        return messages.AGENT_CONTEXT_COMPRESSED.format(before=event.before, after=event.after)
    return ""


def _budget_reason(event: TurnBudgetExhausted) -> str:
    """Bütçe durma sebebini kullanıcı metnine çevir.

    Metin motorda değil BURADA üretilir: motor yalnızca sebep kodunu bilir
    (RULES.md "UI ve CLI").
    """
    template = messages.AGENT_BUDGET_REASONS.get(event.reason)
    if template is None:
        return messages.AGENT_BUDGET_UNKNOWN.format(reason=event.reason)
    return template.format(
        model_calls=event.model_calls,
        tool_rounds=event.tool_rounds,
        idle_rounds=event.idle_rounds,
        elapsed_s=event.elapsed_s,
    )
