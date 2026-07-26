"""Oturum kurulumu — veriyolu, dinleyiciler ve sağlayıcı burada birleştirilir.

Tek bir görevi çalıştırmanın uçtan uca akışı budur. Faz 2'den itibaren burada
motorlar (fusion, agent) çağrılacak; kurulum akışı aynı kalacak.

Dikkat: bu dosya hiçbir şey BASMAZ. Kullanıcıya ne gösterileceğine dinleyiciler
karar verir; buradan yalnızca olay yayınlanır.
"""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from ..config.models import Config
from ..config.permissions import load_allowed_commands
from ..core.events import ErrorOccurred, EventSink, FusionCompleted, TurnFinished
from ..core.tools import ToolContext
from ..core.types import (
    CompletionRequest,
    FusionResult,
    Message,
    VerdictSource,
    is_rate_limit_error,
)
from ..engines.agent import AgentOutcome, run_agent
from ..engines.agent.approval import ApprovalMode, build_policy
from ..engines.agent.loop import AgentDeps
from ..engines.agent.verification import build_verifier
from ..engines.fusion import run_fusion
from ..memory.factory import Memory, build_memory, null_memory
from ..observability.bus import EventBus
from ..observability.cost import CostTracker
from ..observability.json_sink import JsonRenderer
from ..observability.tracing import LangfuseTracer
from ..tools.capabilities import CapabilityRegistry
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
    memory: Memory | None = None,
) -> FusionResult:
    """Görevi fusion motoruyla çalıştır ve sonucu döndür.

    Hata fırlatmaz: hiçbir aday yanıt veremezse `VerdictSource.NONE` ile döner ve
    kullanıcıya gösterilecek açıklama olay olarak yayınlanır.
    """
    async with EventBus() as bus:
        for sink in sinks:
            bus.subscribe(sink)

        store = memory or null_memory()
        _warn_if_unavailable(store, bus)
        result = await run_fusion(
            task,
            config,
            publisher=bus,
            task_type=task_type,
            synthesis=synthesis,
            memory=store.performance,
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
    task_type: str = "general",
    root: Path | None = None,
    interactive: bool | None = None,
    memory: Memory | None = None,
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
        store = memory or null_memory()
        _warn_if_unavailable(store, bus)
        tool_context = ToolContext(root=root or Path.cwd())
        deps = AgentDeps(
            config=config,
            publisher=bus,
            policy=build_policy(mode, prompter),
            tool_context=tool_context,
            asker=prompter if can_ask else None,
            code_index=store.code_index if store.enabled else None,
            lessons=store.lessons,
            capabilities=CapabilityRegistry(Path.home(), tool_context.root),
            allowed_commands=load_allowed_commands(tool_context.root),
            verifier=build_verifier(config, root=tool_context.root, tool_context=tool_context),
            task_type=task_type,
        )
        outcome = await run_agent(task, deps, plan_mode=mode is ApprovalMode.PLAN)

        if not outcome.final_text.strip():
            bus.publish(ErrorOccurred(messages.AGENT_EMPTY_ANSWER, fatal=True))
        elif not outcome.ok and is_rate_limit_error(outcome.final_text):
            # Agent turu kotaya takıldığında elde yalnızca ham sağlayıcı metni olur
            # ("...429 Too Many Requests..."); kullanıcı ne yapacağını bilemez.
            # Fusion yolundaki yönlendirmenin aynısı gösterilir.
            bus.publish(ErrorOccurred(messages.ERROR_RATE_LIMITED, fatal=False))
        bus.publish(TurnFinished())
        return outcome


def open_memory(config: Config, *, root: Path, enabled: bool = True) -> Memory:
    """Belleği aç. Kapalıysa ya da açılamıyorsa boş belleğe düşer."""
    return build_memory(config, root=root) if enabled else null_memory()


def _warn_if_unavailable(memory: Memory, bus: EventBus) -> None:
    """Bellek açılamadıysa kullanıcıya söyle — sessizce öğrenmemek kabul edilemez."""
    if memory.unavailable_reason is not None:
        bus.publish(
            ErrorOccurred(
                messages.MEMORY_UNAVAILABLE.format(reason=memory.unavailable_reason),
                fatal=False,
            )
        )


@dataclass(frozen=True, slots=True)
class Observers:
    """Bir turu izleyen dinleyiciler ve kapanışta yapılacaklar."""

    sinks: tuple[EventSink, ...]
    cost: CostTracker
    tracer: LangfuseTracer

    def finish(self) -> None:
        """Bekleyen izleme kayıtlarını gönder."""
        self.tracer.flush()


def build_observers(
    task: str, *, renderer: EventSink | None = None, as_json: bool = False
) -> Observers:
    """Turu izleyecek dinleyicileri kur.

    Sıra önemlidir: render önce gelir ki kullanıcı çıktıyı beklemesin. İzleme ve
    maliyet toplama sessizdir, ekrana bir şey basmaz.
    """
    cost = CostTracker()
    tracer = LangfuseTracer(task=task)
    sinks: list[EventSink] = []
    if as_json:
        sinks.append(JsonRenderer())
    elif renderer is not None:
        sinks.append(renderer)
    sinks.extend((cost, tracer))
    return Observers(sinks=tuple(sinks), cost=cost, tracer=tracer)
