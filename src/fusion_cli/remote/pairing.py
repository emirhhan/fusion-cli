"""Cihaz eşleştirme: tek kullanımlık kod + masaüstü onayı + tek seferlik teslim.

Akış: masaüstü `begin` → cihaz kodu girer (`submit`) → masaüstü kullanıcısı
`approve` eder → cihaz `claim` ile kimlik ve sırrını bir kez alır. İmzalı (PWA) kanalda
"onay iste" ayarı kapalıysa `submit` kodu kendiliğinden onaylar.
Kod yanlış denemeleri sınırlanır; onaylanmamış kod sır vermez.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from ..core.protocols import Clock
from .constants import (
    PAIRING_CLAIM_TTL_SECONDS,
    PAIRING_CODE_ALPHABET,
    PAIRING_CODE_LENGTH,
    PAIRING_CODE_TTL_SECONDS,
)
from .devices import CHANNEL_SIGNED, Device, DeviceRegistry
from .scopes import parse_scopes


class PairingError(Exception):
    """Eşleştirme reddi; mesaj kullanıcıya gösterilebilir (sır içermez)."""


@dataclass(slots=True)
class _Pending:
    code: str
    scopes: frozenset[str]
    channel: str
    expires_at: float
    device_name: str = ""
    external_id: str = ""
    submitted: bool = False
    approved_device: Device | None = None
    claim_expires_at: float = 0.0
    failures: int = field(default=0)


class PairingService:
    """Bekleyen eşleştirmeleri bellekte tutar; kalıcı olan yalnız onaylı cihazdır."""

    def __init__(
        self,
        registry: DeviceRegistry,
        clock: Clock,
        *,
        token_bytes: Callable[[int], bytes] = os.urandom,
        require_approval: Callable[[], bool] = lambda: True,
        on_paired: Callable[[Device], None] | None = None,
    ) -> None:
        self._require_approval = require_approval
        self._on_paired = on_paired
        self._registry = registry
        self._clock = clock
        self._token_bytes = token_bytes
        self._pending: dict[str, _Pending] = {}

    def begin(self, scopes: object = None, channel: str = CHANNEL_SIGNED) -> tuple[str, float]:
        """Masaüstü yeni kod üretir; kapsamlar açık seçimdir."""
        granted = parse_scopes(scopes)
        self._purge()
        code = self._new_code()
        expires = self._clock.now() + PAIRING_CODE_TTL_SECONDS
        self._pending[code] = _Pending(
            code=code, scopes=granted, channel=channel, expires_at=expires
        )
        return code, expires

    def submit(
        self, code: str, device_name: str, external_id: str = "", channel: str | None = None
    ) -> frozenset[str]:
        """Cihaz kodu girer; masaüstü onayı bekler. Kapsamlar cihaza gösterilir.

        `channel` verilirse kod yalnız o kanal için üretilmiş olmalıdır; Telegram kodu
        imzalı uçta (ya da tersi) kullanılamaz.
        """
        self._purge()
        pending = self._lookup(code)
        if channel is not None and pending.channel != channel:
            raise PairingError("Kod geçersiz veya süresi doldu.")
        if pending.submitted:
            raise PairingError("Bu kod zaten kullanıldı.")
        pending.submitted = True
        pending.device_name = device_name
        pending.external_id = external_id
        # Kodu masaüstünde kullanıcının KENDİSİ üretti (2 dk, hız sınırlı): imzalı (PWA) kanalda
        # doğru kod eşleştirmeyi onaylar. Telegram kanalı ve "onay iste" ayarı eskisi gibi kalır.
        if pending.channel == CHANNEL_SIGNED and not self._require_approval():
            self.approve(pending.code)
        return pending.scopes

    def approve(self, code: str) -> Device:
        """Masaüstü kullanıcısı onaylar; cihaz kaydı o anda oluşur."""
        self._purge()
        pending = self._lookup(code)
        if not pending.submitted:
            raise PairingError("Cihaz henüz kodu girmedi.")
        if pending.approved_device is not None:
            raise PairingError("Eşleştirme zaten onaylandı.")
        device = self._registry.add(
            pending.device_name, pending.channel, pending.scopes, pending.external_id
        )
        pending.approved_device = device
        if pending.channel != CHANNEL_SIGNED:
            self._pending.pop(pending.code, None)  # sır teslimi yok: kimlik kanalda
        pending.claim_expires_at = self._clock.now() + PAIRING_CLAIM_TTL_SECONDS
        if self._on_paired is not None:
            self._on_paired(device)
        return device

    def is_approved(self, code: str) -> bool:
        """Kod girildi ve cihaz kaydı oluştu mu (teslim bekliyor)?"""
        try:
            return self._lookup(code).approved_device is not None
        except PairingError:
            return False

    def reject(self, code: str) -> bool:
        return self._pending.pop(code.strip().upper(), None) is not None

    def claim(self, code: str) -> Device | None:
        """Onaylıysa cihaz bilgisini TEK SEFER verir; onay bekleniyorsa `None`."""
        self._purge()
        pending = self._lookup(code)
        if pending.approved_device is None:
            return None
        device = pending.approved_device
        self._pending.pop(pending.code, None)
        return device

    def _lookup(self, code: str) -> _Pending:
        normalized = code.strip().upper()
        for known, pending in self._pending.items():
            if hmac.compare_digest(known, normalized):
                return pending
        raise PairingError("Kod geçersiz veya süresi doldu.")

    def _purge(self) -> None:
        now = self._clock.now()
        expired = [
            code
            for code, pending in self._pending.items()
            if now > pending.expires_at
            or (pending.approved_device is not None and now > pending.claim_expires_at)
        ]
        for code in expired:
            self._pending.pop(code, None)

    def _new_code(self) -> str:
        alphabet = PAIRING_CODE_ALPHABET
        raw = self._token_bytes(PAIRING_CODE_LENGTH)
        return "".join(alphabet[byte % len(alphabet)] for byte in raw)
