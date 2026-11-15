"""Ertelenen çağrının sürdürülen oturumda yeniden değerlendirilmesi (#114).

Claude Code: `-p`'de PreToolUse `defer` turu `stop_reason: tool_deferred` ile bitirir;
oturum sürdürülünce (`--resume`) aynı çağrı PreToolUse'tan yeniden geçer — kanca bu kez
`allow` derse araç çalışır, `defer` derse tur yine ertelenir, `deny` reddeder.

Fusion'da ertelenen çağrının geçmişteki sonucu `tool_deferred` metinli başarısız araç
mesajıdır. Kök turun ilk model çağrısından ÖNCE bu mesaj geçmişten çıkarılır ve çağrı
olağan araç yolundan (PreToolUse → onay → çalıştırma → PostToolUse) yeniden geçirilir;
yeni sonuç aynı yere konur, böylece model `tool_use`'un hemen ardından sonucunu görür.
"""

from __future__ import annotations

from ...core.types import Message, ToolCall
from .hook_bridge import TOOL_DEFERRED


def take_deferred(messages: list[Message]) -> tuple[int, ToolCall] | None:
    """Geçmişin sonundaki ertelenen çağrı: (sonucun yeri, çağrı); sonuç mesajı çıkarılır.

    Ertelemeden sonra modelin yeni bir araç turu açtığı geçmişte (çağrı zaten aşıldı)
    `None` döner; geçmiş değişmez.
    """
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.role == "assistant" and message.tool_calls:
            return None
        if _is_deferred(message):
            call = _call_for(messages[:index], message.tool_call_id)
            if call is None:
                return None
            del messages[index]
            return index, call
    return None


def _is_deferred(message: Message) -> bool:
    return message.role == "tool" and message.ok is False and message.content == TOOL_DEFERRED


def _call_for(earlier: list[Message], call_id: str | None) -> ToolCall | None:
    for message in reversed(earlier):
        if message.role != "assistant" or not message.tool_calls:
            continue
        return next((call for call in message.tool_calls if call.id == call_id), None)
    return None
