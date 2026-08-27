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
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from ..core.tools import ToolContext
from ..engines.agent.approval import ApprovalRequest
from ..engines.agent.engine_tools import QuestionOption
from ..tools.preview import preview_change
from ..ui import messages, theme

#: Onay sayılan cevaplar. Boş cevap (doğrudan Enter) da onaydır.
_AFFIRMATIVE = frozenset({"", "e", "evet", "y", "yes", "onayla"})


class ConsolePrompter:
    """Kullanıcıya terminalden soran onay/soru arayüzü."""

    def __init__(
        self,
        console: Console,
        tool_context: ToolContext,
        *,
        flush: Callable[[], Awaitable[None]] | None = None,
        suspend: Callable[[], AbstractContextManager[None]] | None = None,
    ) -> None:
        self._console = console
        self._tool_context = tool_context
        # Terminali devralmadan önce olay veriyolunu boşaltır. Bunsuz, doğrudan
        # yazdığımız onay paneli veriyolunda bekleyen satırlarla sırasız karışır.
        self._flush = flush
        # Terminali devralırken canlı çalışma göstergesini (Live "hazırlanıyor…")
        # duraklatır. Bunsuz Live'ın yenileme iş parçacığı cevap istemini ve
        # kullanıcının yazdığını her ~100ms'de siler; giriş yapılamaz görünür.
        self._suspend = suspend
        self._interactive = sys.stdin.isatty()

    async def confirm(self, request: ApprovalRequest) -> bool:
        with self._suspended():
            await self._drain()
            self._render_preview(request)
            if request.danger is not None:
                self._console.print(
                    f"[{theme.ERROR}]{messages.DANGER_WARNING.format(reason=request.danger)}"
                    f"[/{theme.ERROR}]"
                )
            answer = self._ask(messages.CONFIRM_QUESTION)
        # Boş cevap iki anlama gelir: kullanıcı Enter'a bastı (onay) ya da ortam
        # etkileşimsiz (cevap yok). İkincisinde onay varsaymak kabul edilemez.
        if not answer and not self._interactive:
            return False
        return _is_affirmative(answer)

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
                    return messages.NO_ANSWER_AVAILABLE
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

    def _ask(self, prompt: str) -> str:
        try:
            return Prompt.ask(prompt, console=self._console, default="", show_default=False)
        except (EOFError, KeyboardInterrupt, OSError):
            # Cevap alınamadı: stdin kapalı, yönlendirilmiş ya da yakalanmış olabilir
            # (CI, cron, boru hattı). `confirm` bunu REDDETME sayar — onay alınmadan
            # değiştirici işlem yapılamaz; `ask` ayrı bir açıklamaya çevirir.
            return ""


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
    for line in diff.splitlines():
        text.append(line + "\n", style=_diff_style(line))
    return text


def _diff_style(line: str) -> str:
    if line.startswith(("+++", "---")):
        return theme.DIM
    if line.startswith("+"):
        return theme.OK
    if line.startswith("-"):
        return theme.ERROR
    if line.startswith("@@"):
        return theme.INFO
    return "default"


def _is_affirmative(answer: str) -> bool:
    return answer.strip().lower() in _AFFIRMATIVE
