"""Araç çağrısı 401/403 dönünce headersHelper'ı yeniden çalıştırıp BİR KEZ yeniden dene (#249).

Belge (code.claude.com/docs/en/mcp, "Use dynamic headers for custom authentication"): "If a
tool call returns 401 Unauthorized or 403 Forbidden, Claude Code automatically re-runs the
helper under the same rule, reconnects with the fresh headers, and retries the call once."
Sunucu yalnız bu deneme de başarısızsa kimlik doğrulaması gerekiyor olarak işaretlenir.

HTTP durumları korumalı httpx istemcisinin yanıt kancasıyla gözlenir (`egress`); SDK 401'i
çağrıya "Connection closed" olarak yansıttığı için durum kodu başka yoldan görünmez.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import McpClient

AUTH_STATUSES = frozenset({401, 403})

#: Havuzun verdiği yeniden bağlanma: sunucu adı → taze başlıklarla yeni istemci (ya da None).
Reauth = Callable[[str], Awaitable["McpClient | None"]]


class AuthFailures:
    """Sunucu başına son gözlenen 401/403; çağrı hatasında bir kez tüketilir."""

    def __init__(self) -> None:
        self._servers: set[str] = set()

    def observer(self, server: str) -> Callable[[int], None]:
        def _note(status: int) -> None:
            if status in AUTH_STATUSES:
                self._servers.add(server)

        return _note

    def take(self, server: str) -> bool:
        if server in self._servers:
            self._servers.discard(server)
            return True
        return False
