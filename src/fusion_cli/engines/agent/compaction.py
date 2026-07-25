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
from . import history

_PROMPT = (Path(__file__).parent / "prompts" / "compress.txt").read_text(encoding="utf-8")

#: Özet için ayrılan token bütçesi.
SUMMARY_MAX_TOKENS = 600


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
    trace = history.transcript(old, limit=6_000)
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
        hedge_delay_s=config.runtime.hedge_delay_s,
        background=True,
    )
    result = await provider.complete(request)
    return result.text.strip() if result.ok else ""
