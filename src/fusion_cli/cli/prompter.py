"""Terminal onay ve soru arayüzü.

Motor ile kullanıcı arasındaki tek etkileşim noktası. Motor `Prompter`/`UserAsker`
protokollerini görür, Rich'i görmez.

Onay ekranı DAİMA önizleme gösterir: diff ya da çalıştırılacak komut. Kullanıcı neyi
onayladığını görmeden evet dememelidir.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from ..core.tools import ToolContext
from ..engines.agent.approval import ApprovalAnswer, ApprovalReply, ApprovalRequest
from ..engines.agent.auto_switch import AUTO_SWITCH_WORDS
from ..engines.agent.engine_tools import QuestionOption
from ..tools.preview import preview_change
from ..ui import messages, theme
from ..ui.chrome_site_labels import site_host, site_session_hint
from ..ui.diff import diff_lines
from .desktop_never import AppDenials

#: Onay sayılan cevaplar. Boş cevap (doğrudan Enter) yalnız sıradan onayda onaydır;
#: tehlikeli (geri alınamaz) işlemde varsayılan HAYIR'dır (L1-01).
_AFFIRMATIVE = frozenset({"e", "evet", "y", "yes", "onayla"})
#: "Bir daha sorma" (kalıcı izin kuralı, P-003) sayılan cevaplar.
_ALWAYS = frozenset({"k", "kalici", "kalıcı", "always", "a"})
#: Oturum izni (yalnız hatırlanabilen istekte; ör. masaüstü uygulama onayı, P-007).
_SESSION = frozenset({"o", "oturum", "session"})


class ConsolePrompter:
    """Kullanıcıya terminalden soran onay/soru arayüzü."""

    def __init__(
        self,
        console: Console,
        tool_context: ToolContext,
        *,
        flush: Callable[[], Awaitable[None]] | None = None,
        suspend: Callable[[], AbstractContextManager[None]] | None = None,
        denials: AppDenials | None = None,
    ) -> None:
        self._console = console
        #: Masaüstü onayında "Her zaman reddet" (`r`, P-007); yazımı sahip bağlar.
        self._denials = denials or AppDenials()
        self._tool_context = tool_context
        # Terminali devralmadan önce olay veriyolunu boşaltır. Bunsuz, doğrudan
        # yazdığımız onay paneli veriyolunda bekleyen satırlarla sırasız karışır.
        self._flush = flush
        # Terminali devralırken canlı çalışma göstergesini (Live "hazırlanıyor…")
        # duraklatır. Bunsuz Live'ın yenileme iş parçacığı cevap istemini ve
        # kullanıcının yazdığını her ~100ms'de siler; giriş yapılamaz görünür.
        self._suspend = suspend
        self._interactive = sys.stdin.isatty()

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer | ApprovalReply:
        denied = self._denials.short_circuit(request)
        if denied is not None:
            return denied
        with self._suspended():
            await self._drain()
            if request.agent_label:
                self._console.print(
                    f"[{theme.INFO}]"
                    f"{escape(messages.APPROVAL_AGENT_LABEL.format(agent=request.agent_label))}"
                    f"[/{theme.INFO}]"
                )
            self._render_preview(request)
            if request.danger is not None:
                self._console.print(
                    f"[{theme.ERROR}]{escape(messages.DANGER_WARNING.format(reason=request.danger))}"
                    f"[/{theme.ERROR}]"
                )
            elif request.note:
                self._console.print(f"[{theme.DIM}]{escape(request.note)}[/{theme.DIM}]")
            if request.desktop_target is not None:
                line = messages.BILGISAYAR_APPROVAL_TARGET.format(
                    app=request.desktop_target.app, level=request.desktop_target.level.label
                )
                self._console.print(f"[{theme.INFO}]{escape(line)}[/{theme.INFO}]")
            if request.rule:
                self._console.print(
                    f"[{theme.DIM}]{escape(messages.APPROVAL_RULE_NOTE.format(rule=request.rule))}[/{theme.DIM}]"
                )
            is_dangerous = request.danger is not None
            if self._interactive:
                # `k` yalnız kalıcılaştırılabilen istekte kural yazar; ötekinde ipucu verilmez
                # (ölçüldü, 31 Ekim: yıkıcı istekte de gösteriliyor, `k` sıradan evet sayılıyordu).
                hint = (
                    messages.CONFIRM_NOTE_HINT
                    if request.can_persist
                    else messages.CONFIRM_NOTE_HINT_NO_PERSIST
                )
                self._console.print(f"[{theme.DIM}]{escape(hint)}[/{theme.DIM}]")
                if request.offers_auto:
                    auto_hint = messages.CONFIRM_AUTO_SWITCH_HINT
                    self._console.print(f"[{theme.DIM}]{escape(auto_hint)}[/{theme.DIM}]")
                target = request.desktop_target
                if target is not None and request.consent_key is not None:
                    session_hint = messages.BILGISAYAR_CONFIRM_SESSION_HINT.format(app=target.app)
                    self._console.print(f"[{theme.DIM}]{escape(session_hint)}[/{theme.DIM}]")
                host = site_host(request)
                if host is not None and request.can_remember:
                    site_hint = site_session_hint(request)
                    self._console.print(f"[{theme.DIM}]{escape(site_hint)}[/{theme.DIM}]")
            answer = self._ask(
                messages.CONFIRM_QUESTION_DANGER if is_dangerous else messages.CONFIRM_QUESTION
            )
        # Boş cevap iki anlama gelir: kullanıcı Enter'a bastı (onay) ya da ortam
        # etkileşimsiz (cevap yok). İkincisi kullanıcının REDDİ değildir — kimseye
        # SORULAMADI; bunu insanın "hayır" demesiyle aynı saymak, hiç sorulmamış
        # bir kararı kullanıcıya mal ederdi (bkz. `ApprovalAnswer.UNAVAILABLE`).
        if answer is None or (not answer and not self._interactive):
            return ApprovalAnswer.UNAVAILABLE
        return parse_console_answer(answer, request, enter_approves=not is_dangerous)

    async def ask(
        self,
        question: str,
        options: tuple[QuestionOption, ...] = (),
        recommended: str | None = None,
    ) -> str:
        with self._suspended():
            await self._drain()
            self._console.print(
                Panel(
                    question, title=f"[bold]{messages.AGENT_ASKS}[/bold]", border_style=theme.INFO
                )
            )
            if options and self._interactive:
                from ..ui.picker import Choice, pick

                choices = [
                    Choice(
                        option.label,
                        option.label,
                        _option_description(option, recommended),
                    )
                    for option in options
                ]
                choices.append(Choice("__other__", messages.ASK_OTHER, messages.ASK_OTHER_DESC))
                selected = pick(choices, title=question)
                if selected is None:
                    # Esc: ortam etkileşimli, kullanıcı KASITLI vazgeçti (L1-19).
                    return messages.ASK_DECLINED
                if selected != "__other__":
                    return selected
            answer = self._ask(messages.ANSWER_PROMPT)
        # Etkileşimsiz ortamda "hayır" demek yanlış olur: bu bir evet/hayır sorusu
        # değil, serbest metinli bir sorudur. Model cevap alamadığını bilmelidir.
        return answer or messages.NO_ANSWER_AVAILABLE

    def _suspended(self) -> AbstractContextManager[None]:
        """Etkileşim boyunca canlı göstergeyi duraklatan bağlam.

        Gösterge bağlanmamışsa (test, boru hattı) hiçbir şey yapmaz.
        """
        return self._suspend() if self._suspend is not None else contextlib.nullcontext()

    async def _drain(self) -> None:
        if self._flush is not None:
            await self._flush()

    # ----------------------------------------------------------------------- #

    def _render_preview(self, request: ApprovalRequest) -> None:
        preview = preview_change(request.tool.name, request.args, self._tool_context)
        title = messages.APPROVAL_TITLE.format(tool=request.tool.name)
        body = (
            _colorize_diff(preview)
            if preview is not None and request.tool.name != "run_shell"
            else Text(preview or _summarize(request), style="bold")
        )
        self._console.print(Panel(body, title=title, border_style=theme.WARN))

    def _ask(self, prompt: str) -> str | None:
        try:
            return Prompt.ask(prompt, console=self._console, default="", show_default=False)
        except (EOFError, KeyboardInterrupt, OSError):
            # Okuma hatası, kullanıcının bilinçli boş Enter cevabından ayrıdır.
            # `confirm` UNAVAILABLE döndürür; bu ne izin ne insanın reddidir.
            return None


def _summarize(request: ApprovalRequest) -> str:
    pairs = ", ".join(f"{key}={value!r}" for key, value in request.args.items())
    return f"{request.tool.name}({pairs})"


def _option_description(option: QuestionOption, recommended: str | None) -> str:
    parts = [option.description] if option.description else []
    if option.label == recommended:
        parts.append(messages.ASK_RECOMMENDED)
    return " · ".join(parts)


def _colorize_diff(diff: str) -> Text:
    """Unified diff'i renklendir: eklenen yeşil, silinen kırmızı, başlık soluk."""
    text = Text()
    for line, is_file_header in diff_lines(diff):
        text.append(line + "\n", style=_diff_style(line, is_file_header=is_file_header))
    return text


def _diff_style(line: str, *, is_file_header: bool = False) -> str:
    if is_file_header:
        return theme.DIM
    if line.startswith("+"):
        return theme.OK
    if line.startswith("-"):
        return theme.ERROR
    if line.startswith("@@"):
        return theme.INFO
    return "default"


def parse_console_answer(
    answer: str, request: ApprovalRequest, *, enter_approves: bool = True
) -> bool | ApprovalAnswer | ApprovalReply:
    """Terminal cevabını karara çevir.

    İlk sözcük karardır; kalanı kullanıcının NOTUDUR (P-013): `h bunun yerine pytest kullan`
    reddi gerekçesiyle modele iletir. `k` kalıcı izin kuralı yazar (P-003); yıkıcı ya da
    kalıcılaştırılamayan istekte sıradan "evet" sayılır.
    """
    head, _, note = answer.strip().partition(" ")
    word = head.lower()
    if request.desktop_target is not None and request.consent_key is not None:
        # Uygulama onayı (#426, #452): yalnız "bu oturum için izin ver" ya da "reddet".
        if word in _SESSION or _is_affirmative(word, enter_approves=enter_approves):
            return ApprovalAnswer.SESSION
        return ApprovalReply(False, note.strip()) if note.strip() else False
    if word in _ALWAYS:
        return ApprovalAnswer.ALWAYS if request.can_persist else True
    if word in _SESSION and request.can_remember:
        return ApprovalAnswer.SESSION
    if word in AUTO_SWITCH_WORDS and request.offers_auto:
        return ApprovalAnswer.AUTO
    decision = _is_affirmative(word, enter_approves=enter_approves)
    if not decision and note.strip():
        return ApprovalReply(False, note.strip())
    return decision


def _is_affirmative(answer: str, *, enter_approves: bool = True) -> bool:
    normalized = answer.strip().lower()
    if not normalized:
        return enter_approves
    return normalized in _AFFIRMATIVE
