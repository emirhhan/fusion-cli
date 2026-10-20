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
    messages: list[Message],
    *,
    config: Config,
    publisher: EventPublisher | None = None,
    threshold_chars: int | None = None,
) -> list[Message]:
    """Geçmiş eşiği aştıysa eski kısmı özetle. Aksi halde aynen döndür."""
    if not history.needs_compression(messages, threshold_chars=threshold_chars):
        return messages

    cut = history.safe_cut(messages)
    if cut == 0:
        return messages

    # Kök tur (sistem mesajı + ilk kullanıcı sorusu) özetleyiciye asla verilmez.
    # Ölçüldü ("MAVİ-KEDİ" vakası): kesim sistem mesajını ve kullanıcının kök
    # turda söylediği talimatı da `old`'a alıyor, özetleyici o ayrıntıyı hiç
    # yazmayabiliyordu — bilgi telafisiz kayboluyordu. Kök tur burada anchor
    # olarak ayrılır ve `recent` gibi BİREBİR korunur.
    anchor_len = history.root_anchor_length(messages)
    anchor, old, recent = messages[:anchor_len], messages[anchor_len:cut], messages[cut:]
    if not old:
        return messages
    trace = history.transcript(old, limit=TRACE_CHARS)
    if not trace.strip():
        return messages

    summary = await _summarize(trace, config, publisher)
    if not summary:
        return messages
    return [*anchor, Message("user", f"[önceki konuşmanın özeti]\n{summary}"), *recent]


async def compact_in_turn(
    messages: list[Message],
    *,
    config: Config,
    publisher: EventPublisher | None = None,
    threshold_chars: int,
) -> list[Message]:
    """Tur SÜRERKEN bağlamı eşiğin altına indir: önce eski çıktılar, sonra özet.

    Claude Code'un belgelenmiş sırası: "önce eski araç çıktılarını temizler,
    gerekirse sonra konuşmayı özetler; istekleriniz ve önemli kod parçaları
    korunur". Sistem mesajı ve görev (`task_anchor_length`) hiç özetlenmez.
    Özet üretilemezse yalnız temizlenmiş liste döner.
    """
    if not history.needs_compression(messages, threshold_chars=threshold_chars):
        return messages
    temiz = history.clear_old_tool_outputs(messages, threshold_chars)
    if not history.needs_compression(temiz, threshold_chars=threshold_chars):
        return temiz
    anchor_len = history.task_anchor_length(temiz)
    cut = _summary_cut(temiz, anchor_len)
    if cut <= anchor_len:
        return temiz
    anchor, old, recent = temiz[:anchor_len], temiz[anchor_len:cut], temiz[cut:]
    trace = history.transcript(old, limit=TRACE_CHARS)
    if not trace.strip():
        return temiz
    summary = await _summarize(trace, config, publisher)
    if not summary:
        return temiz
    ozet = Message("user", f"[önceki adımların özeti]\n{summary}", harness_note=True)
    return [*anchor, ozet, *recent]


def _summary_cut(messages: list[Message], anchor_len: int) -> int:
    """Özetlenecek aralığın sonu: olabildiğince çok son adımı koru, ama bir şey özetle.

    Önce olağan pencere (`KEEP_RECENT_MESSAGES`) denenir; tur kısa ama çıktıları
    büyükse pencere daraltılır. En az son araç turu (çağrı + sonuç) birebir kalır.
    """
    pencere = history.KEEP_RECENT_MESSAGES
    while pencere >= 2:
        cut = history.round_cut(messages, keep_recent=pencere)
        if cut > anchor_len:
            return cut
        pencere //= 2
    return 0


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
