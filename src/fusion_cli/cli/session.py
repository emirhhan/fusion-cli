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
from ..core.concurrency import BackgroundTasks
from ..core.events import (
    ErrorOccurred,
    EventSink,
    FilesChanged,
    FusionCompleted,
    NoFileChanges,
    TurnFinished,
)
from ..core.health import HealthRegistry
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
    health: HealthRegistry | None = None,
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
            health=health,
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
    extra_roots: tuple[Path, ...] = (),
    history: list[Message] | None = None,
    background: BackgroundTasks | None = None,
    tool_context: ToolContext | None = None,
) -> AgentOutcome:
    """Görevi agent motoruyla (araçlar + onay + öz-denetim) çalıştır.

    `interactive` False ise `ask_user` aracı modele HİÇ sunulmaz: cevaplanamayacak
    soru sormak turu boşa harcar. `history` verilirse çok-turlu sohbet sürdürülür.

    `background` verilirse ders çıkarımı gibi tur SONRASI işler fire-and-forget çalışır
    ve cevabı bekletmez; verilmezse bu işler turu bloklar (gözlemlenen "ekstra gecikme").
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
        # Çağıran bir bağlam verdiyse O kullanılır. `/undo` turun değişiklik
        # kümesine erişebilmek zorundadır; bağlam burada gizlice kurulduğunda
        # çağıranın elinde hiçbir referans kalmıyor ve geri alma sessizce
        # işlevsiz kalıyordu (ölçüldü: TUI'de `/undo` her zaman "geri alınacak
        # değişiklik yok" diyordu, oysa dosyalar değişmişti).
        tool_context = tool_context or ToolContext(
            root=root or Path.cwd(),
            extra_roots=extra_roots,
            restrict_to_root=config.runtime.restrict_to_root,
        )
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
            background=background,
        )
        outcome = await run_agent(task, deps, history=history, plan_mode=mode is ApprovalMode.PLAN)

        # Boş cevap YALNIZCA tur temiz bittiyse hatadır. Bütçe dolduğunda ya da
        # kapı turu kestiğinde sebep ZATEN yayınlandı; ikinci bir "(model boş yanıt
        # verdi)" satırı basmak, açıklanmış bir durumu ikinci kez ve daha az
        # bilgiyle söylemekti.
        if not outcome.final_text.strip() and outcome.ok:
            bus.publish(ErrorOccurred(messages.AGENT_EMPTY_ANSWER, fatal=True))
        elif not outcome.ok and is_rate_limit_error(outcome.final_text):
            bus.publish(ErrorOccurred(messages.ERROR_RATE_LIMITED, fatal=False))
        elif not outcome.ok and not outcome.budget_stopped:
            # Bütçe durdurmasında sebep zaten yayınlandı; cevabı ikinci kez ve
            # hata kılığında basmak kendiyle çelişen satır üretir.
            bus.publish(ErrorOccurred(outcome.final_text, fatal=False))
        # Rozet yalnızca BAŞARILI turda anlamlıdır. Başarısız turda hata mesajı
        # zaten "değişiklik yapılmış kabul edilmemelidir" diyor; rozeti de basmak
        # aynı olguyu iki kez, iki farklı üslupla söylemekti ve kullanıcı ikincisini
        # yeni bilgi sanıyordu. Plan modunda değişiklik zaten yasaktır.
        if outcome.ok and outcome.made_no_changes and mode is not ApprovalMode.PLAN:
            bus.publish(NoFileChanges())
        elif tool_context.changes.paths:
            # Liste modelin hafızasından değil değişiklik kümesinden gelir.
            bus.publish(FilesChanged(_changed_names(tool_context)))
        bus.publish(TurnFinished())
        return outcome


def _changed_names(tool_context: ToolContext) -> tuple[str, ...]:
    """Değişen yolları kullanıcıya gösterilecek biçimde (köke göreli) ver."""
    from ..tools.files import display_path

    return tuple(display_path(tool_context, path) for path in tool_context.changes.paths)


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
