"""Dinleme adresi politikası: internete açık bind yok, LAN yalnız şifreli ya da özel tünelle."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass

#: Tailscale/CGNAT adres bloğu (RFC 6598): internetten yönlendirilemez ama Python
#: `is_private` saymaz. Ölçüldü (30 Ekim, Python 3.11): `100.64.0.1.is_private == False`.
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")


class BindRefusedError(ValueError):
    """Güvensiz dinleme adresi reddedildi; mesaj kullanıcıya gösterilebilir."""


@dataclass(frozen=True, slots=True)
class BindPolicy:
    """Kullanıcının bilinçli seçimleri."""

    allow_lan: bool = False
    tls_enabled: bool = False
    trusted_tunnel: bool = False


def validate_bind(host: str, policy: BindPolicy) -> None:
    """Adres güvenli değilse `BindRefusedError` fırlat."""
    if host in {"localhost"}:
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise BindRefusedError(f"Geçersiz dinleme adresi: {host}") from error
    if address.is_loopback:
        return
    if address.is_unspecified or not (_is_private_network(address) or address.is_link_local):
        raise BindRefusedError(
            "İnternete açık veya tüm arayüzleri dinleyen adres reddedildi; "
            "yerel ağ özel adresi, Tailscale (100.64.0.0/10) adresi ya da 127.0.0.1 kullan."
        )
    if not policy.allow_lan:
        raise BindRefusedError("Yerel ağ dinlemesi için açıkça izin vermelisin.")
    if not (policy.tls_enabled or policy.trusted_tunnel):
        raise BindRefusedError(
            "Yerel ağda şifresiz dinleme yok: TLS sertifikası ya da güvenilir özel tünel gerekir."
        )


def _is_private_network(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Özel ağ ya da paylaşılan (Tailscale) adres alanı mı?"""
    if address.is_private:
        return True
    return isinstance(address, ipaddress.IPv4Address) and address in _SHARED_ADDRESS_SPACE


def private_addresses() -> list[str]:
    """Bu bilgisayarın yerel ağ (özel) IPv4 adresleri; arayüz seçenek olarak gösterir."""
    found: set[str] = set()
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))  # paket gönderilmez; yalnız çıkış arayüzünü seçtirir
        found.add(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(str(info[4][0]))
    except OSError:
        pass
    return sorted(
        address
        for address in found
        if _is_private_network(ipaddress.ip_address(address))
        and not ipaddress.ip_address(address).is_loopback
    )
