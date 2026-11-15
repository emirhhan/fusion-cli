"""Uzak MCP isteklerinin gidebileceği adresleri sınırla (WP11, SSRF).

OAuth keşfinde sunucunun döndürdüğü metadata (korunan kaynak, yetkilendirme
sunucusu, token uç noktası) herhangi bir adresi gösterebilir. SDK oraya bağlantının
kendi istemcisiyle gider. Ölçüldü (28 Ekim, SDK 1.30.0): kötü niyetli bir MCP
sunucusu `authorization_servers` alanına `http://169.254.169.254/` yazarak Fusion'ı
bulut metadata adresine ya da yerel ağdaki cihazlara istek atmaya yönlendirebiliyordu.
`validate_remote_mcp_url` yalnız kullanıcının yazdığı adresin şemasına bakıyordu.

Kural:
- Kullanıcının yapılandırdığı sunucunun KENDİ kökeni (şema + ana makine + port)
  serbesttir. Kullanıcı iç ağdaki bir sunucuyu bilerek ekleyebilir.
- Başka her hedef HTTPS olmalı ve çözülen BÜTÜN adresleri genel internette olmalıdır.

Adres politikası ve IP'ye sabitleme (DNS rebinding) web araçlarıyla ortaktır:
bkz. `tools/pinned_http.py` ve `core/network_address.py`.

Bilinen sınırlar:
- Ortamdaki HTTP(S)_PROXY kullanılmaz (açık taşıma httpx'te ortam vekilini kapatır);
  vekil arkasındaki kullanıcı uzak MCP'ye doğrudan bağlanamazsa NETWORK hatası görür.
- Yapılandırılan kökenin adı her istekte yeniden çözülür ve IP'si denetlenmez:
  kullanıcının eklediği sunucunun DNS'i iç ağı gösterirse istek gider. Kullanıcı o
  sunucuya zaten güvenmiştir; risk yalnız aynı kökene yapılan isteklerle sınırlıdır.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from mcp.shared._httpx_utils import MCP_DEFAULT_SSE_READ_TIMEOUT, MCP_DEFAULT_TIMEOUT

from ..tools.pinned_http import AsyncPinnedTransport, BlockedAddressError

__all__ = ["EgressBlockedError", "guarded_client_factory"]

Resolver = Callable[[str], Awaitable[list[str]]]
TransportFactory = Callable[[str], httpx.AsyncBaseTransport]

#: MCP tarafındaki adı; web araçlarıyla aynı hata türüdür.
EgressBlockedError = BlockedAddressError

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: httpx.URL) -> tuple[str, str, int | None]:
    return url.scheme, url.host, url.port or _DEFAULT_PORTS.get(url.scheme)


class _GuardedTransport(AsyncPinnedTransport):
    """Yapılandırılan köken serbest; başka her hedef genel bir HTTPS adresi olmalı."""

    def __init__(
        self,
        configured: httpx.URL,
        transport_for: TransportFactory | None,
        resolver: Resolver | None,
    ) -> None:
        trusted = _origin(configured)
        kwargs: dict[str, Any] = {"allows_private": lambda url: _origin(url) == trusted}
        if resolver is not None:
            kwargs["resolver"] = resolver
        super().__init__(transport_for=transport_for, **kwargs)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https" and not self._allows_private(request.url):
            raise EgressBlockedError(f"şifresiz adres ({request.url.host})", request=request)
        return await super().handle_async_request(request)


def guarded_client_factory(
    configured_url: str,
    *,
    transport_for: TransportFactory | None = None,
    resolver: Resolver | None = None,
    on_response: Callable[[int], None] | None = None,
) -> Callable[..., httpx.AsyncClient]:
    """SDK'nın `httpx_client_factory` sözleşmesine uyan korumalı istemci üreticisi.

    `transport_for(host)` her ana makine adı için ayrı taşıma (bağlantı havuzu) kurar.
    """
    configured = httpx.URL(configured_url)

    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "timeout": timeout
            or httpx.Timeout(MCP_DEFAULT_TIMEOUT, read=MCP_DEFAULT_SSE_READ_TIMEOUT),
            "transport": _GuardedTransport(configured, transport_for, resolver),
        }
        if headers is not None:
            kwargs["headers"] = headers
        if auth is not None:
            kwargs["auth"] = auth
        if on_response is not None:
            # 401/403 gözlemi (#249): yanıt durumunu bildir, akışa dokunma.
            async def _observe(response: httpx.Response) -> None:
                on_response(response.status_code)

            kwargs["event_hooks"] = {"response": [_observe]}
        return httpx.AsyncClient(**kwargs)

    return factory
