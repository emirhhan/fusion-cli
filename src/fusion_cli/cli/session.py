"""Oturum kurulumu — veriyolu, dinleyiciler ve sağlayıcı burada birleştirilir.

Tek bir görevi çalıştırmanın uçtan uca akışı budur. Faz 2'den itibaren burada
motorlar (fusion, agent) çağrılacak; kurulum akışı aynı kalacak.

Dikkat: bu dosya hiçbir şey BASMAZ. Kullanıcıya ne gösterileceğine dinleyiciler
karar verir; buradan yalnızca olay yayınlanır.
"""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ..config.models import Config
from ..core.events import ErrorOccurred, EventSink, FusionCompleted, TurnFinished
from ..core.tools import ToolContext
from ..core.types import CompletionRequest, FusionResult, Message, VerdictSource
from ..engines.agent import AgentOutcome, run_agent
from ..engines.agent.approval import ApprovalMode, build_policy
from ..engines.agent.loop import AgentDeps
from ..engines.fusion import run_fusion
from ..observability.bus import EventBus
from ..ui import messages

if TYPE_CHECKING:  # pragma: no cover - yalnızca tip denetimi için
    from ..engines.agent.approval import Prompter
    from ..engines.agent.engine_tools import UserAsker

    class AgentPrompter(Prompter, UserAsker, Protocol):
        """Hem onay soran hem soru sorabilen arayüz (terminal uygulaması ikisini de yapar)."""

    #: Veriyolu boşaltma fonksiyonunu alıp prompter üreten fabrika.
    PrompterFactory = Callable[[Callable[[], Awaitable[None]]], AgentPrompter]


def build_request(task: str, config: Config) -> CompletionRequest:
    """Görev metnini yapılandırmadaki çalışma zamanı ayarlarıyla isteğe çevir."""
    runtime = config.runtime
    return CompletionRequest(
        messages=(Message("user", task),),
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        timeout_s=runtime.request_timeout_s,
        max_retries=runtime.max_retries,
    )


async def run_task(
    task: str,
    config: Config,
    *,
    sinks: tuple[EventSink, ...],
    task_type: str = "general",
    synthesis: bool | None = None,
) -> FusionResult:
    """Görevi fusion motoruyla çalıştır ve sonucu döndür.

    Hata fırlatmaz: hiçbir aday yanıt veremezse `VerdictSource.NONE` ile döner ve
    kullanıcıya gösterilecek açıklama olay olarak yayınlanır.
    """
    async with EventBus() as bus:
        for sink in sinks:
            bus.subscribe(sink)

        result = await run_fusion(
            task, config, publisher=bus, task_type=task_type, synthesis=synthesis
        )
        if result.source is VerdictSource.NONE:
            bus.publish(ErrorOccurred(_failure_message(result), fatal=True))
        else:
            bus.publish(FusionCompleted(result))
        bus.publish(TurnFinished())
        return result


def _failure_message(result: FusionResult) -> str:
    """Tüm adaylar başarısızsa: hız sınırı mı, genel bir sorun mu?"""
    if any(candidate.is_rate_limited for candidate in result.candidates):
        return messages.ERROR_RATE_LIMITED
    return messages.ERROR_NO_ANSWER


async def run_agent_task(
    task: str,
    config: Config,
    *,
    sinks: tuple[EventSink, ...],
    prompter_factory: PrompterFactory,
    mode: ApprovalMode = ApprovalMode.AUTO,
    root: Path | None = None,
    interactive: bool | None = None,
) -> AgentOutcome:
    """Görevi agent motoruyla (araçlar + onay + öz-denetim) çalıştır.

    `interactive` False ise `ask_user` aracı modele HİÇ sunulmaz: cevaplanamayacak
    soru sormak turu boşa harcar.
    """
    can_ask = sys.stdin.isatty() if interactive is None else interactive

    async with EventBus() as bus:
        for sink in sinks:
            bus.subscribe(sink)

        # Prompter veriyolunu tanır: terminali devralmadan önce bekleyen olayları
        # boşaltır, böylece onay paneli akan çıktının ortasına düşmez.
        prompter = prompter_factory(bus.drain)
        tool_context = ToolContext(root=root or Path.cwd())
        deps = AgentDeps(
            config=config,
            publisher=bus,
            policy=build_policy(mode, prompter),
            tool_context=tool_context,
            asker=prompter if can_ask else None,
        )
        outcome = await run_agent(task, deps, plan_mode=mode is ApprovalMode.PLAN)

        if not outcome.final_text.strip():
            bus.publish(ErrorOccurred(messages.AGENT_EMPTY_ANSWER, fatal=True))
        bus.publish(TurnFinished())
        return outcome
