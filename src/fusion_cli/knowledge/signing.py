"""Paket imzalama ve doğrulama — HMAC-SHA256 (stdlib, dış bağımlılık yok).

İmza anahtarı gözden geçirme sürecini (maintainer/CI) temsil eder: yalnızca anahtarı
elinde tutan taraf geçerli bir imza üretebilir. İstemci aynı anahtarla imzayı
doğrular ve paketin bozulmadığını/oynanmadığını görür. Simetrik olduğu için bu bir
kimlik değil BÜTÜNLÜK/oynama-tespiti güvencesidir; git tabanlı dağıtım için yeterli.
"""

from __future__ import annotations

import hashlib
import hmac

#: İstemcinin bütünlük doğrulaması için kullandığı varsayılan anahtar. SIR DEĞİLDİR:
#: git üzerinden dağıtımda kazara bozulmayı/oynamayı yakalar. Gerçek kimlik güvencesi
#: gerekirse asimetrik imzaya geçilir (ayrıca konuşulur; şu an kapsam dışı).
DEFAULT_INTEGRITY_KEY = "fusion-cli-knowledge-v1"


def sign(payload: bytes, key: str) -> str:
    """Yükü anahtarla imzala; onaltılık HMAC-SHA256 döndür."""

    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify(payload: bytes, signature: str, key: str) -> bool:
    """İmza bu yük ve anahtar için geçerli mi (sabit-zamanlı karşılaştırma)."""

    expected = sign(payload, key)
    return hmac.compare_digest(expected, signature)
