"""Bir IP adresinin genel internette olup olmadığı: dışa istek atan her yerin tek kuralı.

`ipaddress.is_global` IPv6'ya gömülü IPv4'ü açmaz. Ölçüldü (29 Ekim, Python
3.11.17): NAT64 `64:ff9b::a00:1` (→ 10.0.0.1) ve eski IPv4-uyumlu `::7f00:1`
(→ 127.0.0.1) "genel" sayılıyordu. Gömülü adres açılıp o denetlenir.
"""

from __future__ import annotations

import ipaddress

__all__ = ["is_public_ip"]

#: İçine IPv4 gömülü IPv6 aralıkları: NAT64 (RFC 6052/8215) ve eski IPv4-uyumlu `::a.b.c.d`.
_EMBEDDED_IPV4_NETS = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("::/96"),
)
_LOW_32_BITS = 0xFFFFFFFF


def is_public_ip(address: str) -> bool:
    """Adres genel internette mi? Ayrıştırılamayan adres genel SAYILMAZ.

    CGNAT (`100.64.0.0/10`, Tailscale cihazları) de iç ağdır.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return _is_public(ip)


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return _is_public(ip.ipv4_mapped)
        if any(ip in net for net in _EMBEDDED_IPV4_NETS):
            return _is_public(ipaddress.IPv4Address(int(ip) & _LOW_32_BITS))
    return ip.is_global and not ip.is_multicast
