"""MCP bağlantı başarısızlığını kullanıcıya TEK satırda söyle (sunucu adı + kısa neden).

Ölçüldü (30 Ekim): başlangıçta iki kez ham "MCP bağlantısı kurulamadı" basılıyor,
hangi sunucunun ve neden düştüğü yazmıyordu. Havuz aynı başarısızlığı oturumda bir
kez bildirir (`McpToolPool.take_new_failures`); burada yalnız biçimlenir.
"""

from __future__ import annotations

from ..config.models import McpServerConfig
from ..ui import messages

#: Nedenin ekrana taşınan azami uzunluğu; ayrıntı Bağlantılar ekranındadır.
_REASON_MAX_CHARS = 110


def short_reason(message: str) -> str:
    """Eylem önerisi taşıyan uzun mesajın yalnız ilk cümlesi, tek satıra sığacak kadar."""
    first = message.strip().split(". ", 1)[0].rstrip(".")
    if len(first) > _REASON_MAX_CHARS:
        first = first[: _REASON_MAX_CHARS - 1].rstrip() + "…"
    return first or messages.MCP_SERVER_REASON_UNKNOWN


def new_failure_lines(configs: tuple[McpServerConfig, ...]) -> tuple[str, ...]:
    """Bu turda ilk kez görülen MCP başarısızlıkları için ekrana basılacak satırlar."""
    from ..mcp_bridge.pool import new_mcp_failures

    return tuple(
        messages.MCP_SERVER_UNAVAILABLE.format(
            server=status.server, reason=short_reason(status.message or "")
        )
        for status in new_mcp_failures(configs)
    )
