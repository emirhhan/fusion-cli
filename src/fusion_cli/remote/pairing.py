"""Cihaz eşleştirme: tek kullanımlık kod + masaüstü onayı + tek seferlik teslim.

Akış: masaüstü `begin` → cihaz kodu girer (`submit`) → masaüstü kullanıcısı
`approve` eder → cihaz `claim` ile kimlik ve sırrını bir kez alır. İmzalı (PWA) kanalda
"onay iste" ayarı kapalıysa `submit` kodu kendiliğinden onaylar.
Kod yanlış denemeleri sınırlanır; onaylanmamış kod sır vermez.
"""

from __future__ import annotations

import hashlib
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
    #: Telefonun koda bağladığı teslim anahtarının karması; boşsa eski tek-sefer teslim.
    claim_key_hash: str = ""
    claimed: bool = False


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
        account_id: Callable[[], str] = lambda: "",
    ) -> None:
        #: Kodla eşleşen cihaz, eşleşmeyi onaylayan masaüstündeki açık hesaba bağlanır.
        self._account_id = account_id
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
        self,
        code: str,
        device_name: str,
        external_id: str = "",
        channel: str | None = None,
        *,
        claim_key: str = "",
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
        pending.claim_key_hash = _digest(claim_key) if claim_key else ""
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
            pending.device_name,
            pending.channel,
            pending.scopes,
            pending.external_id,
            account_id=self._account_id(),
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
        pending = self._pending.pop(code.strip().upper(), None)
        if pending is not None and pending.approved_device is not None:
            # Kod onay beklemeden onaylanmış olabilir: reddedilen eşleşmenin cihazı kalmaz.
            self._registry.revoke(pending.approved_device.device_id)
        return pending is not None

    def claim(self, code: str, claim_key: str = "") -> Device | None:
        """Onaylıysa cihaz bilgisini verir; onay bekleniyorsa `None`.

        Teslim anahtarıyla gönderilmiş kodda `claim` teslim süresi boyunca TEKRARLANABİLİR
        (yanıt ağda kaybolduysa telefon aynı cihazı yeniden alır); anahtarı bilmeyen alamaz.
        Anahtarsız eski istemciye cihaz tek sefer verilir.
        """
        self._purge()
        pending = self._lookup(code)
        if pending.approved_device is None:
            return None
        if pending.claim_key_hash:
            if not claim_key or not hmac.compare_digest(_digest(claim_key), pending.claim_key_hash):
                raise PairingError("Kod geçersiz veya süresi doldu.")
        elif pending.claimed:
            raise PairingError("Kod geçersiz veya süresi doldu.")
        pending.claimed = True
        return pending.approved_device

    def acknowledge(self, device_id: str) -> None:
        """Cihazın ilk imzalı isteği: sır telefona ulaştı, bekleyen teslim kapanır."""
        for code, pending in list(self._pending.items()):
            if (
                pending.approved_device is not None
                and pending.approved_device.device_id == device_id
            ):
                self._pending.pop(code, None)

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
            # Onaylanmış eşleştirmede kodun süresi değil TESLİM süresi geçerlidir:
            # kod son saniyede onaylansa da telefon sırrını alabilmeli.
            if now > (pending.claim_expires_at if pending.approved_device else pending.expires_at)
        ]
        for code in expired:
            pending = self._pending.pop(code, None)
            if pending is not None and pending.approved_device is not None:
                # Teslim süresi doldu ve cihaz hiç imzalı istek yapmadı: sırrı hiçbir
                # telefona ulaşmamış hayalet kayıt kalmasın.
                self._registry.revoke(pending.approved_device.device_id)

    def _new_code(self) -> str:
        alphabet = PAIRING_CODE_ALPHABET
        raw = self._token_bytes(PAIRING_CODE_LENGTH)
        return "".join(alphabet[byte % len(alphabet)] for byte in raw)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
