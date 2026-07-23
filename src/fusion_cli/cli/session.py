"""Oturum kurulumu — veriyolu, dinleyiciler ve sağlayıcı burada birleştirilir.

Tek bir görevi çalıştırmanın uçtan uca akışı budur. Faz 2'den itibaren burada
motorlar (fusion, agent) çağrılacak; kurulum akışı aynı kalacak.

Dikkat: bu dosya hiçbir şey BASMAZ. Kullanıcıya ne gösterileceğine dinleyiciler
karar verir; buradan yalnızca olay yayınlanır.
"""

from __future__ import annotations

from ..config.models import Config
from ..core.events import ErrorOccurred, EventSink, StatusChanged, TurnFinished
from ..core.types import CompletionRequest, ModelResult, StreamDone
from ..observability.bus import EventBus
from ..providers.factory import build_provider
from ..providers.litellm_provider import build_messages
from ..ui import messages


def build_request(task: str, config: Config) -> CompletionRequest:
    """Görev metnini yapılandırmadaki çalışma zamanı ayarlarıyla isteğe çevir."""
    runtime = config.runtime
    return CompletionRequest(
        messages=build_messages(task),
        temperature=runtime.temperature,
        max_tokens=runtime.max_tokens,
        timeout_s=runtime.request_timeout_s,
        max_retries=runtime.max_retries,
    )


async def run_task(task: str, config: Config, *, sinks: tuple[EventSink, ...]) -> ModelResult:
    """Görevi tek modelle akıtarak çalıştır ve sonucu döndür.

    Hata fırlatmaz: başarısızlık `ModelResult(ok=False)` ile döner ve kullanıcıya
    gösterilecek açıklama olay olarak yayınlanır.
    """
    async with EventBus() as bus:
        for sink in sinks:
            bus.subscribe(sink)

        provider = build_provider(config.agent, publisher=bus)
        bus.publish(StatusChanged(messages.STATUS_THINKING))

        result: ModelResult | None = None
        async for item in provider.stream(build_request(task, config)):
            if isinstance(item, StreamDone):
                result = item.result

        result = result or _no_result(config)
        if not result.ok:
            bus.publish(ErrorOccurred(_failure_message(result), fatal=True))
        bus.publish(TurnFinished())
        return result


def _no_result(config: Config) -> ModelResult:
    """Akış hiç `StreamDone` üretmeden bittiyse (sağlayıcı beklenmedik davrandı)."""
    return ModelResult(
        name=config.agent.name,
        model=config.agent.model,
        text="",
        latency_ms=0,
        ok=False,
        error=messages.ERROR_NO_ANSWER,
    )


def _failure_message(result: ModelResult) -> str:
    return messages.ERROR_RATE_LIMITED if result.is_rate_limited else messages.ERROR_NO_ANSWER
