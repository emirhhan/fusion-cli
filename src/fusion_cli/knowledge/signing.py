"""Paket imzalama ve doğrulama — Ed25519 asimetrik imza.

İmza artık asimetriktir: yükü yalnızca ÖZEL anahtarı (maintainer/CI) elinde tutan
taraf imzalayabilir; istemci gömülü AÇIK anahtarla imzayı doğrular. Özel anahtar
repoda/kodda ASLA bulunmaz. Böylece bu bir kimlik güvencesidir: açık anahtar herkeste
olsa bile karşılık gelen özel anahtar olmadan geçerli bir imza üretilemez.

Anahtarlar onaltılık (hex) ham bayt olarak taşınır: 32 baytlık açık anahtar, 32
baytlık özel anahtar tohumu. Ed25519 stdlib'de olmadığından `cryptography` gerekir.
"""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

#: İstemciye gömülü, dağıtımı imzalayan çiftin AÇIK anahtarı (hex). Sır DEĞİLDİR:
#: yalnızca doğrulama için kullanılır. Karşılık gelen ÖZEL anahtar maintainer'dadır
#: ve repoya ASLA girmez. Henüz resmî bir dağıtım anahtarı yayımlanmadığından bu
#: değer geçerli-ama-yer-tutucu bir Ed25519 açık anahtarıdır; ilk imzalı paket
#: yayımlanırken maintainer'ın gerçek açık anahtarıyla değiştirilir (özel anahtar
#: repo dışında saklanır). Yer tutucu olduğu için hiçbir üçüncü taraf geçerli imza
#: üretemez: imzasız/yanlış imzalı her paket reddedilir (fail-closed).
DEFAULT_PUBLIC_KEY = "4c37df5465db184d84cf318975b8271b03476835543a4dd1087385aaa8cc88a1"


def sign(payload: bytes, private_key_hex: str) -> str:
    """Yükü özel anahtarla imzala; onaltılık Ed25519 imzası döndür."""

    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    return private_key.sign(payload).hex()


def verify(payload: bytes, signature: str, public_key_hex: str) -> bool:
    """İmza bu yük ve açık anahtar için geçerli mi.

    Geçersiz imza, bozuk anahtar ya da bozuk imza baytları hepsi `False` döner;
    akış kontrolü için istisna dışarı sızmaz.
    """

    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(bytes.fromhex(signature), payload)
    except (InvalidSignature, ValueError):
        return False
    return True


def generate_keypair() -> tuple[str, str]:
    """Yeni bir Ed25519 çifti üret; (özel anahtar hex, açık anahtar hex) döndür.

    İmzalama tarafında (maintainer aracı, test) kullanılır; istemci yalnızca doğrular.
    """

    from cryptography.hazmat.primitives import serialization

    private_key = Ed25519PrivateKey.generate()
    private_hex = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    public_hex = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    return private_hex, public_hex
