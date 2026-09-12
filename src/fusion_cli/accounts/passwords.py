"""Parola karması ve kurtarma kodu.

Parola HİÇBİR YERDE düz metin tutulmaz; karşılaştırma sabit zamanlıdır. Kurtarma
kodu da bir paroladır: aynı karma yolundan geçer, depoda düz hâli bulunmaz.

Sunucu yoktur — parola yalnız bu makinede doğrulanır. Bu, karmayı GEREKSİZ
yapmaz: aynı bilgisayarı paylaşan biri veritabanı dosyasını açabilir ve insanlar
parolalarını başka yerlerde de kullanır.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from ..core.constants import (
    RECOVERY_CODE_BYTES,
    SCRYPT_KEY_BYTES,
    SCRYPT_MAXMEM,
    SCRYPT_N,
    SCRYPT_P,
    SCRYPT_R,
    SCRYPT_SALT_BYTES,
)

__all__ = [
    "PASSWORD_MIN_CHARS",
    "format_recovery_code",
    "generate_recovery_code",
    "hash_secret",
    "normalize_recovery_code",
    "verify_secret",
]

#: Karma kaydının biçim etiketi. Parametreler kayda YAZILIR: ileride maliyet
#: artarsa eski karmalar hâlâ doğrulanabilir.
_SCHEME = "scrypt"

#: Kabul edilen en kısa parola.
#
# Sunucu tarafı hız sınırı olmayan yerel bir depoda kısa parola kolay kırılır;
# 8 karakter yaygın kabul gören alt sınırdır ve kullanıcıyı da yormaz.
PASSWORD_MIN_CHARS = 8

#: Kurtarma kodunun alfabesi — Crockford Base32: 0/O ve 1/I/L karışmaz.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
#: Okunurluk için kaç karakterde bir tire konur.
_GROUP = 4


def hash_secret(secret: str) -> str:
    """Parolayı (ya da kurtarma kodunu) saklanabilir bir karmaya çevir."""
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    digest = _derive(secret, salt)
    return "$".join(
        (
            _SCHEME,
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def verify_secret(secret: str, stored: str) -> bool:
    """Girilen parolayı kayıtla karşılaştır; biçim bozuksa False döner.

    Bozuk kayıtta İSTİSNA FIRLATILMAZ: veritabanı elle kurcalanmışsa doğru
    davranış girişi reddetmektir, uygulamayı çökertmek değil.
    """
    parcalar = stored.split("$")
    if len(parcalar) != 6 or parcalar[0] != _SCHEME:
        return False
    try:
        n, r, p = int(parcalar[1]), int(parcalar[2]), int(parcalar[3])
        salt = base64.b64decode(parcalar[4], validate=True)
        beklenen = base64.b64decode(parcalar[5], validate=True)
    except (ValueError, TypeError):
        return False
    try:
        aday = _derive(secret, salt, n=n, r=r, p=p, length=len(beklenen))
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(aday, beklenen)


def _derive(
    secret: str,
    salt: bytes,
    *,
    n: int = SCRYPT_N,
    r: int = SCRYPT_R,
    p: int = SCRYPT_P,
    length: int = SCRYPT_KEY_BYTES,
) -> bytes:
    return hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=length,
        maxmem=SCRYPT_MAXMEM,
    )


def generate_recovery_code() -> str:
    """Okunabilir, tahmin edilemez bir kurtarma kodu üret.

    Parola unutulduğunda tek çıkış yolu budur: sunucu olmadığı için "e-posta ile
    sıfırla" diye bir şey yok. Kod kullanıcıya BİR KEZ gösterilir.
    """
    ham = secrets.token_bytes(RECOVERY_CODE_BYTES)
    harfler = "".join(_ALPHABET[bayt % len(_ALPHABET)] for bayt in ham)
    return format_recovery_code(harfler)


def format_recovery_code(code: str) -> str:
    """Kodu dörderli gruplara ayır: elle yazarken yer kaybı olmasın."""
    temiz = normalize_recovery_code(code)
    return "-".join(temiz[i : i + _GROUP] for i in range(0, len(temiz), _GROUP))


def normalize_recovery_code(code: str) -> str:
    """Kullanıcının yazdığı kodu karşılaştırılabilir hâle getir.

    Tire, boşluk ve küçük harf farkı bir HATA DEĞİLDİR: kodu elle kopyalayan
    kullanıcı bunların hepsini yapar ve reddedilmesi anlamsız bir engel olurdu.
    """
    return "".join(ch for ch in code.upper() if ch in _ALPHABET)
