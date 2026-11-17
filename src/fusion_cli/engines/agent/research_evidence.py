"""Araştırma kanıtını araç penceresinden bağımsız, sınırlı bütçeyle koruma."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace

from ...core.types import Message

RESEARCH_TOOLS = frozenset({"web_fetch", "web_search"})
#: Araştırma metinlerine ayrılan toplam pay; bütün geçmişin sınırsız büyümesini önler.
RESEARCH_EVIDENCE_CHARS = 16_000
EVIDENCE_ELISION = "\n[… kaynak metni örneklendi; tam kanıt için kaynağı yeniden oku …]\n"


def is_research_result(message: Message) -> bool:
    """Başarılı kaynak okumaları/sorguları genel yeniden üretilebilir çıktı değildir."""
    return message.role == "tool" and message.name in RESEARCH_TOOLS and message.ok is not False


def evidence_metadata_chars(messages: Sequence[Message]) -> int:
    """Kaynak çağrısının URL/kimlik/araç adı ve sonuç zarfını da bütçeye kat."""
    sources = [message for message in messages if is_research_result(message)]
    identifiers = {message.tool_call_id for message in sources}
    calls = [call for message in messages for call in message.tool_calls if call.id in identifiers]
    metadata: list[dict[str, str | None]] = [
        {"id": call.id, "name": call.name, "arguments": call.arguments} for call in calls
    ]
    metadata.extend(
        {"tool_call_id": message.tool_call_id, "name": message.name} for message in sources
    )
    return sum(len(json.dumps(item, ensure_ascii=False)) for item in metadata)


def can_bound_evidence(messages: Sequence[Message]) -> bool:
    """Her kaynak için açık örnekleme notu bile sığmıyorsa kayıplı sıkıştırmayı reddet."""
    sources = [message for message in messages if is_research_result(message)]
    available = RESEARCH_EVIDENCE_CHARS - evidence_metadata_chars(messages)
    if sum(len(message.content) for message in sources) <= available:
        return True
    minimum_share = len(EVIDENCE_ELISION) + 2
    return available >= len(sources) * minimum_share


def bounded_evidence(messages: Sequence[Message]) -> dict[int, Message]:
    """Kaynak metni VE kimliği için ortak bütçe; sığmıyorsa girdi değişmeden kalır.

    Boş eşleme kaynak silme talimatı değildir: çağıran özgün geçmişi korur; sıkıştırma
    bu durumda bağlam bütçesi kapısına kontrolü geri verir.
    """
    sources = [
        (index, message) for index, message in enumerate(messages) if is_research_result(message)
    ]
    if not sources or not can_bound_evidence(messages):
        return {}
    available = RESEARCH_EVIDENCE_CHARS - evidence_metadata_chars(messages)
    if sum(len(message.content) for _, message in sources) <= available:
        return {index: replace(message, images=()) for index, message in sources}
    share = available // len(sources)
    retained = {}
    for index, message in sources:
        content = message.content
        if len(content) > share:
            excerpt_chars = share - len(EVIDENCE_ELISION)
            head = excerpt_chars // 2
            tail = excerpt_chars - head
            content = content[:head] + EVIDENCE_ELISION + content[-tail:]
        retained[index] = replace(message, content=content, images=())
    return retained
