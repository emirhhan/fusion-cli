"""Sandbox proxy'sinde TLS sonlandırma ve kimlik bilgisi yerine koyma (Claude mask, #350, #368).

Claude Code `sandbox.credentials.envVars` `mode: mask`: sandbox içindeki komut gerçek değer
yerine oturum başına bir yer tutucu (sentinel) görür; sandbox proxy'si giden istekte izinli
ana makinelere gerçek değeri koyar. HTTPS için proxy TLS'i sonlandırmalıdır
(`network.tlsTerminate`); düz HTTP için `allowPlaintextInject`.

Yer tutucu gerçek değerle AYNI uzunluktadır (`tools.sandbox_mask`): bayt akışında yerine koyma
`Content-Length` ve parçalı gövde sınırlarını bozmaz, HTTP iletisi çözümlenmeden akış
üzerinde yapılır. Yanıtta gerçek değer geri dönerse yer tutucuya çevrilir (komut gerçek
değeri hiç görmez). Sertifika üretimi (`cryptography`) bu katmanda değildir; proxy'ye
`TlsInterceptor` olarak verilir.
"""

from __future__ import annotations

import select
import socket
import ssl
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .sandbox_policy import normalize_domain

__all__ = [
    "Injection",
    "StreamReplacer",
    "TlsInterceptor",
    "injections_for",
    "relay_rewriting",
    "replacers",
    "starts_tls",
]

_CHUNK = 65_536
_IDLE_TIMEOUT_S = 300.0
#: Akış sonunda yer tutucunun yarısı bekletilirse bu süre içinde gelmeyen devam beklenmez.
_HOLD_S = 0.05
#: TLS el sıkışmasının ilk baytı (ContentType handshake).
TLS_HANDSHAKE = 0x16


@dataclass(frozen=True, slots=True)
class Injection:
    """Yer tutucu → gerçek değer ve yerine konduğu ana makine kalıpları (`*.ornek.com`)."""

    sentinel: bytes
    value: bytes
    hosts: tuple[str, ...]


class TlsInterceptor(Protocol):
    """Ana makine için sunucu bağlamı (geçici CA imzalı) ve gerçek sunucuya istemci bağlamı."""

    def server_context(self, host: str) -> ssl.SSLContext: ...

    def upstream_context(self) -> ssl.SSLContext: ...


def _host_matches(host: str, pattern: str) -> bool:
    entry = normalize_domain(pattern)
    if entry is None:
        return False
    return host.endswith(entry[1:]) if entry.startswith("*.") else host == entry


def injections_for(host: str, injections: Sequence[Injection]) -> tuple[Injection, ...]:
    """Bu ana makineye giden istekte yerine konacak değerler."""
    normalized = normalize_domain(host)
    if normalized is None:
        return ()
    return tuple(
        item for item in injections if any(_host_matches(normalized, p) for p in item.hosts)
    )


class StreamReplacer:
    """Bayt akışında eşit uzunluklu yerine koyma; parçalar arasında bölünen eşleşme beklenir."""

    def __init__(self, pairs: Sequence[tuple[bytes, bytes]]) -> None:
        self._pairs = tuple((old, new) for old, new in pairs if old and old != new)
        self._held = b""

    @property
    def holding(self) -> bool:
        return bool(self._held)

    def feed(self, data: bytes) -> bytes:
        buffer = self._held + data
        for old, new in self._pairs:
            buffer = buffer.replace(old, new)
        keep = self._partial_suffix(buffer)
        self._held = buffer[len(buffer) - keep :] if keep else b""
        return buffer[: len(buffer) - keep]

    def flush(self) -> bytes:
        held, self._held = self._held, b""
        return held

    def _partial_suffix(self, buffer: bytes) -> int:
        best = 0
        for old, _ in self._pairs:
            for size in range(min(len(old) - 1, len(buffer)), best, -1):
                if buffer.endswith(old[:size]):
                    best = size
                    break
        return best


def replacers(found: Sequence[Injection]) -> tuple[StreamReplacer, StreamReplacer]:
    """Giden istekte yer tutucu → değer, gelen yanıtta değer → yer tutucu."""
    outbound = StreamReplacer([(item.sentinel, item.value) for item in found])
    inbound = StreamReplacer([(item.value, item.sentinel) for item in found])
    return outbound, inbound


def starts_tls(client: socket.socket) -> bool:
    """İstemcinin ilk baytı TLS el sıkışması mı? (git/ssh gibi düz tüneller dokunulmadan geçer)"""
    try:
        first = client.recv(1, socket.MSG_PEEK)
    except OSError:
        return False
    return bool(first) and first[0] == TLS_HANDSHAKE


def _ready(sockets: list[socket.socket], waiting: bool) -> list[socket.socket] | None:
    pending: list[socket.socket] = [
        item for item in sockets if isinstance(item, ssl.SSLSocket) and item.pending()
    ]
    if pending:
        return pending
    readable, _, _ = select.select(sockets, [], [], _HOLD_S if waiting else _IDLE_TIMEOUT_S)
    return readable if readable or waiting else None


def relay_rewriting(
    client: socket.socket,
    upstream: socket.socket,
    outbound: StreamReplacer,
    inbound: StreamReplacer,
) -> None:
    """İki yönlü aktarım; istemciden gideni `outbound`, gelen yanıtı `inbound` ile değiştir."""
    sockets = [client, upstream]
    routes = {id(client): (upstream, outbound), id(upstream): (client, inbound)}
    while True:
        ready = _ready(sockets, outbound.holding or inbound.holding)
        if ready is None:
            return
        if not ready:
            # Bekletilen yarım eşleşmenin devamı gelmedi: olduğu gibi gönder.
            for target, replacer in routes.values():
                if replacer.holding:
                    target.sendall(replacer.flush())
            continue
        for source in ready:
            target, replacer = routes[id(source)]
            try:
                data = source.recv(_CHUNK)
            except ssl.SSLWantReadError:
                continue
            except OSError:
                return
            if not data:
                tail = replacer.flush()
                if tail:
                    target.sendall(tail)
                return
            out = replacer.feed(data)
            if out:
                target.sendall(out)
