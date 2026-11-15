"""Denetlenen IP'ye sabitlenmiş HTTP taşıması (SSRF, DNS rebinding).

Adı çözüp denetledikten sonra bağlantıyı httpx'e bırakmak, httpx'in adı YENİDEN
çözmesi demektir. TTL'i 0 olan bir alan adı ilk sorguda genel, ikincide iç adres
döndürerek denetimi atlatır. Burada ad bir kez çözülür, BÜTÜN adresleri genel değilse
istek gönderilmez, istek denetlenen IP'ye gider. `Host` başlığı ve TLS SNI özgün adı
taşır; sertifika o ada göre doğrulanır (httpcore `sni_hostname`'i `server_hostname`
olarak kullanır). Bağlantı havuzu ana makine adına göre ayrıdır: aynı IP'yi paylaşan
iki ad, yalnız birinin sertifikasıyla doğrulanmış bağlantıyı paylaşamaz.

Bilinen sınır: açık taşıma httpx'te ortamdaki HTTP(S)_PROXY'yi kapatır.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable

import httpx

from ..core.errors import FusionError
from ..core.network_address import is_public_ip

__all__ = [
    "AsyncPinnedTransport",
    "BlockedAddressError",
    "PinnedTransport",
    "connect_order",
    "direct_async_transport",
    "direct_transport",
    "pin_request",
]

AllowsPrivate = Callable[[httpx.URL], bool]


class BlockedAddressError(FusionError, httpx.TransportError):
    """Hedef iç ağa çözüldü; istek gönderilmedi."""


def direct_transport(_host: str) -> httpx.BaseTransport:
    return httpx.HTTPTransport()


def direct_async_transport(_host: str) -> httpx.AsyncBaseTransport:
    return httpx.AsyncHTTPTransport()


def _resolve(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


async def _resolve_async(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


def connect_order(addresses: list[str]) -> list[str]:
    """Tekrarsız, IPv4 önce: IPv6'sı çalışmayan ağda AAAA'ya sabitlenip kalmamak için."""
    unique = list(dict.fromkeys(addresses))
    return sorted(unique, key=lambda a: ipaddress.ip_address(a).version)


def pin_request(request: httpx.Request, address: str) -> httpx.Request:
    """İsteği denetlenen IP'ye yönelt; Host ve SNI özgün adı korur."""
    return httpx.Request(
        request.method,
        request.url.copy_with(host=address),
        headers=request.headers,
        stream=request.stream,
        extensions={**request.extensions, "sni_hostname": request.url.host},
    )


def blocked_message(host: str) -> str:
    return f"iç ağ adresi ({host}); istek gönderilmedi"


def _is_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _checked(request: httpx.Request, addresses: list[str], *, allows_private: bool) -> list[str]:
    host = request.url.host
    ordered = connect_order(addresses)
    if not ordered:
        raise BlockedAddressError(f"adres çözülemedi: {host}", request=request)
    if not allows_private and not all(is_public_ip(a) for a in ordered):
        raise BlockedAddressError(blocked_message(host), request=request)
    return ordered


class PinnedTransport(httpx.BaseTransport):
    """Senkron istemciler için (web_fetch, site_crawl)."""

    def __init__(
        self,
        *,
        resolver: Callable[[str], list[str]] = _resolve,
        transport_for: Callable[[str], httpx.BaseTransport] | None = None,
        allows_private: AllowsPrivate = lambda _url: False,
    ) -> None:
        self._resolver = resolver
        self._transport_for = transport_for
        self._allows_private = allows_private
        self._by_host: dict[str, httpx.BaseTransport] = {}

    def _inner(self, host: str) -> httpx.BaseTransport:
        if host not in self._by_host:
            # Fabrika her çağrıda modülden okunur: testler `direct_transport`'u değiştirir.
            factory = self._transport_for or direct_transport
            self._by_host[host] = factory(host)
        return self._by_host[host]

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        private_ok = self._allows_private(request.url)
        inner = self._inner(host)
        if _is_literal(host):
            if not private_ok and not is_public_ip(host):
                raise BlockedAddressError(blocked_message(host), request=request)
            return inner.handle_request(request)
        addresses = _checked(request, self._resolver(host), allows_private=private_ok)
        for address in addresses[:-1]:
            try:
                return inner.handle_request(pin_request(request, address))
            except httpx.ConnectError:
                continue
        return inner.handle_request(pin_request(request, addresses[-1]))

    def close(self) -> None:
        for transport in self._by_host.values():
            transport.close()


class AsyncPinnedTransport(httpx.AsyncBaseTransport):
    """Asenkron istemciler için (download_file, uzak MCP)."""

    def __init__(
        self,
        *,
        resolver: Callable[[str], Awaitable[list[str]]] = _resolve_async,
        transport_for: Callable[[str], httpx.AsyncBaseTransport] | None = None,
        allows_private: AllowsPrivate = lambda _url: False,
    ) -> None:
        self._resolver = resolver
        self._transport_for = transport_for
        self._allows_private = allows_private
        self._by_host: dict[str, httpx.AsyncBaseTransport] = {}

    def _inner(self, host: str) -> httpx.AsyncBaseTransport:
        if host not in self._by_host:
            factory = self._transport_for or direct_async_transport
            self._by_host[host] = factory(host)
        return self._by_host[host]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        private_ok = self._allows_private(request.url)
        inner = self._inner(host)
        if _is_literal(host):
            if not private_ok and not is_public_ip(host):
                raise BlockedAddressError(blocked_message(host), request=request)
            return await inner.handle_async_request(request)
        addresses = _checked(request, await self._resolver(host), allows_private=private_ok)
        for address in addresses[:-1]:
            try:
                return await inner.handle_async_request(pin_request(request, address))
            except httpx.ConnectError:
                continue
        return await inner.handle_async_request(pin_request(request, addresses[-1]))

    async def aclose(self) -> None:
        for transport in self._by_host.values():
            await transport.aclose()
