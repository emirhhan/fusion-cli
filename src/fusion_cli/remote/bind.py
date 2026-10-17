"""Dinleme adresi politikası: internete açık bind yok, LAN yalnız şifreli ya da özel tünelle."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass


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
    if address.is_unspecified or not (address.is_private or address.is_link_local):
        raise BindRefusedError(
            "İnternete açık veya tüm arayüzleri dinleyen adres reddedildi; "
            "yerel ağ özel adresi ya da 127.0.0.1 kullan."
        )
    if not policy.allow_lan:
        raise BindRefusedError("Yerel ağ dinlemesi için açıkça izin vermelisin.")
    if not (policy.tls_enabled or policy.trusted_tunnel):
        raise BindRefusedError(
            "Yerel ağda şifresiz dinleme yok: TLS sertifikası ya da güvenilir özel tünel gerekir."
        )


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
        if ipaddress.ip_address(address).is_private
        and not ipaddress.ip_address(address).is_loopback
    )
