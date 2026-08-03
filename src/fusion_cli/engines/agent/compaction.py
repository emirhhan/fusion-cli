"""Bağlam sıkıştırma — uzun oturumların bağlam limitine çarpmasını önler.

Eski turlar tek bir özet notuna indirilir, son turlar birebir korunur. Özet
üretilemezse geçmiş DEĞİŞTİRİLMEZ: yarım bir özet, hiç özetten kötüdür.
"""

from __future__ import annotations

from pathlib import Path

from ...config.models import Config
from ...core.events import EventPublisher
from ...core.types import CompletionRequest, Message
from ...providers.factory import build_provider
from ...providers.web_registry import web_registry_for
from . import history

_PROMPT = (Path(__file__).parent / "prompts" / "compress.txt").read_text(encoding="utf-8")

#: Özet için ayrılan token bütçesi.
#:
#: Sıkıştırma eşiği yükseldiği için özetlenen geçmiş de büyüdü; 600 token artık atılan
#: içeriği temsil edemezdi.
SUMMARY_MAX_TOKENS = 2_000
#: Özetleyiciye verilecek oturum izinin uzunluğu.
#:
#: Eskiden 6.000 karakterdi. Eşik 177.000 karaktere çıkınca özetleyici, attığı geçmişin
#: ancak %3'ünü görüyor olurdu — özet yalnızca gördüğü kadarını temsil eder.
TRACE_CHARS = 60_000


async def compress(
    messages: list[Message], *, config: Config, publisher: EventPublisher | None = None
) -> list[Message]:
    """Geçmiş eşiği aştıysa eski kısmı özetle. Aksi halde aynen döndür."""
    if not history.needs_compression(messages):
        return messages

    cut = history.safe_cut(messages)
    if cut == 0:
        return messages

    old, recent = messages[:cut], messages[cut:]
    trace = history.transcript(old, limit=TRACE_CHARS)
    if not trace.strip():
        return messages

    summary = await _summarize(trace, config, publisher)
    if not summary:
        return messages
    return [Message("user", f"[önceki konuşmanın özeti]\n{summary}"), *recent]


async def _summarize(trace: str, config: Config, publisher: EventPublisher | None) -> str:
    request = CompletionRequest(
        messages=(Message("user", _PROMPT.replace("{trace}", trace)),),
        temperature=config.runtime.utility_temperature,
        max_tokens=SUMMARY_MAX_TOKENS,
        timeout_s=config.runtime.request_timeout_s,
        max_retries=config.runtime.max_retries,
    )
    # Arka plan işi: gösterilmez ama muhasebeye girer.
    provider = build_provider(
        config.judge,
        publisher=publisher,
        retry_delays_s=config.runtime.retry_delays_s,
        background=True,
        web_sessions=web_registry_for(config),
    )
    result = await provider.complete(request)
    return result.text.strip() if result.ok else ""
