"""İmzalı istek: HMAC-SHA256, saat sapması sınırı, nonce yeniden oynatma koruması.

İmzalanan metin: sürüm, yöntem, yol, zaman, nonce, sıra numarası ve gövde özeti.
Böylece gövde, yol veya sıra değiştirilen istek doğrulanamaz.
"""

from __future__ import annotations

import hashlib
import hmac
from collections import OrderedDict
from dataclasses import dataclass

from ..core.protocols import Clock
from .constants import (
    NONCE_CACHE_LIMIT,
    NONCE_RETENTION_SECONDS,
    RPC_VERSION,
    SIGNATURE_MAX_SKEW_SECONDS,
)


@dataclass(frozen=True, slots=True)
class SignedRequest:
    """Sunucunun doğrulayacağı imzalı istek üstverisi."""

    method: str
    path: str
    timestamp: int
    nonce: str
    sequence: int
    body: bytes
    signature: str


def canonical_string(
    method: str, path: str, timestamp: int, nonce: str, sequence: int, body: bytes
) -> bytes:
    """İmza girdisi; alanlar satır sonuyla ayrılır, gövde özetle bağlanır."""
    digest = hashlib.sha256(body).hexdigest()
    parts = (RPC_VERSION, method.upper(), path, str(timestamp), nonce, str(sequence), digest)
    return "\n".join(parts).encode("utf-8")


def sign(
    secret: bytes, method: str, path: str, timestamp: int, nonce: str, sequence: int, body: bytes
) -> str:
    """İstemci tarafı imza (onaltılık)."""
    message = canonical_string(method, path, timestamp, nonce, sequence, body)
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


class NonceCache:
    """Tolerans penceresi boyunca görülen nonce'ları tutar; ikinci kullanımı reddeder."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._seen: OrderedDict[tuple[str, str], float] = OrderedDict()

    def register(self, device_id: str, nonce: str) -> bool:
        """İlk görülüşse `True`; tekrarsa `False`."""
        now = self._clock.now()
        self._evict(now)
        key = (device_id, nonce)
        if key in self._seen:
            return False
        self._seen[key] = now
        while len(self._seen) > NONCE_CACHE_LIMIT:
            self._seen.popitem(last=False)
        return True

    def _evict(self, now: float) -> None:
        while self._seen:
            oldest_key = next(iter(self._seen))
            if now - self._seen[oldest_key] <= NONCE_RETENTION_SECONDS:
                break
            self._seen.pop(oldest_key)


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """İmza doğrulama sonucu; neden bilgisi ham sır içermez."""

    ok: bool
    reason: str = ""


class SignatureVerifier:
    """İmza + saat sapması + nonce + monoton sıra numarası."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._nonces = NonceCache(clock)
        self._last_sequence: dict[str, int] = {}

    def verify(self, device_id: str, secret: bytes, request: SignedRequest) -> VerifyResult:
        expected = sign(
            secret,
            request.method,
            request.path,
            request.timestamp,
            request.nonce,
            request.sequence,
            request.body,
        )
        if not hmac.compare_digest(expected, request.signature):
            return VerifyResult(False, "imza_gecersiz")
        if abs(self._clock.now() - request.timestamp) > SIGNATURE_MAX_SKEW_SECONDS:
            return VerifyResult(False, "zaman_asimi")
        if request.sequence <= self._last_sequence.get(device_id, 0):
            return VerifyResult(False, "sira_eski")
        if not self._nonces.register(device_id, request.nonce):
            return VerifyResult(False, "nonce_tekrar")
        self._last_sequence[device_id] = request.sequence
        return VerifyResult(True)
