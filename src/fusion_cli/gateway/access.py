"""Gateway ağ erişim sınırı: bağlantının gerçek kaynağı ve belirteç denetimi.

`Host` başlığını istemci yazar; yerel olup olmadığına ancak ASGI `client`
(TCP karşı ucu) karar verir. Yerel olmayan bağlantı, gateway açıkça bir belirteçle
başlatılmışsa ve istek o belirteci `Authorization: Bearer` ya da `x-api-key` başlığıyla
taşıyorsa kabul edilir (Anthropic SDK'ları `ANTHROPIC_API_KEY`'i yalnız `x-api-key` ile
gönderir; ölçüldü 31 Ekim, Bearer şartı onları 401'e düşürüyordu). Belirteç yoksa ağdan
gelen hiçbir istek kabul edilmez.
"""

from __future__ import annotations

import hmac
import ipaddress
from collections.abc import Iterable, Mapping
from typing import Any

#: Yerel sayılan bind adları (IP olmayanlar).
_LOOPBACK_NAMES = frozenset({"localhost"})
_BEARER_PREFIX = "bearer "


def is_loopback_address(host: str) -> bool:
    """`127.0.0.0/8`, `::1` veya `localhost` mu? Joker adres (`0.0.0.0`, `::`) DEĞİLDİR."""
    value = host.strip().strip("[]").lower()
    if value in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def is_loopback_peer(scope: Mapping[str, Any]) -> bool:
    """TCP karşı ucu bu bilgisayar mı? Bilinmeyen karşı uç yerel sayılmaz."""
    client = scope.get("client")
    if not client:
        return False
    return is_loopback_address(str(client[0]))


def bearer_matches(headers: Iterable[tuple[bytes, bytes]], token: str | None) -> bool:
    """`Authorization: Bearer <token>` sabit zamanlı karşılaştırmayla eşleşiyor mu?"""
    if not token:
        return False
    for key, value in headers:
        if key.lower() != b"authorization":
            continue
        raw = value.decode("latin-1").strip()
        if not raw.lower().startswith(_BEARER_PREFIX):
            return False
        offered = raw[len(_BEARER_PREFIX) :].strip()
        return hmac.compare_digest(offered.encode(), token.encode())
    return False


def api_key_matches(headers: Iterable[tuple[bytes, bytes]], token: str | None) -> bool:
    """`x-api-key: <token>` (Anthropic SDK biçimi) sabit zamanlı eşleşiyor mu?"""
    if not token:
        return False
    for key, value in headers:
        if key.lower() == b"x-api-key":
            offered = value.decode("latin-1").strip()
            return hmac.compare_digest(offered.encode(), token.encode())
    return False


def token_matches(headers: Iterable[tuple[bytes, bytes]], token: str | None) -> bool:
    """Belirteç Bearer ya da x-api-key başlığından geldi mi? İkisi de yoksa False."""
    return bearer_matches(headers, token) or api_key_matches(headers, token)
