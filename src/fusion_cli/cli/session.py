"""Oturum kurulumu — veriyolu, dinleyiciler ve sağlayıcı burada birleştirilir.

Tek bir görevi çalıştırmanın uçtan uca akışı budur. Faz 2'den itibaren burada
motorlar (fusion, agent) çağrılacak; kurulum akışı aynı kalacak.

Dikkat: bu dosya hiçbir şey BASMAZ. Kullanıcıya ne gösterileceğine dinleyiciler
karar verir; buradan yalnızca olay yayınlanır.
"""

from __future__ import annotations

from ..config.models import Config
from ..core.events import ErrorOccurred, EventSink, FusionCompleted, TurnFinished
from ..core.types import CompletionRequest, FusionResult, Message, VerdictSource
from ..engines.fusion import run_fusion
from ..observability.bus import EventBus
from ..ui import messages


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
